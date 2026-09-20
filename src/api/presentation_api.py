"""
FastAPI 主应用文件

提供战斗模拟 API 和用户系统集成。
"""

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Literal, Optional

from src.combat.engagement import Engagement
from src.combat.entry import BattleEntryService
from src.presentation.contracts import TimelineDocument
from src import DataLoader
from src.api.context import set_loader, get_loader
from src.presentation.registry import initialize_shared_registry
from src.models import PracticeScenarioKind, PracticeScenarioConfig

# 数据库与用户系统
from src.database import init_db, close_db
from src.database.session import get_async_session
from src.database.models import User
from src.api import user_api, inventory_api, pve_api
from src.user.dependencies import get_optional_user
from sqlalchemy.ext.asyncio import AsyncSession

app = FastAPI(title="EBSP Combat Presentation API")

# 挂载路由
app.include_router(user_api.router, prefix="/api")
app.include_router(inventory_api.router, prefix="/api")
app.include_router(pve_api.router, prefix="/api")

# 全局状态管理由 src.api.context 负责

# ==============================================================================
# 请求模型
# ==============================================================================

class BattleRequest(BaseModel):
    mecha_a_id: str
    mecha_b_id: str

    # 战报入口标记（Doc 14 v1.7）：客户端只可声明 debug/training，
    # pve/pvp 为服务端内部标签，经此参数声明一律 422 拒绝
    route: Literal["debug", "training"] = "debug"

    # 可选: 使用用户存档覆盖机体配置
    use_user_save_for_a: bool = False
    use_user_save_for_b: bool = False

    # 规则环境（Doc 16 §5.3）：练习场防御测试局声明战斗规则环境；
    # None = 不注入，调试老路径零变化
    environment_id: Optional[str] = None


class PracticeScenarioItem(BaseModel):
    """练习场对局条目（Doc 16 v1.2 八字段）：契约不携带任何图片资源引用。

    立绘解析归前端"配置 ID → 图片路径"对照表（Doc 14 §9.1 裁决）；
    机体官方名由加载器从机体配置派生（单一真相），不进练习场配置文件。
    environment_id 直取自场景配置（用户追认生效，Doc 16 v1.4）——前端拿它
    透传 simulate，隐映射（角标 kind 反查环境）会造成两处真相漂移。
    """
    name: str
    description: str
    mecha_a_id: str   # 我方（画面左侧；登录时为演示/降级配置）
    mecha_b_id: str   # 敌方（画面右侧）
    mecha_a_name: str
    mecha_b_name: str
    environment_id: str
    kind: PracticeScenarioKind

# ==============================================================================
# 生命周期事件
# ==============================================================================

@app.on_event("startup")
async def startup_event():
    """服务启动时初始化数据库和加载数据"""
    global _loader

    # 1. 初始化数据库表
    await init_db()
    print("✅ 数据库初始化完成")

    # 2. 加载游戏配置数据
    loader = DataLoader(data_dir="data")
    loader.load_all()
    set_loader(loader)
    print(f"✅ 数据加载完成: {len(loader.mechas)} 机体, {len(loader.equipments)} 装备")

    # 3. 加载演出模板 (CPS v5.1)：进程内唯一加载点，引擎侧经 get_shared_registry 共用
    # 使用异常处理代替 os.path.exists() 避免 TOCTOU 反模式
    import os
    template_path = os.path.join("data", "presentation", "templates.yaml")
    try:
        shared_registry = initialize_shared_registry(template_path)
        print(f"✅ 演出模板加载完成: {len(shared_registry.action_bones)} ActionBone, "
              f"{len(shared_registry.reaction_bones)} ReactionBone")
    except FileNotFoundError:
        print(f"⚠️  演出模板文件不存在: {template_path}，将使用 T3 兜底文本")

    # 4. 启动后台守护任务
    from src.pve.heartbeat import HeartbeatGuard
    HeartbeatGuard.start()
    print("✅ PVE 心跳守护已启动")

@app.on_event("shutdown")
async def shutdown_event():
    """服务关闭时清理资源"""
    from src.pve.heartbeat import HeartbeatGuard
    HeartbeatGuard.stop()
    
    await close_db()
    print("✅ 数据库连接已关闭")

# ==============================================================================
# 辅助函数
# ==============================================================================

# get_loader 已移至 src.api.context

# ==============================================================================
# API 路由
# ==============================================================================

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/battle/practice", response_model=List[PracticeScenarioItem])
def list_practice_scenarios():
    """
    练习场对局列表（只读配置，Doc 16）。

    - 纯静态投影：读 `data/practice_scenarios.json`，无状态、无鉴权、不触战斗引擎。
    - 前端选一场后，以条目里的 `mecha_a_id` / `mecha_b_id` 直接调
      `POST /battle/simulate`（列表不发明第二个开战入口）。
    - 立绘规则（Doc 14 §9.1 裁决）：后端契约只报配置 ID，图片路径由前端
      对照表解析，缺图走前端自有降级。
    """
    loader = get_loader()
    loader.practice_scenarios.clear()
    loader._load_from_json("practice_scenarios.json", PracticeScenarioConfig, loader.practice_scenarios, keep_first=True)
    loader._validate_practice_scenarios()
    return [
        PracticeScenarioItem(
            name=s.name,
            description=s.description,
            mecha_a_id=s.mecha_a_id,
            mecha_b_id=s.mecha_b_id,
            # 官方名从机体配置派生（Doc 16 §3：名字单一真相归后端）
            mecha_a_name=loader.mechas[s.mecha_a_id].name,
            mecha_b_name=loader.mechas[s.mecha_b_id].name,
            # environment_id 直取场景配置（前端透传 simulate）；kind 从环境
            # 派生（v1.2 契约切换，Doc 16 §5.3）——坏环境引用已在加载期
            # 剔除，运行时不可能缺
            environment_id=s.environment_id,
            kind=loader.environments[s.environment_id].kind,
        )
        for s in loader.get_all_practice_scenarios()
    ]

@app.post("/battle/simulate", response_model=TimelineDocument)
async def simulate_battle(
    req: BattleRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    模拟战斗

    - **mecha_a_id**: 机体 A 的配置 ID
    - **mecha_b_id**: 机体 B 的配置 ID
    - **route**: 战报入口标记（debug/training，默认 debug）
    - **environment_id**: 规则环境 ID（可选，Doc 16 §5.3；None 不注入）
    - **use_user_save_for_a**: 是否使用用户存档覆盖机体 A (需要登录)
    - **use_user_save_for_b**: 是否使用用户存档覆盖机体 B (需要登录)

    如果用户已登录并设置 use_user_save，则从用户的出战存档加载机体配置。
    """
    try:
        loader = get_loader()

        # 装配走收发室（红线 5：单点装配，E1 收编）；
        # 未知机体 ID → KeyError → 404（Doc 14 §2 契约）
        spec = await BattleEntryService.build_debug(loader, req, current_user, session)

        # 执行裁定：快照交裁判，拿完整战报（Doc 15 §5 simulate 行；
        # 契约即响应模型，序列化漏字段在结构上不可能——红线 1）
        report = Engagement(spec).resolve()

        return report.timeline

    except KeyError:
        raise HTTPException(status_code=404, detail="机体配置不存在")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn  # type: ignore
    uvicorn.run(app, host="0.0.0.0", port=8000)
