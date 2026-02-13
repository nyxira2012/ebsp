"""
工厂模块 - 从配置创建运行时快照
"""

from typing import List, Dict, Any
from .models import (
    MechaSnapshot, PilotConfig, WeaponSnapshot, WeaponType,
    MechaConfig, EquipmentConfig
)


class MechaFactory:
    """机体工厂 - 从配置创建运行时快照"""

    @staticmethod
    def create_from_config(config: MechaConfig, pilot_config: PilotConfig | None = None) -> MechaSnapshot:
        """从 MechaConfig 创建 MechaSnapshot

        Args:
            config: 机体配置
            pilot_config: 驾驶员配置（可选）

        Returns:
            MechaSnapshot: 机体运行时快照
        """
        # 备份驾驶员属性
        pilot_stats_backup = {}
        if pilot_config:
            pilot_stats_backup = {
                'stat_shooting': pilot_config.stat_shooting,
                'stat_melee': pilot_config.stat_melee,
                'stat_awakening': pilot_config.stat_awakening,
                'stat_defense': pilot_config.stat_defense,
                'stat_reaction': pilot_config.stat_reaction,
                'weapon_proficiency': pilot_config.weapon_proficiency,
                'mecha_proficiency': pilot_config.mecha_proficiency,
            }

        # 创建 MechaSnapshot
        snapshot = MechaSnapshot(
            instance_id=config.id,
            mecha_name=config.name,
            main_portrait=config.portrait_id,
            model_asset=config.model_asset,

            # 资源属性
            final_max_hp=config.init_hp,
            current_hp=config.init_hp,
            final_max_en=config.init_en,
            current_en=config.init_en,

            # 战斗属性
            final_armor=config.init_armor,
            final_mobility=config.init_mobility,

            # 判定属性
            final_hit=config.init_hit,
            final_precision=config.init_precision,
            final_crit=config.init_crit,

            final_dodge=config.init_dodge,
            final_parry=config.init_parry,
            final_block=config.init_block,
            block_reduction=config.init_block_red,

            # 驾驶员属性备份
            pilot_stats_backup=pilot_stats_backup,

            # 初始武器列表（需要额外加载装备配置）
            weapons=[],
            skills=[],
        )

        return snapshot

    @staticmethod
    def create_weapon_from_config(config: EquipmentConfig) -> WeaponSnapshot:
        """从 EquipmentConfig 创建 WeaponSnapshot

        Args:
            config: 装备配置

        Returns:
            WeaponSnapshot: 武器快照
        """
        return WeaponSnapshot(
            uid=f"{config.id}_uid",
            definition_id=config.id,
            name=config.name,
            type=config.weapon_type or WeaponType.SHOOTING,
            final_power=config.weapon_power or 1000,
            en_cost=config.weapon_en_cost or 10,
            range_min=config.weapon_range_min or 0,
            range_max=config.weapon_range_max or 6000,
            will_req=config.weapon_will_req or 0,
            anim_id=config.weapon_anim_id or "default_anim",
            tags=config.weapon_tags or [],
        )


class SnapshotFactory:
    """快照工厂 - 用于测试"""

    @staticmethod
    def create_mecha_snapshot(
        mecha_conf: MechaConfig,
        pilot_conf: PilotConfig | None = None,
        equipments: List[EquipmentConfig] | None = None,
        upgrade_level: int = 0
    ) -> MechaSnapshot:
        """创建 MechaSnapshot

        Args:
            mecha_conf: 机体配置
            pilot_conf: 驾驶员配置
            equipments: 装备列表
            upgrade_level: 改造等级

        Returns:
            MechaSnapshot: 机体快照
        """
        # 备份驾驶员属性
        pilot_stats_backup = {}
        if pilot_conf:
            pilot_stats_backup = {
                'stat_shooting': pilot_conf.stat_shooting,
                'stat_melee': pilot_conf.stat_melee,
                'stat_awakening': pilot_conf.stat_awakening,
                'stat_defense': pilot_conf.stat_defense,
                'stat_reaction': pilot_conf.stat_reaction,
                'weapon_proficiency': pilot_conf.weapon_proficiency,
                'mecha_proficiency': pilot_conf.mecha_proficiency,
            }

        # 应用改造加成
        hp_bonus = upgrade_level * 200
        armor_bonus = upgrade_level * 20

        # 初始化属性
        final_hp = mecha_conf.init_hp + hp_bonus
        final_armor = mecha_conf.init_armor + armor_bonus
        final_mobility = mecha_conf.init_mobility
        final_hit = mecha_conf.init_hit

        # 应用装备属性修正
        weapons = []
        if equipments:
            for equip in equipments:
                if equip.type == "WEAPON":
                    weapons.append(SnapshotFactory.create_weapon_snapshot(equip))
                # 应用装备属性修正
                for stat_name, value in equip.stat_modifiers.items():
                    if stat_name == "mobility":
                        final_mobility += int(value)
                    elif stat_name == "hit_rate":
                        final_hit += value

        snapshot = MechaSnapshot(
            instance_id=mecha_conf.id,
            mecha_name=mecha_conf.name,
            main_portrait=mecha_conf.portrait_id,
            model_asset=mecha_conf.model_asset,
            final_max_hp=int(final_hp),
            current_hp=int(final_hp),
            final_max_en=mecha_conf.init_en,
            current_en=mecha_conf.init_en,
            final_armor=int(final_armor),
            final_mobility=int(final_mobility),
            final_hit=final_hit,
            final_precision=mecha_conf.init_precision,
            final_crit=mecha_conf.init_crit,
            final_dodge=mecha_conf.init_dodge,
            final_parry=mecha_conf.init_parry,
            final_block=mecha_conf.init_block,
            block_reduction=mecha_conf.init_block_red,
            pilot_stats_backup=pilot_stats_backup,
            weapons=weapons,
            skills=[],
        )

        return snapshot

    @staticmethod
    def create_weapon_snapshot(config: EquipmentConfig) -> WeaponSnapshot:
        """从 EquipmentConfig 创建 WeaponSnapshot"""
        return WeaponSnapshot(
            uid=f"{config.id}_uid",
            definition_id=config.id,
            name=config.name,
            type=config.weapon_type or WeaponType.SHOOTING,
            final_power=config.weapon_power or 1000,
            en_cost=config.weapon_en_cost or 10,
            range_min=config.weapon_range_min or 0,
            range_max=config.weapon_range_max or 6000,
            will_req=config.weapon_will_req or 0,
            anim_id=config.weapon_anim_id or "default_anim",
            tags=config.weapon_tags or [],
        )
