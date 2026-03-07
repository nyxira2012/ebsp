"""
快照服务 (SnapshotService)

职责：从 DB 获取用户养成数据，从静态配置获取基础数据，
然后委托 MechaFactory 完成最终的快照组装。

自身不包含任何属性计算逻辑。
"""

from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import MechaSnapshot, MechaConfig
from src.factory import MechaFactory
from src.user.repository import UserAssetRepository
from src.user.schemas import UserMechaDB

# 属性按级成长系数（后期可转移到 JSON 配置中或专门的规则引擎）
UPGRADE_SCALING = {
    "hp": 50,
    "en": 5,
    "armor": 20,
    "mobility": 5,
}


class SnapshotFactory:
    """从 DB 养成数据 + 静态配置生成战斗快照的服务层。

    核心原则：
    - 本类只负责「数据获取」和「编排」
    - 所有属性计算逻辑统一委托给 MechaFactory
    """

    def __init__(self, static_db: Any, user_repo: UserAssetRepository):
        """
        初始化服务

        Args:
            static_db: 静态数据管理器 (DataLoader，能读取 mechas.json)
            user_repo: 数据库仓储类，用于获取用户养成进度
        """
        self.static_db = static_db
        self.user_repo = user_repo

    async def create_combat_snapshot(
        self, session: AsyncSession, user_id: int, user_mecha_id: int
    ) -> MechaSnapshot:
        """根据数据库养成记录与静态配置生成机体快照。

        流程:
        1. 查 DB → 获取养成数据 (改造等级)
        2. 查 JSON → 获取机体静态配置
        3. 计算升级加成 → 转为 upgrade_bonuses 字典
        4. 委托 MechaFactory → 组装完整快照
        """

        # ── Step 1: 从 DB 获取用户养成数据 ──
        user_mecha_model = await self.user_repo.get_user_mecha(session, user_mecha_id)
        if not user_mecha_model:
            raise ValueError(f"不存在的机体资产: ID={user_mecha_id}")

        user_mecha_db = UserMechaDB.model_validate(user_mecha_model)

        # ── Step 2: 从静态配置获取机体原型 ──
        base_config: MechaConfig = self.static_db.get_mecha(user_mecha_db.mech_id)
        if not base_config:
            raise ValueError(f"未知的机体原型 ID: {user_mecha_db.mech_id}")

        # ── Step 3: 将养成数据转为 upgrade_bonuses ──
        upgrades = user_mecha_db.upgrades
        upgrade_bonuses = {
            "hp": upgrades.hp * UPGRADE_SCALING["hp"],
            "en": upgrades.en * UPGRADE_SCALING["en"],
            "armor": upgrades.armor * UPGRADE_SCALING["armor"],
            "mobility": upgrades.mobility * UPGRADE_SCALING["mobility"],
        }

        # ── Step 4: 收集武器配置 (固定武器的 EquipmentConfig 字典) ──
        weapon_configs = {}
        if hasattr(self.static_db, 'equipments'):
            weapon_configs = self.static_db.equipments

        # ── Step 5: 委托 MechaFactory 组装快照 ──
        # TODO: 未来从 DB 查询装配的驾驶员、外挂装备、副驾驶等
        #   pilot_conf = self.static_db.get_pilot(user_pilot_db.pilot_id)
        #   equipments = [self.static_db.get_equipment(e.equipment_id) for e in user_equips]
        mecha = MechaFactory.create_mecha_snapshot(
            mecha_conf=base_config,
            pilot_conf=None,           # TODO: 接入用户驾驶员
            equipments=None,           # TODO: 接入用户装备
            weapon_configs=weapon_configs,
            upgrade_bonuses=upgrade_bonuses,
        )

        # 覆盖实例 ID 和昵称（来自用户数据）
        mecha.instance_id = f"user_{user_id}_mech_{user_mecha_db.id}"
        if user_mecha_db.nickname:
            mecha.mecha_name = user_mecha_db.nickname

        return mecha
