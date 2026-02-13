"""
复杂战斗场景测试
模拟完整的战斗流程，测试多个系统的集成
"""

import pytest
from src.models import Mecha, Pilot, BattleContext, Weapon, WeaponType, Effect, AttackResult
from src.combat.resolver import AttackTableResolver
from src.combat.engine import BattleSimulator
from src.skills import EffectManager, TraitManager, SpiritCommands, SkillRegistry


# ============================================================================
# Fixtures 说明
# ============================================================================
# 所有战斗场景 fixtures 已移至 conftest.py，包括：
# - ace_pilot: 王牌驾驶员
# - normal_pilot: 普通驾驶员
# - gundam_rx78: RX-78高达（进攻型机体，带武器）
# - zaku_ii: 扎古II（平衡型机体，带武器）
# - battlefield: 战场环境上下文

# ============================================================================
# 场景1: 王牌驾驶员 VS 普通驾驶员
# ============================================================================

class TestAceVsNormal:
    """场景1：王牌驾驶员碾压普通驾驶员"""

    def test_ace_advantage_in_hit_rate(self, battlefield):
        """测试王牌驾驶员命中优势"""
        # 应用特性
        TraitManager.apply_traits(battlefield.get_attacker())
        TraitManager.apply_traits(battlefield.get_defender())

        # 计算圆桌段
        segments = AttackTableResolver.calculate_attack_table_segments(battlefield)

        # 高达的MISS应该很低
        miss_rate = segments.get('MISS', {}).get('rate', 0)
        assert miss_rate < 20  # 高熟练度+高命中

        # HIT+CRIT应该占大部分
        hit_rate = segments.get('HIT', {}).get('rate', 0)
        crit_rate = segments.get('CRIT', {}).get('rate', 0)
        assert (hit_rate + crit_rate) > 50

    def test_ace_higher_crit_chance(self, battlefield):
        """测试王牌驾驶员高暴击率"""
        TraitManager.apply_traits(battlefield.get_attacker())

        segments = AttackTableResolver.calculate_attack_table_segments(battlefield)

        crit_rate = segments.get('CRIT', {}).get('rate', 0)
        # 基础暴击15%可能被防御挤压，但应该有显著暴击空间
        assert crit_rate >= 5  # 至少有一些暴击空间

    def test_reversed_situation_disadvantage(self, gundam_rx78, zaku_ii):
        """测试反转情况：扎古攻击高达"""
        battlefield_reversed = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=zaku_ii,
            mecha_b=gundam_rx78,
            weapon=zaku_ii.weapons[0]
        )

        TraitManager.apply_traits(zaku_ii)
        TraitManager.apply_traits(gundam_rx78)

        segments = AttackTableResolver.calculate_attack_table_segments(battlefield_reversed)

        # 扎古的命中率应该较低（高达高闪避）
        hit_rate = segments.get('HIT', {}).get('rate', 0)
        miss_rate = segments.get('MISS', {}).get('rate', 0)

        assert hit_rate < 50 or miss_rate > 20


# ============================================================================
# 场景2: 精神指令战术
# ============================================================================

class TestSpiritTactics:
    """场景2：精神指令战术运用"""

    def test_strike_guarantees_hit(self, gundam_rx78, zaku_ii):
        """测试必中战术"""
        # 使用必中
        SpiritCommands.activate_strike(gundam_rx78)

        # 创建战斗上下文
        ctx = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        # 处理命中钩子
        final_hit = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 25.0, ctx)

        # 必中应该让命中率达到100（或接近）
        assert final_hit >= 90

    def test_valor_double_damage(self, gundam_rx78, zaku_ii):
        """测试热血战术"""
        # 使用热血
        SpiritCommands.activate_valor(gundam_rx78)

        ctx = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        # 处理伤害倍率钩子
        base_damage = 1500
        final_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)

        # 热血应该让伤害x2
        assert final_mult >= 2.0

    def test_focus_improves_both_offense_and_defense(self, gundam_rx78, zaku_ii):
        """测试集中战术（攻防一体）"""
        # 使用集中
        SpiritCommands.activate_focus(gundam_rx78)

        # 检查效果数量（集中生成2个效果）
        assert len(gundam_rx78.effects) >= 2

        # 验证命中提升
        ctx_atk = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        hit_bonus = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 25.0, ctx_atk)
        assert hit_bonus > 25.0

        # 验证回避提升（反转攻防）
        ctx_def = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=zaku_ii,
            mecha_b=gundam_rx78,
            weapon=zaku_ii.weapons[0]
        )

        dodge_bonus = SkillRegistry.process_hook("HOOK_PRE_DODGE_RATE", 15.0, ctx_def)
        assert dodge_bonus > 15.0


