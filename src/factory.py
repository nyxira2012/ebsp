"""Factory module for creating runtime snapshots from configurations.

This module provides a unified factory interface for creating game objects
from their configuration definitions.
"""

from typing import List, Dict, Any
from .models import (
    MechaSnapshot, PilotConfig, WeaponSnapshot, WeaponType,
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
    def _apply_equipment_modifiers(
        equipments: List[EquipmentConfig] | None,
        base_mobility: float,
        base_hit: float,
        base_hp: int = 0,
        base_en: int = 0,
        base_armor: int = 0
    ) -> tuple[int, int, int, int, float, float, float, float, float, float, float, List[WeaponSnapshot]]:
        """Apply equipment stat modifiers and collect weapons.

        Args:
            equipments: List of equipment configurations.
            base_mobility: Base mobility value.
            base_hit: Base hit rate value.
            base_hp: Base HP value.
            base_en: Base EN value.
            base_armor: Base armor value.

        Returns:
            Tuple of (hp, en, armor, mobility, hit, dodge, parry, block, precision, crit, weapons).
        """
        weapons = []
        final_hp = base_hp
        final_en = base_en
        final_armor = base_armor
        final_mobility = base_mobility
        final_hit = base_hit
        final_dodge = 0.0
        final_parry = 0.0
        final_block = 0.0
        final_precision = 0.0
        final_crit = 0.0

        if not equipments:
            return final_hp, final_en, final_armor, final_mobility, final_hit, final_dodge, final_parry, final_block, final_precision, final_crit, weapons

        for equip in equipments:
            # Collect weapons
            if equip.type == "WEAPON":
                weapons.append(MechaFactory.create_weapon_snapshot(equip))

            # Apply stat modifiers
            for stat_name, value in equip.stat_modifiers.items():
                if stat_name == "final_max_hp":
                    final_hp += int(value)
                elif stat_name == "final_max_en":
                    final_en += int(value)
                elif stat_name == "final_armor":
                    final_armor += int(value)
                elif stat_name == "final_mobility":
                    final_mobility += int(value)
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

        return final_hp, final_en, final_armor, final_mobility, final_hit, final_dodge, final_parry, final_block, final_precision, final_crit, weapons

    @staticmethod
    def create_mecha_snapshot(
        mecha_conf: MechaConfig,
        pilot_conf: PilotConfig | None = None,
        equipments: List[EquipmentConfig] | None = None,
        weapon_configs: dict | None = None,
        upgrade_level: int = 0
    ) -> MechaSnapshot:
        """Create a MechaSnapshot from configuration with optional enhancements.

        Args:
            mecha_conf: Mecha configuration object.
            pilot_conf: Optional pilot configuration for stat backup.
            equipments: Optional list of equipment to apply modifiers.
            upgrade_level: Upgrade level for stat bonuses (default: 0).

        Returns:
            Fully configured MechaSnapshot ready for combat.
        """
        # Backup pilot stats
        pilot_stats_backup = MechaFactory._backup_pilot_stats(pilot_conf)

        # Apply upgrade bonuses
        hp_bonus = upgrade_level * 200
        armor_bonus = upgrade_level * 20

        # Calculate base stats
        base_hp = mecha_conf.init_hp + hp_bonus
        base_en = mecha_conf.init_en
        base_armor = mecha_conf.init_armor + armor_bonus
        base_mobility = mecha_conf.init_mobility
        base_hit = mecha_conf.init_hit

        # Apply equipment modifiers (returns all modified stats)
        (final_hp, final_en, final_armor, final_mobility, final_hit,
         final_dodge, final_parry, final_block, final_precision, final_crit, weapons) = (
            MechaFactory._apply_equipment_modifiers(
                equipments, base_mobility, base_hit, base_hp, base_en, base_armor
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
            pilot_stats_backup=pilot_stats_backup,
            weapons=weapons,
            skills=[],
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
