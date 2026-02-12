import random
from ..config import Config
from ..models import BattleContext, AttackResult, WeaponType
from ..skills import SkillRegistry
from .calculator import CombatCalculator


class AttackTableResolver:
    """圆桌判定系统 (核心难点)"""

    @staticmethod
    def _calculate_segments(ctx: BattleContext) -> dict:
        """计算圆桌判定的各个段 (内部方法)

        计算并返回圆桌判定中各个段的阈值范围。

        Args:
            ctx: 战场上下文

        Returns:
            dict: 包含各个段的名称、阈值范围的字典
        """
        attacker = ctx.attacker
        defender = ctx.defender

        # === 1. 计算 MISS 段 ===
        base_miss: float = CombatCalculator.calculate_proficiency_miss_penalty(
            attacker.pilot.weapon_proficiency
        )
        miss_rate = SkillRegistry.process_hook("HOOK_PRE_MISS_RATE", base_miss, ctx)

        hit_bonus: float = attacker.hit_rate
        hit_bonus = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", hit_bonus, ctx)

        miss_rate = max(0.0, miss_rate - hit_bonus)

        # === 2. 计算防御段 ===
        precision_reduction: float = CombatCalculator.calculate_precision_reduction(attacker.precision)
        precision_reduction = SkillRegistry.process_hook("HOOK_PRE_PRECISION", precision_reduction, ctx)

        # DODGE
        dodge_base: float = CombatCalculator.calculate_proficiency_defense_ratio(
            defender.pilot.mecha_proficiency,
            Config.BASE_DODGE_RATE
        )
        dodge_total: float = dodge_base + defender.dodge_rate
        dodge_total = SkillRegistry.process_hook("HOOK_PRE_DODGE_RATE", dodge_total, ctx)
        dodge_rate: float = max(0.0, dodge_total * (1 - precision_reduction))

        # PARRY
        parry_base: float = CombatCalculator.calculate_proficiency_defense_ratio(
            defender.pilot.mecha_proficiency,
            Config.BASE_PARRY_RATE
        )
        parry_total: float = parry_base + defender.parry_rate
        parry_total = SkillRegistry.process_hook("HOOK_PRE_PARRY_RATE", parry_total, ctx)
        parry_rate: float = max(0.0, min(50.0, parry_total * (1 - precision_reduction)))

        # BLOCK
        block_base: float = Config.BASE_BLOCK_RATE + defender.block_rate
        block_base = SkillRegistry.process_hook("HOOK_PRE_BLOCK_RATE", block_base, ctx)
        block_rate: float = max(0.0, min(80.0, block_base * (1 - precision_reduction)))

        # === 3. 计算 CRIT 段 ===
        crit_rate: float = Config.BASE_CRIT_RATE + attacker.crit_rate
        crit_rate = SkillRegistry.process_hook("HOOK_PRE_CRIT_RATE", crit_rate, ctx)

        # === 4. 构建圆桌段 ===
        segments = {}
        current = 0.0

        if miss_rate > 0:
            segments['MISS'] = {'rate': miss_rate, 'start': current, 'end': current + miss_rate}
            current += miss_rate

        if dodge_rate > 0:
            segments['DODGE'] = {'rate': dodge_rate, 'start': current, 'end': current + dodge_rate}
            current += dodge_rate

        if parry_rate > 0:
            segments['PARRY'] = {'rate': parry_rate, 'start': current, 'end': current + parry_rate}
            current += parry_rate

        if block_rate > 0:
            segments['BLOCK'] = {'rate': block_rate, 'start': current, 'end': current + block_rate}
            current += block_rate

        if crit_rate > 0:
            # CRIT 可能被前面的段挤压
            available_space = max(0, 100 - current)
            actual_crit_rate = min(crit_rate, available_space)
            segments['CRIT'] = {'rate': actual_crit_rate, 'start': current, 'end': current + actual_crit_rate}
            current += actual_crit_rate

        # HIT (剩余空间)
        hit_space = max(0, 100 - current)
        if hit_space > 0:
            segments['HIT'] = {'rate': hit_space, 'start': current, 'end': 100}
            current += hit_space

        segments['total'] = current

        return segments

    @staticmethod
    def calculate_attack_table_segments(ctx: BattleContext) -> dict:
        """计算圆桌判定的各个段 (公共方法)

        用于显示和分析圆桌判定的组成，返回各个段的理论值。
        模拟器和测试工具使用此方法来获取圆桌判定的理论分布。

        Args:
            ctx: 战场上下文

        Returns:
            dict: 包含各个段的名称、阈值范围的字典
        """
        return AttackTableResolver._calculate_segments(ctx)

    @staticmethod
    def resolve_attack(ctx: BattleContext) -> tuple[AttackResult, int]:
        """使用圆桌判定法计算单次攻击的结果和伤害。

        圆桌判定优先级顺序 (从高到低):
        1. Miss (未命中) - 受武器熟练度影响
        2. Dodge (躲闪) - 受机体熟练度影响,被精准削减
        3. Parry (招架) - 受机体熟练度影响,被精准削减,上限50%
        4. Block (格挡) - 被精准削减,上限80%
        5. Crit (暴击) - 按优先级顺序被前面的段挤压
        6. Hit (普通命中) - 剩余全部空间

        算法思路:
        - 生成 0-100 随机数
        - 按优先级顺序累加各区间阈值
        - 根据随机数落入的区间返回对应结果

        Args:
            ctx: 战场上下文,包含攻击方、防御方、武器等信息

        Returns:
            tuple[AttackResult, int]: (攻击判定结果, 最终伤害值)
        """
        attacker = ctx.attacker
        defender = ctx.defender
        weapon = ctx.weapon
        
        # 生成 0-100 随机数 (使用 uniform 避免 randint 产生的 101 个整数导致的 1% 偏移)
        roll: float = random.uniform(0, 100)
        ctx.roll = roll
        
        # === 1. 计算基础概率 (Base Rates) ===
        # 基础未命中率
        base_miss: float = CombatCalculator.calculate_proficiency_miss_penalty(
            attacker.pilot.weapon_proficiency
        )
        # HOOK: 未命中率修正
        miss_rate = SkillRegistry.process_hook("HOOK_PRE_MISS_RATE", base_miss, ctx)
        
        # 命中修正 (Hit Rate Bonus)
        hit_bonus: float = attacker.hit_rate
        
        # HOOK: 命中率修正 (PRE_HIT_RATE)
        hit_bonus = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", hit_bonus, ctx)

        # 命中加成首先抵消 Miss（必中只影响MISS段，不影响防御判定）
        miss_rate = max(0.0, miss_rate - hit_bonus)

        # === 2. 计算防御概率 (受精准削减) ===
        precision_reduction: float = CombatCalculator.calculate_precision_reduction(attacker.precision)
        precision_reduction = SkillRegistry.process_hook("HOOK_PRE_PRECISION", precision_reduction, ctx)

        # 躲闪率 (Dodge)
        # 计算基础值（受机体熟练度影响）
        dodge_base: float = CombatCalculator.calculate_proficiency_defense_ratio(
            defender.pilot.mecha_proficiency,
            Config.BASE_DODGE_RATE
        )
        # 加上机体提供的加成值
        dodge_total: float = dodge_base + defender.dodge_rate
        dodge_total = SkillRegistry.process_hook("HOOK_PRE_DODGE_RATE", dodge_total, ctx)
        dodge_rate: float = max(0.0, dodge_total * (1 - precision_reduction))

        # 招架率 (Parry)
        # 计算基础值（受机体熟练度影响）
        parry_base: float = CombatCalculator.calculate_proficiency_defense_ratio(
            defender.pilot.mecha_proficiency,
            Config.BASE_PARRY_RATE
        )
        # 加上机体提供的加成值
        parry_total: float = parry_base + defender.parry_rate
        parry_total = SkillRegistry.process_hook("HOOK_PRE_PARRY_RATE", parry_total, ctx)
        parry_rate: float = max(0.0, min(50.0, parry_total * (1 - precision_reduction)))

        # 格挡率 (Block)
        # 基础值 + 机体提供的加成值
        block_base: float = Config.BASE_BLOCK_RATE + defender.block_rate
        block_base = SkillRegistry.process_hook("HOOK_PRE_BLOCK_RATE", block_base, ctx)
        block_rate: float = max(0.0, min(80.0, block_base * (1 - precision_reduction)))

        # === 3. 暴击率 (Crit) ===
        # 暴击率按优先级顺序被前面的段挤压，不占绝对宽度
        # 基础值 + 攻击方提供的加成值
        crit_rate: float = Config.BASE_CRIT_RATE + attacker.crit_rate
        crit_rate = SkillRegistry.process_hook("HOOK_PRE_CRIT_RATE", crit_rate, ctx)
        
        # === 4. 圆桌判定 (Standard One-Roll Table) ===
        override_result = SkillRegistry.process_hook("HOOK_OVERRIDE_RESULT", None, ctx)
        
        final_result = None
        if override_result is not None:
             final_result = override_result
        else:
            # 优先级顺序：Miss -> Dodge -> Parry -> Block -> Crit -> Hit
            current_threshold: float = 0.0
            
            if roll < (current_threshold := current_threshold + miss_rate):
                final_result = AttackResult.MISS
            elif roll < (current_threshold := current_threshold + dodge_rate):
                final_result = AttackResult.DODGE
            elif roll < (current_threshold := current_threshold + parry_rate):
                final_result = AttackResult.PARRY
            elif roll < (current_threshold := current_threshold + block_rate):
                final_result = AttackResult.BLOCK
            elif roll < (current_threshold := current_threshold + crit_rate):
                final_result = AttackResult.CRIT
            else:
                final_result = AttackResult.HIT

        # HOOK: 判定后修正 (POST_ROLL_RESULT)
        # 允许把 Hit 变成 Dodge (分身)，或者 Parry 变成 Hit (直击)
        final_result = SkillRegistry.process_hook("HOOK_POST_ROLL_RESULT", final_result, ctx)

        # === 5. 执行结果逻辑 ===
        result, damage = (AttackResult.MISS, 0)
        if final_result == AttackResult.MISS:
            result, damage = AttackTableResolver._resolve_miss(ctx)
        elif final_result == AttackResult.DODGE:
            result, damage = AttackTableResolver._resolve_dodge(ctx)
        elif final_result == AttackResult.PARRY:
            result, damage = AttackTableResolver._resolve_parry(ctx)
        elif final_result == AttackResult.BLOCK:
            result, damage = AttackTableResolver._resolve_block(ctx)
        elif final_result == AttackResult.CRIT:
            result, damage = AttackTableResolver._resolve_crit(ctx)
        else: # HIT
            result, damage = AttackTableResolver._resolve_hit(ctx)

        # 存储结果到 context
        ctx.attack_result = result
        ctx.damage = damage

        # 应用气力变化
        if ctx.attacker_will_delta != 0:
            attacker.modify_will(ctx.attacker_will_delta)
        if ctx.defender_will_delta != 0:
            defender.modify_will(ctx.defender_will_delta)

        return result, damage
    
    
    @staticmethod
    def _calculate_base_damage(ctx: BattleContext) -> int:
        """计算攻击的基础伤害。

        计算步骤:
        1. 根据武器类型选择驾驶员的对应属性 (格斗用格斗值,射击用射击值)
        2. 基础伤害 = 修正后武器威力 + (修正后驾驶员属性 * 2)
        3. 应用修正后气力修正系数

        Args:
            ctx: 战场上下文

        Returns:
            int: 计算后的基础伤害值 (取整)
        """
        attacker = ctx.attacker
        weapon = ctx.weapon

        # HOOK: 武器威力修正
        weapon_power = float(weapon.power)
        weapon_power = SkillRegistry.process_hook("HOOK_PRE_WEAPON_POWER", weapon_power, ctx)

        # 武器威力 + 机体性能修正 (使用动态属性)
        stat_bonus: float = 0.0
        if weapon.weapon_type == WeaponType.MELEE:
            stat_bonus = attacker.pilot.get_effective_stat('stat_melee')
        elif weapon.weapon_type == WeaponType.SHOOTING:
            stat_bonus = attacker.pilot.get_effective_stat('stat_shooting')
            
        # HOOK: 属性加成修正
        stat_bonus = SkillRegistry.process_hook("HOOK_PRE_STAT_BONUS", stat_bonus, ctx)

        base_damage: float = weapon_power + (stat_bonus * 2)  # 简化公式

        # 气力修正
        will_modifier: float = CombatCalculator.calculate_will_damage_modifier(attacker.current_will)
        
        # HOOK: 气力系数修正
        will_modifier = SkillRegistry.process_hook("HOOK_PRE_WILL_MODIFIER", will_modifier, ctx)
        
        base_damage *= will_modifier

        return int(base_damage)
    
    @staticmethod
    def _apply_armor_mitigation(damage: int, ctx: BattleContext) -> int:
        """应用护甲减伤效果。

        使用非线性减伤公式: 减伤比例 = 护甲 / (护甲 + K)
        气力会提升有效护甲值,技能钩子可以调整减伤比例。

        Args:
            damage: 应用护甲前的原始伤害
            ctx: 战场上下文

        Returns:
            int: 护甲减伤后的最终伤害 (最小为 0)
        """
        attacker = ctx.attacker
        defender = ctx.defender

        # HOOK: 防御等级修正
        defense_level = float(defender.defense_level)
        defense_level = SkillRegistry.process_hook("HOOK_PRE_DEFENSE_LEVEL", defense_level, ctx)

        # HOOK: 护甲值修正 (装甲强化、合金装甲等)
        defense_level = SkillRegistry.process_hook("HOOK_PRE_ARMOR_VALUE", defense_level, ctx)

        # 气力对防御的修正
        will_def_modifier: float = CombatCalculator.calculate_will_defense_modifier(defender.current_will)

        # 护甲减伤
        mitigation_ratio: float = CombatCalculator.calculate_armor_mitigation(
            int(defense_level),
            will_def_modifier
        )
        
        # HOOK: 减伤比例修正 (HOOK_PRE_MITIGATION)
        # 注意：这里是对 "减伤比例" 的修正。例如 0.3 -> 0.4 (减免更多)
        mitigation_ratio = SkillRegistry.process_hook("HOOK_PRE_MITIGATION", mitigation_ratio, ctx)
        
        # 计算受到的伤害比例
        damage_taken_ratio: float = 1.0 - mitigation_ratio
        
        # 应用减伤
        final_damage: int = int(damage * damage_taken_ratio)
        return max(0, final_damage)
    
    @staticmethod
    def _resolve_miss(ctx: BattleContext) -> tuple[AttackResult, int]:
        """处理未命中结果。

        Args:
            ctx: 战场上下文

        Returns:
            tuple[AttackResult, int]: (MISS, 0)
        """
        return (AttackResult.MISS, 0)
    
    @staticmethod
    def _resolve_dodge(ctx: BattleContext) -> tuple[AttackResult, int]:
        """处理躲闪结果。

        躲闪成功会给防御方增加 5 点气力。

        Args:
            ctx: 战场上下文

        Returns:
            tuple[AttackResult, int]: (DODGE, 0)
        """
        # 气力变动: 防御方 +5
        ctx.defender_will_delta = 5
        return (AttackResult.DODGE, 0)
    
    @staticmethod
    def _resolve_parry(ctx: BattleContext) -> tuple[AttackResult, int]:
        """处理招架结果。

        招架成功会给防御方增加 15 点气力 (高于躲闪)。

        Args:
            ctx: 战场上下文

        Returns:
            tuple[AttackResult, int]: (PARRY, 0)
        """
        # 气力变动: 防御方 +15
        ctx.defender_will_delta = 15
        return (AttackResult.PARRY, 0)
    
    @staticmethod
    def _resolve_block(ctx: BattleContext) -> tuple[AttackResult, int]:
        """处理格挡结果。

        格挡会减少伤害: 先计算基础伤害和护甲减伤,再减去格挡值。
        防御方获得 5 点气力。

        Args:
            ctx: 战场上下文

        Returns:
            tuple[AttackResult, int]: (BLOCK, 最终伤害)
        """
        # 气力变动: 防御方 +5
        ctx.defender_will_delta = 5

        # 计算伤害并减去格挡值
        base_damage: int = AttackTableResolver._calculate_base_damage(ctx)
        
        # HOOK: 伤害倍率修正 (HOOK_PRE_DAMAGE_MULT)
        damage_mult: float = 1.0
        damage_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", damage_mult, ctx)
        damage_before_armor: int = int(base_damage * damage_mult)
        
        damage_after_armor: int = AttackTableResolver._apply_armor_mitigation(damage_before_armor, ctx)
        
        # HOOK: 格挡值修正 (HOOK_PRE_BLOCK_VALUE)
        block_value: int = ctx.defender.block_value
        block_value = SkillRegistry.process_hook("HOOK_PRE_BLOCK_VALUE", block_value, ctx)
        
        final_damage: int = max(0, damage_after_armor - block_value)
        
        # HOOK: 伤害抵消 (HOOK_ON_DAMAGE_TAKEN)
        final_damage = SkillRegistry.process_hook("HOOK_ON_DAMAGE_TAKEN", final_damage, ctx)

        return (AttackResult.BLOCK, final_damage)
    
    @staticmethod
    def _resolve_hit(ctx: BattleContext) -> tuple[AttackResult, int]:
        """处理普通命中结果。

        双方都会获得气力: 攻击方 +2, 防御方 +1。

        Args:
            ctx: 战场上下文

        Returns:
            tuple[AttackResult, int]: (HIT, 最终伤害)
        """
        # 气力变动: 攻击方 +2, 防御方 +1
        ctx.attacker_will_delta = 2
        ctx.defender_will_delta = 1

        base_damage: int = AttackTableResolver._calculate_base_damage(ctx)
        
        # HOOK: 伤害倍率修正 (HOOK_PRE_DAMAGE_MULT)
        # 例如：热血 (2.0)
        damage_mult: float = 1.0
        damage_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", damage_mult, ctx)
        
        damage_before_armor: int = int(base_damage * damage_mult)
        
        final_damage: int = AttackTableResolver._apply_armor_mitigation(damage_before_armor, ctx)
        
        # HOOK: 伤害抵消 (HOOK_ON_DAMAGE_TAKEN)
        # 例如：I力场 (抵消伤害 -> 变成0)
        final_damage = SkillRegistry.process_hook("HOOK_ON_DAMAGE_TAKEN", final_damage, ctx)

        return (AttackResult.HIT, final_damage)
    
    @staticmethod
    def _resolve_crit(ctx: BattleContext) -> tuple[AttackResult, int]:
        """处理暴击结果。

        暴击伤害 = 基础伤害 * 伤害倍率 * 暴击倍率
        攻击方获得 5 点气力。

        Args:
            ctx: 战场上下文

        Returns:
            tuple[AttackResult, int]: (CRIT, 暴击伤害)
        """
        # 气力变动: 攻击方 +5
        ctx.attacker_will_delta = 5

        base_damage: int = AttackTableResolver._calculate_base_damage(ctx)

        # HOOK: 伤害倍率修正 (HOOK_PRE_DAMAGE_MULT)
        damage_mult: float = 1.0
        damage_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", damage_mult, ctx)
        
        # HOOK: 暴击倍率修正 (HOOK_PRE_CRIT_MULTIPLIER)
        crit_mult: float = Config.CRIT_MULTIPLIER
        crit_mult = SkillRegistry.process_hook("HOOK_PRE_CRIT_MULTIPLIER", crit_mult, ctx)

        damage_before_armor: int = int(base_damage * damage_mult * crit_mult)
        
        final_damage: int = AttackTableResolver._apply_armor_mitigation(damage_before_armor, ctx)
        
        # HOOK: 伤害抵消 (HOOK_ON_DAMAGE_TAKEN)
        final_damage = SkillRegistry.process_hook("HOOK_ON_DAMAGE_TAKEN", final_damage, ctx)

        return (AttackResult.CRIT, final_damage)