# ============================================================================
# 场景3: 状态管理多回合战斗
# ============================================================================

class TestMultiRoundCombat:
    """场景3：多回合战斗状态管理"""

    def test_effect_duration_across_rounds(self, gundam_rx78, zaku_ii):
        """测试效果持续多回合"""
        # 使用热血（持续1回合）
        SpiritCommands.activate_valor(gundam_rx78)

        # 找到热血效果
        valor_effect = None
        for eff in gundam_rx78.effects:
            if "valor" in eff.id.lower():
                valor_effect = eff
                break

        if valor_effect:
            initial_duration = valor_effect.duration

            # 第一回合结束
            EffectManager.tick_effects(gundam_rx78)

            # 持续时间应该减少
            assert valor_effect.duration == initial_duration - 1

            # 第二回合结束
            EffectManager.tick_effects(gundam_rx78)

            # 效果应该被移除
            assert valor_effect not in gundam_rx78.effects

    def test_will_changes_throughout_battle(self, gundam_rx78, zaku_ii):
        """测试气力在战斗中的变化"""
        initial_will_attacker = gundam_rx78.current_will
        initial_will_defender = zaku_ii.current_will

        ctx = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        # 执行攻击（使用resolver）
        result, roll = AttackTableResolver.resolve_attack(ctx)

        # 检查气力变化
        if result is AttackResult.HIT:
            # 攻击命中，攻击者气力上升
            assert gundam_rx78.current_will > initial_will_attacker
            # 防守者气力也会上升（被攻击）
            assert zaku_ii.current_will >= initial_will_defender

    def test_en_consumption_and_management(self, gundam_rx78, zaku_ii):
        """测试EN消耗和管理"""
        initial_en = gundam_rx78.current_en

        # 武器EN消耗
        weapon = gundam_rx78.weapons[0]
        en_cost = weapon.en_cost

        # 检查能否攻击
        assert gundam_rx78.can_attack(weapon)

        # 模拟EN消耗
        gundam_rx78.consume_en(en_cost)

        assert gundam_rx78.current_en == initial_en - en_cost

    def test_low_hp_effects_triggering(self, gundam_rx78, zaku_ii):
        """测试低HP效果触发"""
        # 降低HP到30%以下
        gundam_rx78.current_hp = int(gundam_rx78.final_max_hp * 0.25)

        # 添加低HP触发效果
        low_hp_effect = Effect(
            id="berserk_mode", name="狂暴模式",
            hook="HOOK_PRE_DAMAGE_MULT",
            operation="mul", value=1.5,
            duration=-1, priority=60,
            conditions=[{"type": "hp_threshold", "val": 0.3, "op": "<"}]
        )
        gundam_rx78.effects.append(low_hp_effect)

        ctx = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        # 处理伤害钩子
        damage_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)

        # 低HP应该触发伤害加成
        assert damage_mult >= 1.5


# ============================================================================
# 场景4: 极端条件战斗
# ============================================================================

