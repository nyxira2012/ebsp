"""
Helper functions for the Presentation System.
"""

from enum import Enum


class HpStatus(str, Enum):
    """
    HP Status Classification for Damage Grading
    """
    LETHAL = "LETHAL"      # HP <= 0: Unit destroyed
    CRITICAL = "CRITICAL"  # HP < 30%: Heavy damage
    MODERATE = "MODERATE"  # 30% <= HP <= 70%: Medium damage
    LIGHT = "LIGHT"        # HP > 70%: Light damage


def calculate_hp_status(hp_after: int, max_hp: int, damage: int = 0) -> HpStatus:
    """
    Calculate the HP status based on remaining HP percentage AND damage ratio.

    同时考虑剩余HP百分比和本次伤害占比，取更严重的级别。

    Args:
        hp_after: HP after the attack
        max_hp: Maximum HP (defender_max_hp)
        damage: Damage dealt in this attack

    Returns:
        HpStatus enum value

    评估逻辑:
        1. LETHAL:   hp_after <= 0
        2. CRITICAL: hp_after < 30% OR 伤害占比 > 50%
        3. MODERATE: 30% <= hp_after <= 70% OR 伤害占比 > 25%
        4. LIGHT:    hp_after > 70% AND 伤害占比 <= 25%
    """
    if max_hp <= 0:
        return HpStatus.LETHAL

    if hp_after <= 0:
        return HpStatus.LETHAL

    # 计算剩余HP比例和本次伤害比例
    hp_ratio = hp_after / max_hp
    damage_ratio = damage / max_hp if max_hp > 0 else 0

    # 优先级：伤害占比高 OR 剩余血量低 → 更严重的级别
    if damage_ratio > 0.5 or hp_ratio < 0.3:
        return HpStatus.CRITICAL
    elif damage_ratio > 0.25 or hp_ratio <= 0.7:
        return HpStatus.MODERATE
    else:
        return HpStatus.LIGHT
