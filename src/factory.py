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
        base_hit: float
    ) -> tuple[float, float, List[WeaponSnapshot]]:
        """Apply equipment stat modifiers and collect weapons.

        Args:
            equipments: List of equipment configurations.
            base_mobility: Base mobility value.
            base_hit: Base hit rate value.

        Returns:
            Tuple of (modified mobility, modified hit rate, weapon list).
        """
        weapons = []
        final_mobility = base_mobility
        final_hit = base_hit

        if not equipments:
            return final_mobility, final_hit, weapons

        for equip in equipments:
            # Collect weapons
            if equip.type == "WEAPON":
                weapons.append(MechaFactory.create_weapon_snapshot(equip))

            # Apply stat modifiers
            for stat_name, value in equip.stat_modifiers.items():
                if stat_name == "mobility":
                    final_mobility += int(value)
                elif stat_name == "hit_rate":
                    final_hit += value

        return final_mobility, final_hit, weapons

    @staticmethod
    def create_mecha_snapshot(
        mecha_conf: MechaConfig,
        pilot_conf: PilotConfig | None = None,
        equipments: List[EquipmentConfig] | None = None,
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
        final_hp = mecha_conf.init_hp + hp_bonus
        final_armor = mecha_conf.init_armor + armor_bonus
        final_mobility = mecha_conf.init_mobility
        final_hit = mecha_conf.init_hit

        # Apply equipment modifiers
        final_mobility, final_hit, weapons = MechaFactory._apply_equipment_modifiers(
            equipments, final_mobility, final_hit
        )

        # Construct snapshot
        return MechaSnapshot(
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
