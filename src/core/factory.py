"""
快照工厂 (SnapshotFactory)

负责将静态数据 (JSON 配置) 与动态养成就度 (DB) 组合在一起，
生成用于解耦版战斗引擎的运行时快照 (MechaSnapshot)。
"""

import copy
from typing import Dict, Any, List

from sqlalchemy.ext.asyncio import AsyncSession

from src.models import MechaSnapshot, MechaConfig, WeaponSnapshot
from src.user.repository import UserRepository
from src.user.schemas import UserMechaDB

# 简单的属性按级成长系数（后期可转移到 JSON 配置中或专门的规则引擎）
UPGRADE_SCALING = {
    "hp": 50,
    "en": 5,
    "armor": 20,
    "mobility": 5,
}

class SnapshotFactory:
    """组合不同数据源生成运行时战斗对象的工厂"""

    def __init__(self, static_db: Any, user_repo: UserRepository):
        """
        初始化工厂
        
        Args:
            static_db: 静态数据管理器 (StaticDataService，能读取 mechas.json)
            user_repo: 数据库仓储类，用于获取用户养成进度
        """
        self.static_db = static_db
        self.user_repo = user_repo

    async def create_combat_snapshot(
        self, session: AsyncSession, user_id: int, user_mecha_id: int
    ) -> MechaSnapshot:
        """根据数据库养成记录与静态配置生成机体快照"""

        # 1. 查 DB：获取“养成数据” (包含 JSONB 被序列化后的 updates)
        user_mecha_model = await self.user_repo.get_user_mecha(session, user_mecha_id)
        if not user_mecha_model:
            raise ValueError(f"不存在的机体资产: ID={user_mecha_id}")

        # 将 SQLAlchemy ORM 模型显式转为 Pydantic DB 模型，利用 Pydantic 的默认补全
        user_mecha_db = UserMechaDB.model_validate(user_mecha_model)

        # 2. 查 JSON：获取机体的“静态数据”
        base_mech_config: MechaConfig = self.static_db.get_mecha(user_mecha_db.mech_id)
        if not base_mech_config:
            # 兜底：如果这台机甲在配置里被删除了可以采用 FALLBACK，这里暂不抛出
            raise ValueError(f"未知的机体原型 ID: {user_mecha_db.mech_id}")

        # 3. 核心拼接逻辑：计算最终属性
        # 公式: 基础属性 + (养成等级 * 每级成长偏量)
        upgrades = user_mecha_db.upgrades

        final_hp = base_mech_config.init_hp + (upgrades.hp * UPGRADE_SCALING["hp"])
        final_en = base_mech_config.init_en + (upgrades.en * UPGRADE_SCALING["en"])
        final_armor = base_mech_config.init_armor + (upgrades.armor * UPGRADE_SCALING["armor"])
        final_mobility = base_mech_config.init_mobility + (upgrades.mobility * UPGRADE_SCALING["mobility"])

        # 4. 构建并返回快照对象
        mecha = MechaSnapshot(
            instance_id=f"user_{user_id}_mech_{user_mecha_db.id}",
            mecha_name=user_mecha_db.nickname or base_mech_config.name,
            model_asset=base_mech_config.model_asset,
            main_portrait=base_mech_config.portrait_id,

            # 注入拼接后的最大数值和当前数值（开战时满状态）
            final_max_hp=final_hp,
            current_hp=final_hp,
            final_max_en=final_en,
            current_en=final_en,
            
            final_armor=final_armor,
            final_mobility=final_mobility,

            # 同步基础静态属性
            final_hit=base_mech_config.init_hit,
            final_precision=base_mech_config.init_precision,
            final_crit=base_mech_config.init_crit,
            final_dodge=base_mech_config.init_dodge,
            final_parry=base_mech_config.init_parry,
            final_block=base_mech_config.init_block,
            block_reduction=base_mech_config.init_block_red,
            
            final_en_regen_rate=base_mech_config.init_en_regen_rate,
            final_en_regen_fixed=base_mech_config.init_en_regen_fixed,
        )

        # TODO: 从 DB 里捞取装配在该机体上的专属武器（user_equipments），这也会组合进 Factory
        self._hydrate_weapons(mecha, base_mech_config)

        # 将技能应用在当前实例上
        from src.skills import TraitManager
        TraitManager.apply_traits(mecha)

        return mecha

    def _hydrate_weapons(self, mecha: MechaSnapshot, config: MechaConfig):
        """将 JSON 中的外挂装备/固定武器填入快照中"""
        # 注意: 这一部分逻辑会随着未来实现装配表而不断完善。目前先走默认配置的固定武器。
        weapons: List[WeaponSnapshot] = []
        for w_id in config.fixed_weapons:
            w_config = self.static_db.get_equipment(w_id)
            if not w_config or w_config.type != "WEAPON":
                continue
            
            weapons.append(WeaponSnapshot(
                uid=f"{mecha.instance_id}_{w_id}",
                definition_id=w_id,
                name=w_config.name,
                type=w_config.weapon_type,
                final_power=w_config.weapon_power or 0, # 没有受过强化
                range_min=w_config.weapon_range_min or 0,
                range_max=w_config.weapon_range_max or 0,
                en_cost=w_config.weapon_en_cost or 0,
                will_req=w_config.weapon_will_req or 0,
                anim_id=w_config.weapon_anim_id,
            ))
        mecha.weapons = weapons