class TestExtremeCombat:
    """场景4：极端条件下的战斗"""

    def test_zero_en_cannot_attack(self, gundam_rx78, zaku_ii):
        """测试EN不足无法攻击"""
        gundam_rx78.current_en = 0
        weapon = gundam_rx78.weapons[0]

        # 应该无法攻击
        assert not gundam_rx78.can_attack(weapon)

    def test_zero_hp_defeated(self, gundam_rx78, zaku_ii):
        """测试HP归零被击败"""
        zaku_ii.current_hp = 0

        # 应该无法战斗
        assert not zaku_ii.is_alive()

    def test_max_will_bonus(self, gundam_rx78, zaku_ii):
        """测试最大气力加成"""
        from src.config import Config
        gundam_rx78.current_will = Config.WILL_MAX

        # 尝试继续提升（应该被限制）
        gundam_rx78.modify_will(10)

        assert gundam_rx78.current_will == Config.WILL_MAX

    def test_out_of_range_penalty(self, gundam_rx78, zaku_ii):
        """测试射程外惩罚"""
        # 远距离（超出武器射程）
        ctx = BattleContext(
            round_number=1,
            distance=10000,  # 超出光束步枪射程6000
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        # 武器应该有命中惩罚
        weapon = gundam_rx78.weapons[0]
        hit_modifier = weapon.get_hit_modifier_at_distance(ctx.distance)

        assert hit_modifier < 0  # 应该有惩罚


# ============================================================================
# 场景5: 复杂组合战术
# ============================================================================

class TestComplexComboTactics:
    """场景5：复杂组合战术"""

    def test_spirit_combo_strike_plus_valor(self, gundam_rx78, zaku_ii):
        """测试必中+热血组合"""
        # 连续使用精神指令
        SpiritCommands.activate_strike(gundam_rx78)
        SpiritCommands.activate_valor(gundam_rx78)

        ctx = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        # 命中应该极高
        hit_rate = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 25.0, ctx)
        assert hit_rate >= 90

        # 伤害应该翻倍
        damage_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)
        assert damage_mult >= 2.0

    def test_trait_plus_spirit_synergy(self, gundam_rx78, zaku_ii):
        """测试特性+精神指令协同"""
        # 应用特性
        TraitManager.apply_traits(gundam_rx78)

        trait_count = len(gundam_rx78.effects)

        # 使用精神指令
        SpiritCommands.activate_focus(gundam_rx78)

        # 效果应该叠加
        assert len(gundam_rx78.effects) > trait_count

        # 处理命中钩子（应该有特性和精神双重加成）
        ctx = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        final_hit = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 25.0, ctx)
        assert final_hit > 25.0  # 应该有显著提升

    def test_multi_stage_combo(self, gundam_rx78, zaku_ii):
        """测试多阶段组合战术"""
        # 第1回合：使用集中提升攻防
        SpiritCommands.activate_focus(gundam_rx78)

        ctx_r1 = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        # 命中和回避都提升
        hit_r1 = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 25.0, ctx_r1)

        # 回合结束，效果duration-1
        EffectManager.tick_effects(gundam_rx78)

        # 第2回合：使用热血准备致命一击
        SpiritCommands.activate_valor(gundam_rx78)

        ctx_r2 = BattleContext(
            round_number=2,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        # 伤害倍率提升
        damage_r2 = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx_r2)
        assert damage_r2 >= 2.0


# ============================================================================
# 场景6: 完整战斗流程模拟
# ============================================================================

class TestFullBattleSimulation:
    """场景6：完整战斗流程模拟"""

    def test_three_round_battle(self, gundam_rx78, zaku_ii):
        """测试三回合完整战斗"""
        # 初始化
        TraitManager.apply_traits(gundam_rx78)
        TraitManager.apply_traits(zaku_ii)

        # 第1回合：使用必中确保命中
        SpiritCommands.activate_strike(gundam_rx78)

        ctx_r1 = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        result_r1, damage_r1 = AttackTableResolver.resolve_attack(ctx_r1)

        # 处理伤害
        if result_r1 in (AttackResult.HIT, AttackResult.CRIT):
            zaku_ii.take_damage(damage_r1)

        # 第2回合
        ctx_r2 = BattleContext(
            round_number=2,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        result_r2, damage_r2 = AttackTableResolver.resolve_attack(ctx_r2)

        if result_r2 in (AttackResult.HIT, AttackResult.CRIT):
            zaku_ii.take_damage(damage_r2)

        # 第3回合：使用热血
        SpiritCommands.activate_valor(gundam_rx78)

        ctx_r3 = BattleContext(
            round_number=3,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        result_r3, damage_r3 = AttackTableResolver.resolve_attack(ctx_r3)

        if result_r3 in (AttackResult.HIT, AttackResult.CRIT):
            zaku_ii.take_damage(damage_r3)

        # 第1回合使用了必中，至少应该命中一次
        assert zaku_ii.current_hp < zaku_ii.final_max_hp

    def test_clutch_final_attack(self, gundam_rx78, zaku_ii):
        """测试绝境反击"""
        # 高达濒死
        gundam_rx78.current_hp = int(gundam_rx78.final_max_hp * 0.1)
        gundam_rx78.current_will = 150  # 高气力

        # 添加低HP加成效果
        clutch_effect = Effect(
            id="clutch_berserk", name="绝境爆发",
            hook="HOOK_PRE_DAMAGE_MULT",
            operation="mul", value=2.0,
            duration=-1, priority=60,
            conditions=[{"type": "hp_threshold", "val": 0.2, "op": "<"}]
        )
        gundam_rx78.effects.append(clutch_effect)

        # 使用热血
        SpiritCommands.activate_valor(gundam_rx78)

        ctx = BattleContext(
            round_number=1,
            distance=3000,
            terrain=None,
            mecha_a=gundam_rx78,
            mecha_b=zaku_ii,
            weapon=gundam_rx78.weapons[0]
        )

        # 伤害应该极高（低HPx2 + 热血x2 = x4）
        damage_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)
        assert damage_mult >= 4.0
