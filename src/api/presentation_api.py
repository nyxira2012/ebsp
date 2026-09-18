"""
FastAPI 主应用文件

提供战斗模拟 API 和用户系统集成。
"""

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from src.combat.engagement import Engagement
from src.combat.entry import BattleEntryService
from src.presentation.contracts import TimelineDocument
from src import DataLoader
from src.api.context import set_loader, get_loader, initialize_presentation_registry

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

    # 可选: 使用用户存档覆盖机体配置
    use_user_save_for_a: bool = False
    use_user_save_for_b: bool = False

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

    # 3. 加载演出模板 (CPS v5.1)
    # 使用异常处理代替 os.path.exists() 避免 TOCTOU 反模式
    from src.api.context import initialize_presentation_registry
    import os
    template_path = os.path.join("data", "presentation", "templates.yaml")
    try:
        initialize_presentation_registry(template_path)
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
