"""
FastAPI 主应用文件

提供战斗模拟 API 和用户系统集成。
"""

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from src.models import Mecha, PilotConfig, MechaConfig, Weapon, WeaponType
from src.factory import MechaFactory
from src.combat.engine import BattleSimulator
from src.presentation.renderer import JSONRenderer
from src import DataLoader

# 数据库与用户系统
from src.database import init_db, close_db
from src.database.session import get_async_session
from src.database.models import User
from src.api import user_api
from src.user.repository import UserAssetRepository
from src.user.dependencies import get_optional_user
from sqlalchemy.ext.asyncio import AsyncSession

app = FastAPI(title="EBSP Combat Presentation API")

# 挂载用户路由
app.include_router(user_api.router, prefix="/api")

# 全局数据加载器（服务启动时初始化）
_loader: DataLoader | None = None

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
    _loader = DataLoader(data_dir="data")
    _loader.load_all()
    print(f"✅ 数据加载完成: {len(_loader.mechas)} 机体, {len(_loader.equipments)} 装备")

@app.on_event("shutdown")
async def shutdown_event():
    """服务关闭时清理资源"""
    await close_db()
    print("✅ 数据库连接已关闭")

# ==============================================================================
# 辅助函数
# ==============================================================================

def get_loader() -> DataLoader:
    """获取全局数据加载器"""
    if _loader is None:
        raise RuntimeError("数据加载器未初始化")
    return _loader

# ==============================================================================
# API 路由
# ==============================================================================

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/battle/simulate")
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

        # 获取基础配置
        config_a = loader.get_mecha_config(req.mecha_a_id)
        config_b = loader.get_mecha_config(req.mecha_b_id)

        if not config_a or not config_b:
            raise HTTPException(status_code=404, detail="机体配置不存在")

        # 创建基础快照
        mecha_a = MechaFactory.create_mecha_snapshot(config_a, weapon_configs=loader.equipments)
        mecha_b = MechaFactory.create_mecha_snapshot(config_b, weapon_configs=loader.equipments)

        # 如果用户已登录，尝试加载出战小队阵容覆盖
        if current_user is not None:
            active_squad = await UserAssetRepository.get_active_squad(session, current_user.id)

            if active_squad is not None and len(active_squad.mecha_ids) > 0:
                try:
                    # 获取工厂
                    from src.core.factory import SnapshotFactory
                    factory = SnapshotFactory(loader, UserAssetRepository())
                    
                    # 取出战小队的第一台和第二台机体进行覆盖
                    # 实际业务中应配合请求参数选择出战序号，此处作为平滑过渡
                    user_mechas = active_squad.mecha_ids
                    
                    if req.use_user_save_for_a and len(user_mechas) > 0:
                        mecha_a = await factory.create_combat_snapshot(session, current_user.id, user_mechas[0])
                    
                    if req.use_user_save_for_b and len(user_mechas) > 1:
                        mecha_b = await factory.create_combat_snapshot(session, current_user.id, user_mechas[1])
                    elif req.use_user_save_for_b and len(user_mechas) > 0:
                        # 兜底：如果选了B但只有一个机甲，用那个
                        mecha_b = await factory.create_combat_snapshot(session, current_user.id, user_mechas[0])

                except ValueError as e:
                    # 养成数据无效，忽略并使用默认配置
                    print(f"⚠️ 玩家出战数据无效，使用默认配置: {e}")

        # 执行战斗模拟
        sim = BattleSimulator(mecha_a, mecha_b, enable_presentation=True)
        sim.run_battle()

        timeline = sim.presentation_timeline
        json_data = JSONRenderer.render_timeline(timeline)

        return json_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn  # type: ignore
    uvicorn.run(app, host="0.0.0.0", port=8000)
