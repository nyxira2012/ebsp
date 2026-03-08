"""Factory module for creating runtime snapshots from configurations.

This module provides a unified factory interface for creating game objects
from their configuration definitions.
"""

from typing import List, Dict, Any, Optional
from .models import (
    MechaSnapshot, PilotConfig, SubPilotConfig, WeaponSnapshot, WeaponType,
    MechaConfig, EquipmentConfig
)


class MechaFactory:
    """Unified factory for creating mecha and weapon snapshots from configs.

    This factory combines the functionality of MechaFactory and SnapshotFactory,
    supporting both basic config loading and advanced features like upgrades
    and equipment modifications.
    """

    @staticmethod
    def _backup_pilot_stats(pilot_config: PilotConfig | None) -> Dict[str, int]:
        """Backup pilot stats for runtime use.

        Args:
            pilot_config: Pilot configuration object, can be None.

        Returns:
            Dictionary containing all pilot stat values. Returns empty dict
            if pilot_config is None.
        """
        if not pilot_config:
            return {}

        return {
            'stat_shooting': pilot_config.stat_shooting,
            'stat_melee': pilot_config.stat_melee,
            'stat_awakening': pilot_config.stat_awakening,
            'stat_defense': pilot_config.stat_defense,
            'stat_reaction': pilot_config.stat_reaction,
            'weapon_proficiency': pilot_config.weapon_proficiency,
            'mecha_proficiency': pilot_config.mecha_proficiency,
        }

    @staticmethod
    def _aggregate_skills(
        pilot_conf: PilotConfig | None,
        equipments: List[EquipmentConfig] | None,
        sub_pilot_conf: Optional[SubPilotConfig] = None
    ) -> List[str]:
        """聚合所有来源的技能列表

        Args:
            pilot_conf: 主驾驶员配置
            equipments: 装备列表
            sub_pilot_conf: 副驾驶配置（可选）

        Returns:
            去重后的技能ID列表
        """
        skills = []

        # 1. 主驾驶员天赋技能
        if pilot_conf and pilot_conf.innate_skills:
            skills.extend(pilot_conf.innate_skills)

        # 2. 装备被动技能 (包括原厂固有和随机技能)
        if equipments:
            for equip in equipments:
                if equip.passive_skills:
                    skills.extend(equip.passive_skills)
                    
        # 2.5. 装备随机技能
        # 注意: 此时技能名和结构需要由调用方预先整合或者稍后改造
        # 但如果是通过 _aggregate_skills 的参数传进去，建议直接在 create_mecha_snapshot 补充

        # 3. 副驾驶技能（如果存在）
        if sub_pilot_conf and hasattr(sub_pilot_conf, 'innate_skills'):
            skills.extend(sub_pilot_conf.innate_skills)

        # 去重并保持顺序
        seen = set()
        result = []
        for skill in skills:
            if skill not in seen:
                seen.add(skill)
                result.append(skill)

        return result

    @staticmethod
    def _aggregate_pilot_stats(
        main_pilot: PilotConfig | None,
        sub_pilot: Optional['SubPilotConfig'] = None
    ) -> Dict[str, int]:
        """聚合主副驾驶员属性

        Args:
            main_pilot: 主驾驶员配置
            sub_pilot: 副驾驶配置（可选）

        Returns:
            聚合后的属性字典
        """
        if not main_pilot:
            return {}

        # 主驾驶员属性（100%）
        stats = {
            'stat_shooting': main_pilot.stat_shooting,
            'stat_melee': main_pilot.stat_melee,
            'stat_awakening': main_pilot.stat_awakening,
            'stat_defense': main_pilot.stat_defense,
            'stat_reaction': main_pilot.stat_reaction,
            'weapon_proficiency': main_pilot.weapon_proficiency,
            'mecha_proficiency': main_pilot.mecha_proficiency,
        }

        # 副驾驶属性（按贡献率叠加）
        if sub_pilot and sub_pilot.contribution_rate > 0:
            rate = sub_pilot.contribution_rate
            stats['stat_shooting'] += int(sub_pilot.stat_shooting * rate)
            stats['stat_melee'] += int(sub_pilot.stat_melee * rate)
            stats['stat_awakening'] += int(sub_pilot.stat_awakening * rate)
            stats['stat_defense'] += int(sub_pilot.stat_defense * rate)
            stats['stat_reaction'] += int(sub_pilot.stat_reaction * rate)
            # 熟练度通常不共享，但可根据需求调整

        return stats

    @staticmethod
    def _backup_sub_pilot_stats(sub_pilot: Optional['SubPilotConfig'] | None) -> Dict[str, int]:
        """备份副驾驶原始属性（用于UI显示等）"""
        if not sub_pilot:
            return {}

        return {
            'stat_shooting': sub_pilot.stat_shooting,
            'stat_melee': sub_pilot.stat_melee,
            'stat_awakening': sub_pilot.stat_awakening,
            'stat_defense': sub_pilot.stat_defense,
            'stat_reaction': sub_pilot.stat_reaction,
        }

    @staticmethod
    def _validate_equipment_slot(
        equip: EquipmentConfig,
        slot_type: str,
        mecha_series: str = ""
    ) -> bool:
        """验证装备是否可安装到指定槽位

        Args:
            equip: 装备配置
            slot_type: 槽位类型
            mecha_series: 机体系列标识（用于EXCLUSIVE验证）

        Returns:
            是否可安装
        """
        # EXCLUSIVE槽位检查
        if slot_type == "EXCLUSIVE":
            if not equip.compatible_series:
                return False  # 非专属装备不能装EXCLUSIVE槽
            return mecha_series in equip.compatible_series

        # 其他槽位的基本类型检查
        if slot_type == "WEAPON":
            return equip.type == "WEAPON"
        if slot_type == "EQUIP":
            return equip.type == "EQUIP"
        if slot_type == "FIXED":
            return True  # FIXED槽位由fixed_weapons管理

        return False

    @staticmethod
    def _apply_equipment_modifiers(
        equipments: List[EquipmentConfig] | None,
        base_mobility: float,
        base_hit: float,
        base_hp: int = 0,
        base_en: int = 0,
        base_armor: int = 0,
        base_en_regen_rate: float = 0.0,
        base_en_regen_fixed: int = 0,
        equipment_random_stats: List[Dict[str, Any]] | None = None,
        affix_configs: Dict[str, Any] | None = None
    ) -> tuple[int, int, int, float, float, float, float, float, float, float, float, int, List[WeaponSnapshot]]:
        """Apply equipment stat modifiers and collect weapons.

        Args:
            equipments: List of equipment configurations.
            base_mobility: Base mobility value.
            base_hit: Base hit rate value.
            base_hp: Base HP value.
            base_en: Base EN value.
            base_armor: Base armor value.
            base_en_regen_rate: Base EN regeneration rate (percentage).
            base_en_regen_fixed: Base EN regeneration fixed value.

        Returns:
            Tuple of (hp, en, armor, mobility, hit, dodge, parry, block, precision, crit, en_regen_rate, en_regen_fixed, weapons).
        """
        weapons = []
        final_hp = base_hp
        final_en = base_en
        final_armor = base_armor
        final_mobility = float(base_mobility)
        final_hit = base_hit
        final_dodge = 0.0
        final_parry = 0.0
        final_block = 0.0
        final_precision = 0.0
        final_crit = 0.0
        final_en_regen_rate = base_en_regen_rate
        final_en_regen_fixed = base_en_regen_fixed

        if not equipments:
            return final_hp, final_en, final_armor, final_mobility, final_hit, final_dodge, final_parry, final_block, final_precision, final_crit, final_en_regen_rate, final_en_regen_fixed, weapons

        for i, equip in enumerate(equipments):
            # Collect weapons
            if equip.type == "WEAPON":
                weapons.append(MechaFactory.create_weapon_snapshot(equip))

            # Apply base stat modifiers
            for stat_name, value in equip.stat_modifiers.items():
                if stat_name == "final_max_hp" or stat_name == "init_hp":
                    final_hp += int(value)
                elif stat_name == "final_max_en" or stat_name == "init_en":
                    final_en += int(value)
                elif stat_name == "final_armor" or stat_name == "init_armor":
                    final_armor += int(value)
                elif stat_name == "final_mobility" or stat_name == "init_mobility":
                    final_mobility += float(value)
                elif stat_name == "final_hit":
                    final_hit += value
                elif stat_name == "final_dodge":
                    final_dodge += value
                elif stat_name == "final_parry":
                    final_parry += value
                elif stat_name == "final_block":
                    final_block += value
                elif stat_name == "final_precision":
                    final_precision += value
                elif stat_name == "final_crit":
                    final_crit += value
                elif stat_name == "final_en_regen_rate":
                    final_en_regen_rate += value
                elif stat_name == "final_en_regen_fixed":
                    final_en_regen_fixed += int(value)

            # Apply random stat affixes (Doc 8)
            if equipment_random_stats and i < len(equipment_random_stats) and affix_configs:
                r_stats = equipment_random_stats[i]
                if r_stats:
                    ilvl = r_stats.get("ilvl", 0)
                    affixes = r_stats.get("affixes", [])
                    tier_multipliers = {1: 0.70, 2: 0.85, 3: 1.00, 4: 1.15}
                    
                    for affix_entry in affixes:
                        affix_id = affix_entry.get("id")
                        t = affix_entry.get("t")
                        if affix_id in affix_configs and t in tier_multipliers:
                            affix = affix_configs[affix_id]
                            if affix.type == "stat" and affix.target:
                                val = affix.base_value + ilvl * affix.ilvl_scale * tier_multipliers[t]
                                
                                # Inject into local vars matching stat names
                                target = affix.target
                                if target == "final_max_hp" or target == "init_hp":
                                    final_hp += int(val)
                                elif target == "final_max_en" or target == "init_en":
                                    final_en += int(val)
                                elif target == "final_armor" or target == "init_armor":
                                    final_armor += int(val)
                                elif target == "final_mobility" or target == "init_mobility":
                                    final_mobility += float(val)
                                elif target == "final_hit":
                                    final_hit += val
                                elif target == "final_dodge":
                                    final_dodge += val
                                elif target == "final_parry":
                                    final_parry += val
                                elif target == "final_block":
                                    final_block += val
                                elif target == "final_precision":
                                    final_precision += val
                                elif target == "final_crit":
                                    final_crit += val
                                elif target == "final_en_regen_rate":
                                    final_en_regen_rate += val
                                elif target == "final_en_regen_fixed":
                                    final_en_regen_fixed += int(val)

        return final_hp, final_en, final_armor, final_mobility, final_hit, final_dodge, final_parry, final_block, final_precision, final_crit, final_en_regen_rate, final_en_regen_fixed, weapons

    @staticmethod
    def create_mecha_snapshot(
        mecha_conf: MechaConfig,
        pilot_conf: PilotConfig | None = None,
        equipments: List[EquipmentConfig] | None = None,
        weapon_configs: dict | None = None,
        upgrade_level: int = 0,
        sub_pilot_conf: Optional[SubPilotConfig] = None,
        upgrade_bonuses: Dict[str, int] | None = None,
        equipment_random_stats: List[Dict[str, Any]] | None = None,
        affix_configs: Dict[str, Any] | None = None
    ) -> MechaSnapshot:
        """Create a MechaSnapshot from configuration with optional enhancements.

        Args:
            mecha_conf: Mecha configuration object.
            pilot_conf: Optional pilot configuration for stat backup.
            equipments: Optional list of equipment to apply modifiers.
            weapon_configs: Optional dict of weapon configs keyed by ID.
            upgrade_level: Legacy upgrade level (deprecated, use upgrade_bonuses).
            sub_pilot_conf: Optional sub-pilot configuration.
            upgrade_bonuses: Per-attribute upgrade bonuses dict.
                Keys: "hp", "en", "armor", "mobility". Values: flat bonus amounts.
                If provided, overrides upgrade_level.

        Returns:
            Fully configured MechaSnapshot ready for combat.
        """
        # 聚合主副驾驶员属性
        pilot_stats_backup = MechaFactory._aggregate_pilot_stats(
            pilot_conf, sub_pilot_conf
        )
        sub_pilot_stats_backup = MechaFactory._backup_sub_pilot_stats(sub_pilot_conf)
        contribution_rate = sub_pilot_conf.contribution_rate if sub_pilot_conf else 0.0

        # 聚合技能（支持副驾驶）
        skills = MechaFactory._aggregate_skills(pilot_conf, equipments, sub_pilot_conf)
        
        # 加上装备产生的随机技能
        if equipment_random_stats:
            for r_stats in equipment_random_stats:
                if r_stats and r_stats.get("skill"):
                    r_skill = r_stats.get("skill")
                    if r_skill not in skills:
                        skills.append(r_skill)

        # Apply upgrade bonuses (new dict-based system takes priority over legacy upgrade_level)
        if upgrade_bonuses is not None:
            hp_bonus = upgrade_bonuses.get("hp", 0)
            en_bonus = upgrade_bonuses.get("en", 0)
            armor_bonus = upgrade_bonuses.get("armor", 0)
            mobility_bonus = upgrade_bonuses.get("mobility", 0)
        else:
            # Legacy fallback: single upgrade_level applies fixed scaling
            hp_bonus = upgrade_level * 200
            en_bonus = 0
            armor_bonus = upgrade_level * 20
            mobility_bonus = 0

        # Calculate base stats
        base_hp = mecha_conf.init_hp + hp_bonus
        base_en = mecha_conf.init_en + en_bonus
        base_armor = mecha_conf.init_armor + armor_bonus
        base_mobility = mecha_conf.init_mobility + mobility_bonus
        base_hit = mecha_conf.init_hit
        base_en_regen_rate = mecha_conf.init_en_regen_rate
        base_en_regen_fixed = mecha_conf.init_en_regen_fixed

        # Apply equipment modifiers (returns all modified stats)
        (final_hp, final_en, final_armor, final_mobility, final_hit,
         final_dodge, final_parry, final_block, final_precision, final_crit,
         final_en_regen_rate, final_en_regen_fixed, weapons) = (
            MechaFactory._apply_equipment_modifiers(
                equipments, base_mobility, base_hit, base_hp, base_en, base_armor,
                base_en_regen_rate, base_en_regen_fixed,
                equipment_random_stats, affix_configs
            )
        )

        # Load fixed weapons from mecha configuration
        if hasattr(mecha_conf, 'fixed_weapons') and mecha_conf.fixed_weapons:
            for weapon_id in mecha_conf.fixed_weapons:
                if weapon_configs and weapon_id in weapon_configs:
                    weapons.append(MechaFactory.create_weapon_snapshot(weapon_configs[weapon_id]))

        # Construct snapshot
        return MechaSnapshot(
            instance_id=mecha_conf.id,
            mecha_name=mecha_conf.name,
            main_portrait=mecha_conf.portrait_id,
            model_asset=mecha_conf.model_asset,
            final_max_hp=int(final_hp),
            current_hp=int(final_hp),
            final_max_en=int(final_en),
            current_en=int(final_en),
            final_armor=int(final_armor),
            final_mobility=int(final_mobility),
            final_hit=final_hit,
            final_precision=mecha_conf.init_precision + final_precision,
            final_crit=mecha_conf.init_crit + final_crit,
            final_dodge=mecha_conf.init_dodge + final_dodge,
            final_parry=mecha_conf.init_parry + final_parry,
            final_block=mecha_conf.init_block + final_block,
            block_reduction=mecha_conf.init_block_red,
            final_en_regen_rate=final_en_regen_rate,
            final_en_regen_fixed=final_en_regen_fixed,
            pilot_stats_backup=pilot_stats_backup,
            sub_pilot_stats_backup=sub_pilot_stats_backup,
            sub_pilot_contribution_rate=contribution_rate,
            sub_portrait=sub_pilot_conf.portrait_id if sub_pilot_conf else None,
            weapons=weapons,
            skills=skills,
        )

    @staticmethod
    def create_weapon_snapshot(config: EquipmentConfig) -> WeaponSnapshot:
        """Create a WeaponSnapshot from equipment configuration.

        Args:
            config: Equipment configuration object.

        Returns:
            WeaponSnapshot with default values for missing attributes.
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
