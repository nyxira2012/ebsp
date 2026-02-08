import random
from ..config import Config
from ..models import BattleContext, AttackResult, WeaponType
from ..skills import SkillRegistry
from .calculator import CombatCalculator


class AttackTableResolver:
    """圆桌判定系统 (核心难点)"""
    
    @staticmethod
    def resolve_attack(ctx: BattleContext) -> tuple[AttackResult, int]:
        """使用圆桌判定法计算单次攻击的结果和伤害。

        圆桌判定优先级顺序 (从高到低):
        1. Miss (未命中) - 受武器熟练度影响
        2. Dodge (躲闪) - 受机体熟练度影响,被精准削减
        3. Parry (招架) - 受机体熟练度影响,被精准削减,上限50%
        4. Block (格挡) - 被精准削减,上限80%
        5. Crit (暴击) - 占据剩余空间的暴击率比例
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
        
        # 生成 0-100 随机数
        roll: int = random.randint(0, 100)
        ctx.roll = roll
        
        # === 1. 计算基础概率 (Base Rates) ===
        # 基础未命中率
        base_miss: float = CombatCalculator.calculate_proficiency_miss_penalty(
            attacker.pilot.weapon_proficiency
        )
        # 命中修正 (Hit Rate Bonus)
        hit_bonus: float = attacker.hit_rate
        
        # HOOK: 命中率修正 (PRE_HIT_RATE)
        # 这里的 value 传递的是 hit_bonus (命中加成)，或者我们可以传递 "最终期望命中率"
        # 为了支持 "必中" (100% 命中), 我们定义: 如果 Hook 返回 >= 100, 则 Miss/Dodge/Parry 统统失效
        hit_bonus = SkillRegistry.process_hook("PRE_HIT_RATE", hit_bonus, ctx)

        if hit_bonus >= 100.0:
            # 必中生效: 强制命中 (Miss=0, Dodge=0, Parry=0)
            miss_rate = 0.0
            dodge_rate = 0.0
            parry_rate = 0.0
            block_rate = 0.0 # 必中通常也能被格挡? SRW里必中不破分身/格挡，只破回避。
            # 直感/必中通常无法无视格挡，但可以无视分身(Dodge)。
            # 这里简化: 必中 = 不会 Miss 和 Dodge
        else:
            miss_rate = max(0.0, base_miss - hit_bonus)

            # === 2. 计算防御概率 (受精准削减) ===
            precision_reduction: float = CombatCalculator.calculate_precision_reduction(attacker.precision)
            
            # HOOK: 精准修正
            precision_reduction = SkillRegistry.process_hook("PRE_PRECISION", precision_reduction, ctx)

            # 躲闪率 (Dodge)
            dodge_base: float = CombatCalculator.calculate_proficiency_defense_ratio(
                defender.pilot.mecha_proficiency,
                Config.BASE_DODGE_RATE
            )
            # HOOK: 回避率修正 (PRE_EVADE_RATE)
            dodge_base = SkillRegistry.process_hook("PRE_EVADE_RATE", dodge_base, ctx)
            
            dodge_rate: float = dodge_base * (1 - precision_reduction)
            dodge_rate = max(0.0, dodge_rate)
            
            # 招架率 (Parry)
            parry_base: float = CombatCalculator.calculate_proficiency_defense_ratio(
                defender.pilot.mecha_proficiency,
                Config.BASE_PARRY_RATE
            )
            parry_rate: float = parry_base * (1 - precision_reduction)
            parry_rate = max(0.0, min(50.0, parry_rate))
            
            # 格挡率 (Block)
            block_rate: float = defender.block_rate * (1 - precision_reduction)
            block_rate = max(0.0, min(80.0, block_rate))

        # === 3. 暴击率 ===
        crit_rate: float = min(100.0, attacker.crit_rate)
        # HOOK: 暴击率修正
        crit_rate = SkillRegistry.process_hook("PRE_CRIT_RATE", crit_rate, ctx)
        
        # === 4. 构建圆桌 (优先级排列) ===
        current_threshold: float = 0.0
        
        # Miss
        current_threshold += miss_rate
        if roll <= current_threshold:
            return AttackTableResolver._resolve_miss(ctx)
        
        # Dodge
        current_threshold += dodge_rate
        if roll <= current_threshold:
            return AttackTableResolver._resolve_dodge(ctx)
        
        # Parry
        current_threshold += parry_base * (1 - precision_reduction) # Note: reused dodge logic style
        if roll <= current_threshold:
            return AttackTableResolver._resolve_parry(ctx)
        
        # Block
        current_threshold += block_rate
        if roll <= current_threshold:
            return AttackTableResolver._resolve_block(ctx)
        
        # 剩余空间分配给 Crit 和 Hit
        remaining: float = 100.0 - current_threshold
        
        # Crit 占用剩余空间的一部分
        crit_threshold: float = current_threshold + (remaining * crit_rate / 100.0)
        if roll <= crit_threshold:
            return AttackTableResolver._resolve_crit(ctx)
        
        # Hit 占据剩余全部
        return AttackTableResolver._resolve_hit(ctx)
    
    @staticmethod
    def _calculate_base_damage(ctx: BattleContext) -> int:
        """计算攻击的基础伤害。

        计算步骤:
        1. 根据武器类型选择驾驶员的对应属性 (格斗用格斗值,射击用射击值)
        2. 基础伤害 = 武器威力 + (驾驶员属性 * 2)
        3. 应用气力修正系数
        4. 应用技能钩子的伤害倍率

        Args:
            ctx: 战场上下文

        Returns:
            int: 计算后的基础伤害值 (取整)
        """
        attacker = ctx.attacker
        weapon = ctx.weapon

        # 武器威力 + 机体性能修正 (使用动态属性)
        stat_bonus: int = 0
        if weapon.weapon_type == WeaponType.MELEE:
            stat_bonus = int(attacker.pilot.get_effective_stat('stat_melee'))
        elif weapon.weapon_type in [WeaponType.RIFLE, WeaponType.HEAVY]:
            stat_bonus = int(attacker.pilot.get_effective_stat('stat_shooting'))

        base_damage: float = weapon.power + (stat_bonus * 2)  # 简化公式

        # 气力修正
        will_modifier: float = CombatCalculator.calculate_will_damage_modifier(attacker.current_will)
        base_damage *= will_modifier

        # HOOK: 伤害计算 (PRE_DAMAGE_CALC)
        # 替换原有的 hooks.get('HOOK_DMG_MUL')
        base_damage = SkillRegistry.process_hook("PRE_DAMAGE_CALC", base_damage, ctx)

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
        defender = ctx.defender

        # 气力对防御的修正
        will_def_modifier: float = CombatCalculator.calculate_will_defense_modifier(defender.current_will)

        # 护甲减伤
        mitigation_ratio: float = CombatCalculator.calculate_armor_mitigation(
            defender.defense_level,
            will_def_modifier
        )

        # HOOK: 伤减计算 (PRE_MITIGATION) -> 注意这里是减伤后的剩余比例(受到伤害比例)还是减伤比例?
        # 原逻辑: mitigation_ratio 是减伤比例 (0.3 = 减免30%)
        # 铁壁逻辑: 受到 1/4 伤害 -> 意味着最终 damage_taken_ratio = 0.25
        # 所以我们需要转换一下概念。
        # 现在的 mitigation_ratio 是 "被抵消的部分"。 (1 - mitigation_ratio) 是 "受到的部分"。
        
        damage_taken_ratio: float = 1.0 - mitigation_ratio
        
        # HOOK: 修正受伤害比例
        damage_taken_ratio = SkillRegistry.process_hook("PRE_MITIGATION", damage_taken_ratio, ctx)
        
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
        damage_after_armor: int = AttackTableResolver._apply_armor_mitigation(base_damage, ctx)
        final_damage: int = max(0, damage_after_armor - ctx.defender.block_value)

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
        final_damage: int = AttackTableResolver._apply_armor_mitigation(base_damage, ctx)

        return (AttackResult.HIT, final_damage)
    
    @staticmethod
    def _resolve_crit(ctx: BattleContext) -> tuple[AttackResult, int]:
        """处理暴击结果。

        暴击伤害 = 基础伤害 * 暴击倍率 (1.5倍)
        攻击方获得 5 点气力。

        Args:
            ctx: 战场上下文

        Returns:
            tuple[AttackResult, int]: (CRIT, 暴击伤害)
        """
        # 气力变动: 攻击方 +5
        ctx.attacker_will_delta = 5

        base_damage: int = AttackTableResolver._calculate_base_damage(ctx)
        # 暴击倍率
        crit_damage: int = int(base_damage * Config.CRIT_MULTIPLIER)
        final_damage: int = AttackTableResolver._apply_armor_mitigation(crit_damage, ctx)

        return (AttackResult.CRIT, final_damage)
