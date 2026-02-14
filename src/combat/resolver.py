"""Combat resolution system using round table mechanics.

This module provides the core attack resolution logic, including:
- Round table probability segment calculation
- Damage resolution with armor mitigation
- Hook-based skill system integration
"""

import random
from ..config import Config
from ..models import BattleContext, AttackResult, WeaponType
from ..skills import SkillRegistry
from .calculator import CombatCalculator


class AttackTableResolver:
    """Round table attack resolution system (core mechanic).

    The round table uses priority-based segments:
    1. MISS (affected by weapon proficiency)
    2. DODGE (affected by mecha proficiency, reduced by precision)
    3. PARRY (affected by mecha proficiency, reduced by precision, capped at 50%)
    4. BLOCK (reduced by precision, capped at 80%)
    5. CRIT (squeezed by previous segments)
    6. HIT (remaining space)
    """

    @staticmethod
    def _calculate_all_segments_data(ctx: BattleContext) -> dict:
        """Calculate all round table segment rates.

        This unified method computes MISS, DODGE, PARRY, BLOCK, and CRIT rates
        with all hook modifications applied. Used by both segment display
        and attack resolution.

        Args:
            ctx: Battle context containing attacker and defender information.

        Returns:
            Dictionary with keys: 'miss_rate', 'dodge_rate', 'parry_rate',
            'block_rate', 'crit_rate', 'precision_reduction'.
        """
        attacker = ctx.get_attacker()
        defender = ctx.get_defender()

        # Type safety checks
        assert attacker is not None, "Attacker cannot be None"
        assert defender is not None, "Defender cannot be None"

        # 1. Calculate MISS segment
        base_miss: float = CombatCalculator.calculate_proficiency_miss_penalty(
            attacker.pilot_stats_backup.get('weapon_proficiency', 500)
        )
        miss_rate = SkillRegistry.process_hook("HOOK_PRE_MISS_RATE", base_miss, ctx)

        hit_bonus: float = attacker.final_hit
        hit_bonus = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", hit_bonus, ctx)

        miss_rate = max(0.0, miss_rate - hit_bonus)

        # DODGE segment
        dodge_base: float = CombatCalculator.calculate_proficiency_defense_ratio(
            defender.pilot_stats_backup.get('mecha_proficiency', 2000),
            Config.BASE_DODGE_RATE
        )
        dodge_total: float = dodge_base + defender.final_dodge
        dodge_total = SkillRegistry.process_hook("HOOK_PRE_DODGE_RATE", dodge_total, ctx)
        # 精准削减：使用减法公式（设计文档：每1点精准降低0.66%躲闪率）
        dodge_rate: float = max(0.0, dodge_total - (attacker.final_precision * 0.66))

        # PARRY segment
        parry_base: float = CombatCalculator.calculate_proficiency_defense_ratio(
            defender.pilot_stats_backup.get('mecha_proficiency', 2000),
            Config.BASE_PARRY_RATE
        )
        parry_total: float = parry_base + defender.final_parry
        parry_total = SkillRegistry.process_hook("HOOK_PRE_PARRY_RATE", parry_total, ctx)
        # 精准削减：使用减法公式（设计文档：每1点精准降低0.66%招架率）
        parry_rate: float = max(0.0, min(50.0, parry_total - (attacker.final_precision * 0.66)))

        # BLOCK segment
        block_base: float = CombatCalculator.calculate_proficiency_defense_ratio(
            defender.pilot_stats_backup.get('mecha_proficiency', 2000),
            Config.BASE_BLOCK_RATE
        )
        block_total: float = block_base + defender.final_block
        block_total = SkillRegistry.process_hook("HOOK_PRE_BLOCK_RATE", block_total, ctx)
        # 精准削减：使用减法公式（设计文档：每1点精准降低0.33%格挡率）
        block_rate: float = max(0.0, min(80.0, block_total - (attacker.final_precision * 0.33)))

        # 3. Calculate CRIT segment
        crit_rate: float = Config.BASE_CRIT_RATE + attacker.final_crit
        crit_rate = SkillRegistry.process_hook("HOOK_PRE_CRIT_RATE", crit_rate, ctx)

        return {
            'miss_rate': miss_rate,
            'dodge_rate': dodge_rate,
            'parry_rate': parry_rate,
            'block_rate': block_rate,
            'crit_rate': crit_rate,
        }

    @staticmethod
    def _build_segments_from_data(data: dict) -> dict:
        """Build segment ranges from calculated rates.

        Round table priority: MISS > DODGE > PARRY > BLOCK > CRIT > HIT
        Each segment may be squeezed by previous segments if space runs out.

        Args:
            data: Dictionary containing rate values from _calculate_all_segments_data.

        Returns:
            Dictionary with segment info: name, rate, start, end.
        """
        segments = {}
        current = 0.0

        # Segment types in priority order (highest to lowest)
        segment_types = [
            ('MISS', data['miss_rate']),
            ('DODGE', data['dodge_rate']),
            ('PARRY', data['parry_rate']),
            ('BLOCK', data['block_rate']),
            ('CRIT', data['crit_rate']),
        ]

        for name, rate in segment_types:
            if rate > 0:
                available_space = max(0, 100 - current)
                actual_rate = min(rate, available_space)
                if actual_rate > 0:
                    segments[name] = {
                        'rate': actual_rate,
                        'start': current,
                        'end': current + actual_rate
                    }
                    current += actual_rate

        # HIT (remaining space)
        hit_space = max(0, 100 - current)
        if hit_space > 0:
            segments['HIT'] = {'rate': hit_space, 'start': current, 'end': 100}
            current += hit_space

        segments['total'] = current
        return segments

    @staticmethod
    def calculate_attack_table_segments(ctx: BattleContext) -> dict:
        """Calculate round table segments for display and analysis.

        Public method used by simulator and testing tools to get the
        theoretical probability distribution of attack results.

        Args:
            ctx: Battle context.

        Returns:
            Dictionary containing segment names, rates, and threshold ranges.
        """
        data = AttackTableResolver._calculate_all_segments_data(ctx)
        return AttackTableResolver._build_segments_from_data(data)

    @staticmethod
    def resolve_attack(ctx: BattleContext) -> tuple[AttackResult, int]:
        """Resolve a single attack using round table mechanics.

        Resolution priority (highest to lowest):
        1. MISS - affected by weapon proficiency
        2. DODGE - affected by mecha proficiency, reduced by precision
        3. PARRY - affected by mecha proficiency, reduced by precision, capped at 50%
        4. BLOCK - reduced by precision, capped at 80%
        5. CRIT - squeezed by previous segments
        6. HIT - remaining space

        Algorithm:
        - Generate 0-100 random roll
        - Accumulate segment thresholds by priority
        - Return result based on which segment the roll falls into

        Args:
            ctx: Battle context containing mecha_a, mecha_b, weapon info.

        Returns:
            Tuple of (AttackResult, final_damage_value).
        """
        attacker = ctx.get_attacker()
        defender = ctx.get_defender()
        weapon = ctx.weapon

        # Type safety checks
        assert attacker is not None, "Attacker cannot be None"
        assert defender is not None, "Defender cannot be None"
        assert weapon is not None, "Weapon cannot be None"

        # Generate random roll (uniform to avoid 101-integer bias)
        roll: float = random.uniform(0, 100)
        ctx.roll = roll

        # Calculate segment data
        data = AttackTableResolver._calculate_all_segments_data(ctx)

        # Apply override result hook
        override_result = SkillRegistry.process_hook("HOOK_OVERRIDE_RESULT", None, ctx)

        final_result = None
        if override_result is not None:
            final_result = override_result
        else:
            # Build segments with proper squeezing logic
            segments = AttackTableResolver._build_segments_from_data(data)

            # Check which segment the roll falls into
            if 'MISS' in segments and roll < segments['MISS']['end']:
                final_result = AttackResult.MISS
            elif 'DODGE' in segments and roll < segments['DODGE']['end']:
                final_result = AttackResult.DODGE
            elif 'PARRY' in segments and roll < segments['PARRY']['end']:
                final_result = AttackResult.PARRY
            elif 'BLOCK' in segments and roll < segments['BLOCK']['end']:
                final_result = AttackResult.BLOCK
            elif 'CRIT' in segments and roll < segments['CRIT']['end']:
                final_result = AttackResult.CRIT
            else:
                final_result = AttackResult.HIT

        # Apply post-roll result hook
        final_result = SkillRegistry.process_hook("HOOK_POST_ROLL_RESULT", final_result, ctx)

        # Determine will deltas based on result type
        will_deltas = {
            AttackResult.MISS: (0, 0),
            AttackResult.DODGE: (0, 5),
            AttackResult.PARRY: (0, 15),
            AttackResult.BLOCK: (0, 5),
            AttackResult.HIT: (2, 1),
            AttackResult.CRIT: (5, 0),
        }
        attacker_will_delta, defender_will_delta = will_deltas.get(final_result, (0, 0))

        # Resolve outcome
        result, damage = AttackTableResolver._resolve_damage_outcome(
            ctx, final_result, attacker_will_delta, defender_will_delta
        )

        # Store results in context
        ctx.attack_result = result
        ctx.damage = damage

        # Apply will changes
        if ctx.current_attacker_will_delta != 0:
            attacker.modify_will(ctx.current_attacker_will_delta)
        if ctx.current_defender_will_delta != 0:
            defender.modify_will(ctx.current_defender_will_delta)

        return result, damage

    @staticmethod
    def _calculate_base_damage(ctx: BattleContext) -> int:
        """Calculate base damage for an attack.

        Calculation steps:
        1. Select pilot stat based on weapon type (melee vs shooting)
        2. Base damage = weapon_power + (pilot_stat * 2)
        3. Apply will power modifier

        Args:
            ctx: Battle context.

        Returns:
            Integer base damage value.
        """
        attacker = ctx.get_attacker()
        weapon = ctx.weapon

        # Type safety checks
        assert attacker is not None, "Attacker cannot be None"
        assert weapon is not None, "Weapon cannot be None"

        # Hook: Weapon power modification
        weapon_power = float(weapon.power)
        weapon_power = SkillRegistry.process_hook("HOOK_PRE_WEAPON_POWER", weapon_power, ctx)

        # Weapon power + mecha performance bonus (using dynamic attributes)
        stat_bonus: float = 0.0
        if weapon.weapon_type == WeaponType.MELEE:
            stat_bonus = attacker.pilot_stats_backup.get('stat_melee', 0)
        elif weapon.weapon_type == WeaponType.SHOOTING:
            stat_bonus = attacker.pilot_stats_backup.get('stat_shooting', 0)

        # Hook: Stat bonus modification
        stat_bonus = SkillRegistry.process_hook("HOOK_PRE_STAT_BONUS", stat_bonus, ctx)

        base_damage: float = weapon_power + (stat_bonus * 2)

        # Will modifier
        will_modifier: float = CombatCalculator.calculate_will_damage_modifier(
            attacker.current_will
        )

        # Hook: Will modifier adjustment
        will_modifier = SkillRegistry.process_hook("HOOK_PRE_WILL_MODIFIER", will_modifier, ctx)

        base_damage *= will_modifier

        return int(base_damage)

    @staticmethod
    def _apply_armor_mitigation(damage: int, ctx: BattleContext) -> int:
        """Apply armor damage reduction.

        Uses nonlinear mitigation formula: mitigation% = armor / (armor + K)
        Will power increases effective armor value.

        Args:
            damage: Pre-armor damage value.
            ctx: Battle context.

        Returns:
            Final damage after armor reduction (minimum 0).
        """
        defender = ctx.get_defender()

        # Type safety check
        assert defender is not None, "Defender cannot be None"

        # Hook: Defense level modification
        defense_level = float(defender.final_armor)
        defense_level = SkillRegistry.process_hook("HOOK_PRE_DEFENSE_LEVEL", defense_level, ctx)

        # Hook: Armor value modification
        defense_level = SkillRegistry.process_hook("HOOK_PRE_ARMOR_VALUE", defense_level, ctx)

        # Will modifier for defense
        will_def_modifier: float = CombatCalculator.calculate_will_defense_modifier(
            defender.current_will
        )

        # Armor mitigation
        mitigation_ratio: float = CombatCalculator.calculate_armor_mitigation(
            int(defense_level),
            will_def_modifier
        )

        # Hook: Mitigation ratio adjustment
        mitigation_ratio = SkillRegistry.process_hook("HOOK_PRE_MITIGATION", mitigation_ratio, ctx)

        # Calculate damage taken ratio
        damage_taken_ratio: float = 1.0 - mitigation_ratio

        # Apply mitigation
        final_damage: int = int(damage * damage_taken_ratio)
        return max(0, final_damage)

    @staticmethod
    def _resolve_damage_outcome(
        ctx: BattleContext,
        result_type: AttackResult,
        attacker_will_delta: int = 0,
        defender_will_delta: int = 0,
        damage_mult: float = 1.0
    ) -> tuple[AttackResult, int]:
        """Resolve damage outcome for any attack result type.

        Unified damage resolution method that handles the common flow:
        1. Set will deltas
        2. Calculate base damage
        3. Apply damage multiplier hooks
        4. Apply armor mitigation
        5. Apply result-specific adjustments (block value, crit multiplier)
        6. Apply damage taken hooks

        Args:
            ctx: Battle context.
            result_type: Type of attack result (MISS, DODGE, PARRY, BLOCK, CRIT, HIT).
            attacker_will_delta: Will change for attacker.
            defender_will_delta: Will change for defender.
            damage_mult: Damage multiplier (default 1.0, 2.0 for valor, etc).

        Returns:
            Tuple of (AttackResult, final_damage).
        """
        # Set will deltas
        ctx.current_attacker_will_delta = attacker_will_delta
        ctx.current_defender_will_delta = defender_will_delta

        # MISS, DODGE, PARRY deal no damage
        if result_type in (AttackResult.MISS, AttackResult.DODGE, AttackResult.PARRY):
            return (result_type, 0)

        # Calculate base damage
        base_damage: int = AttackTableResolver._calculate_base_damage(ctx)

        # Hook: Damage multiplier adjustment
        damage_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", damage_mult, ctx)
        damage_before_armor: int = int(base_damage * damage_mult)

        # Apply crit multiplier if CRIT
        if result_type == AttackResult.CRIT:
            crit_mult: float = Config.CRIT_MULTIPLIER
            crit_mult = SkillRegistry.process_hook("HOOK_PRE_CRIT_MULTIPLIER", crit_mult, ctx)
            damage_before_armor = int(damage_before_armor * crit_mult)

        # Apply armor mitigation
        final_damage: int = AttackTableResolver._apply_armor_mitigation(damage_before_armor, ctx)

        # Apply block value if BLOCK
        if result_type == AttackResult.BLOCK:
            defender = ctx.get_defender()
            assert defender is not None, "Defender cannot be None"
            block_value: int = defender.block_reduction
            block_value = SkillRegistry.process_hook("HOOK_PRE_BLOCK_VALUE", block_value, ctx)
            final_damage = max(0, final_damage - block_value)

        # Hook: Damage taken adjustment
        final_damage = SkillRegistry.process_hook("HOOK_ON_DAMAGE_TAKEN", final_damage, ctx)

        return (result_type, final_damage)
