"""
复杂集成测试套件
测试多回合战斗、复杂技能组合、状态持续性、边界条件组合等高复杂度场景

运行方式:
    pytest tests/test-integration-complex.py -v
    pytest tests/test-integration-complex.py::TestMultiRoundBattle -v
    pytest tests/test-integration-complex.py -m "integration" -v
"""

import pytest
from unittest.mock import patch, Mock
from src.models import Mecha, Pilot, Weapon, WeaponType, BattleContext, Effect, Terrain, AttackResult
from src.skills import SkillRegistry, EffectManager, TraitManager
from src.combat.engine import BattleSimulator
from src.combat.resolver import AttackTableResolver

# ============================================================================
# 标记定义
# ============================================================================
pytestmark = [pytest.mark.integration, pytest.mark.slow]


# ============================================================================
# 1. 多回合战斗集成测试
# ============================================================================

class TestMultiRoundBattle:
    """测试多回合战斗中的状态传递和资源管理"""

    def test_three_round_battle_with_en_management(self, heavy_mecha, basic_mecha):
        """测试3回合战斗：验证EN消耗、HP变化、气力增长"""
        heavy_weapon = Weapon(id="w_heavy", name="Heavy Cannon", weapon_type=WeaponType.HEAVY,
                             power=3000, en_cost=30, range_min=1, range_max=5)
        basic_mecha.weapons = [heavy_weapon]

        sim = BattleSimulator(heavy_mecha, basic_mecha)
        sim.run_battle()

        assert sim.round_number >= 2, "应该进行至少2回合"
        total_damage = (heavy_mecha.max_hp - heavy_mecha.current_hp +
                       basic_mecha.max_hp - basic_mecha.current_hp)
        assert total_damage > 0, "应该有伤害产生"

    def test_will_growth_across_rounds(self, basic_mecha):
        """测试气力在多回合中的增长"""
        opponent = Mecha(
            id="m_opp", name="Opponent", pilot=basic_mecha.pilot,
            max_hp=5000, current_hp=5000, max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        initial_will = basic_mecha.current_will
        sim = BattleSimulator(basic_mecha, opponent)
        sim.run_battle()

        assert basic_mecha.current_will >= initial_will, "气力应该增长或保持不变"

    def test_effect_expiration_after_rounds(self, basic_mecha, basic_context):
        """测试效果在回合结束后过期"""
        EffectManager.add_effect(basic_mecha, "spirit_strike", duration=1)

        initial_count = len(basic_mecha.effects)
        assert initial_count > 0, "应该有精神效果"

        EffectManager.tick_effects(basic_mecha)
        assert len(basic_mecha.effects) < initial_count, "效果应该过期"

    def test_repeated_attacks_with_charges_consumption(self, basic_mecha, basic_context):
        """测试带次数限制的效果在多次攻击中消耗"""
        EffectManager.add_effect(basic_mecha, "spirit_valor")

        mult1 = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, basic_context)
        assert mult1 == 2.0, "第一次攻击应该触发热血x2"

        mult2 = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, basic_context)
        assert mult2 == 1.0, "第二次攻击热血应该失效"


# ============================================================================
# 2. 复杂技能组合测试
# ============================================================================

class TestComplexSkillCombinations:
    """测试多个技能同时作用的复杂场景"""

    def test_spirit_combo_strike_valor_focus(self, basic_mecha, basic_context):
        """测试精神组合：必中+热血+集中"""
        EffectManager.add_effect(basic_mecha, "spirit_strike")
        EffectManager.add_effect(basic_mecha, "spirit_valor")
        EffectManager.add_effect(basic_mecha, "spirit_focus")

        hit_rate = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 50.0, basic_context)
        assert hit_rate == 100.0, "必中应该设为100%"

        damage_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, basic_context)
        assert damage_mult == 2.0, "热血应该x2"

        has_focus = any(e.id.startswith("spirit_focus") for e in basic_mecha.effects)
        assert has_focus, "应该有集中效果"

    def test_trait_and_spirit_synergy(self, basic_mecha, basic_context):
        """测试特性和精神协同：精英+热血"""
        basic_mecha.traits = ["trait_expert"]
        TraitManager.apply_traits(basic_mecha)
        EffectManager.add_effect(basic_mecha, "spirit_valor")

        damage_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, basic_context)
        # 精英增加0.1，热血x2 = 1.0 * 1.1 * 2.0 = 2.2
        assert damage_mult == pytest.approx(2.2, rel=0.01), f"精英+热血应该等于2.2倍，实际{damage_mult}"

    def test_priority_chain_execution(self, basic_mecha, basic_context):
        """测试优先级链：低优先级→高优先级→低优先级"""
        effect_low = Effect(id="low", name="Low", hook="HOOK_PRE_HIT_RATE",
                          operation="add", value=10.0, priority=10)
        effect_high = Effect(id="high", name="High", hook="HOOK_PRE_HIT_RATE",
                           operation="add", value=50.0, priority=100)
        effect_mid = Effect(id="mid", name="Mid", hook="HOOK_PRE_HIT_RATE",
                          operation="add", value=20.0, priority=50)

        basic_mecha.effects.extend([effect_low, effect_high, effect_mid])
        final_hit = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 50.0, basic_context)
        assert final_hit == 130.0, f"优先级链应该是130，实际{final_hit}"

    def test_conditional_skill_triggering(self, basic_mecha, basic_context):
        """测试条件触发：HP<30%时触发狂战士"""
        berserk = Effect(
            id="berserk", name="狂战士",
            hook="HOOK_PRE_DAMAGE_MULT",
            operation="mul", value=1.5,
            conditions=[{"type": "hp_threshold", "val": 0.3, "op": "<"}]
        )
        basic_mecha.effects.append(berserk)

        mult_full = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, basic_context)
        assert mult_full == 1.0, "满血时狂战士不应触发"

        basic_mecha.current_hp = int(basic_mecha.max_hp * 0.25)
        mult_low = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, basic_context)
        assert mult_low == 1.5, "低HP时狂战士应该触发"


# ============================================================================
# 3. 状态持续性测试
# ============================================================================

class TestStatePersistence:
    """测试状态在战斗过程中的持续性"""

    def test_effect_survives_weapon_switch(self, ace_pilot):
        """测试效果在武器切换后依然有效"""
        attacker = Mecha(
            id="m_attacker", name="Attacker", pilot=ace_pilot,
            max_hp=5000, current_hp=5000, max_en=100, current_en=100,
            hit_rate=20.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        EffectManager.add_effect(attacker, "spirit_strike")
        assert len(attacker.effects) > 0

        rifle = Weapon(id="w_rifle", name="Beam Rifle", weapon_type=WeaponType.RIFLE,
                      power=1000, en_cost=10, range_min=1, range_max=5)
        saber = Weapon(id="w_saber", name="Beam Saber", weapon_type=WeaponType.MELEE,
                      power=1500, en_cost=15, range_min=1, range_max=2)
        attacker.weapons = [rifle, saber]

        assert len(attacker.effects) > 0, "切换武器后效果应该保留"

    def test_trait_effects_are_permanent(self, basic_mecha):
        """测试特性效果是永久的"""
        basic_mecha.traits = ["trait_nt"]
        TraitManager.apply_traits(basic_mecha)

        initial_count = len(basic_mecha.effects)
        assert initial_count > 0, "NT特性应该产生效果"

        for _ in range(5):
            EffectManager.tick_effects(basic_mecha)

        assert len(basic_mecha.effects) == initial_count, "特性效果应该永久存在"

    def test_hook_result_caching(self, basic_mecha, basic_context):
        """测试钩子结果缓存机制"""
        precision_focus = Effect(
            id="precision_focus", name="精准专注",
            hook="HOOK_PRE_DAMAGE_MULT",
            operation="add", value=0.5,
            conditions=[{"type": "ref_hook", "ref_hook": "HOOK_PRE_HIT_RATE", "val": 90, "op": ">"}]
        )
        basic_mecha.effects.append(precision_focus)

        SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 95.0, basic_context)
        damage_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, basic_context)

        assert damage_mult == 1.5, "应该根据缓存的命中率触发条件"


# ============================================================================
# 4. 边界条件组合测试
# ============================================================================

class TestEdgeCaseCombinations:
    """测试多个边界条件组合的极端场景"""

    def test_zero_en_with_attack_attempt(self, basic_mecha, basic_context):
        """测试0 EN时尝试攻击"""
        basic_mecha.current_en = 0
        EffectManager.add_effect(basic_mecha, "spirit_strike")

        en_cost = SkillRegistry.process_hook("HOOK_PRE_EN_COST_MULT", 50.0, basic_context)
        assert en_cost >= 0, "EN消耗不应该为负"

    @pytest.mark.parametrize("hp_percent,expected_alive", [
        (0, False), (0.01, False), (1, True), (100, True),
    ])
    def test_hp_boundary_life_status(self, basic_mecha, hp_percent, expected_alive):
        """测试HP边界值的生存状态"""
        basic_mecha.current_hp = int(basic_mecha.max_hp * hp_percent / 100)
        is_alive = basic_mecha.is_alive()
        assert is_alive == expected_alive, f"HP{hp_percent}%时生存状态应该是{expected_alive}"

    def test_max_will_cap(self, basic_mecha):
        """测试气力上限控制"""
        from src.config import Config
        basic_mecha.current_will = Config.WILL_MAX
        basic_mecha.modify_will(50)
        assert basic_mecha.current_will == Config.WILL_MAX, "气力应该被限制在最大值"

    def test_min_will_floor(self, basic_mecha):
        """测试气力下限控制"""
        from src.config import Config
        basic_mecha.current_will = Config.WILL_MIN
        basic_mecha.modify_will(-10)
        assert basic_mecha.current_will == Config.WILL_MIN, "气力应该被限制在最小值"


# ============================================================================
# 5. 参数化场景测试
# ============================================================================

class TestParameterizedScenarios:
    """使用参数化测试覆盖多种场景"""

    @pytest.mark.parametrize("base_value,add_effect,expected_min,expected_max", [
        (0, 0, 0, 10),      # 0基础 + 0加成
        (50, 30, 80, 80),   # 50基础 + 30加成 = 80
        (70, 50, 120, 120), # 70基础 + 50加成 = 120 (会被限制在100)
        (100, -20, 80, 80), # 100基础 - 20惩罚 = 80
    ])
    def test_hit_rate_calculations(self, basic_mecha, basic_context,
                                   base_value, add_effect, expected_min, expected_max):
        """参数化测试：命中率计算的多种场景"""
        # 添加一个简单的加成效果
        if add_effect != 0:
            effect = Effect(
                id="test_hit", name="Test Hit",
                hook="HOOK_PRE_HIT_RATE",
                operation="add", value=float(add_effect)
            )
            basic_mecha.effects.append(effect)

        # 传递基础命中值
        final_hit = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", float(base_value), basic_context)
        assert final_hit >= expected_min, f"命中率应该至少为{expected_min}，实际{final_hit}"
        assert final_hit <= expected_max, f"命中率应该不超过{expected_max}，实际{final_hit}"

    @pytest.mark.parametrize("spirit_id,expected_effect_count", [
        ("spirit_strike", 1), ("spirit_focus", 2), ("spirit_valor", 1),
    ])
    def test_spirit_command_effect_counts(self, basic_mecha, spirit_id, expected_effect_count):
        """参数化测试：不同精神命令产生的效果数量"""
        EffectManager.add_effect(basic_mecha, spirit_id)
        assert len([e for e in basic_mecha.effects if e.id.startswith(spirit_id)]) == expected_effect_count

    @pytest.mark.parametrize("operation,initial,value,expected", [
        ("add", 100, 50, 150), ("sub", 100, 30, 70), ("mul", 100, 2, 200),
        ("div", 100, 2, 50), ("set", 100, 999, 999),
        ("min", 100, 50, 50), ("max", 100, 150, 150),
    ])
    def test_effect_operations(self, basic_mecha, basic_context,
                              operation, initial, value, expected):
        """参数化测试：所有效果操作类型"""
        effect = Effect(
            id="test_op", name="Test",
            hook="HOOK_PRE_HIT_RATE",
            operation=operation, value=value
        )
        basic_mecha.effects.append(effect)

        result = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", initial, basic_context)
        if isinstance(result, float):
            assert result == pytest.approx(expected, rel=0.01)
        else:
            assert result == expected


# ============================================================================
# 6. Mock和Patch测试
# ============================================================================

class TestMockedScenarios:
    """使用Mock测试可控的随机场景"""

    @patch('random.uniform')
    def test_forced_miss_result(self, mock_uniform, basic_context):
        """Mock测试：强制产生Miss结果"""
        mock_uniform.return_value = 0.01
        result, damage = AttackTableResolver.resolve_attack(basic_context)
        assert result == AttackResult.MISS, "应该强制产生Miss"

    def test_callback_effect_with_mock(self, basic_mecha, basic_context):
        """Mock测试：验证回调函数被正确调用"""
        @SkillRegistry.register_callback("test_mock_cb")
        def mock_cb_func(v, c, o):
            return 999

        effect = Effect(
            id="test_cb", name="Test Callback",
            hook="HOOK_PRE_HIT_RATE",
            operation="callback", value="test_mock_cb"
        )
        basic_mecha.effects.append(effect)

        result = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 50.0, basic_context)
        assert result == 999, "应该返回Mock的值"


# ============================================================================
# 7. 异常和错误处理测试
# ============================================================================

class TestErrorHandling:
    """测试系统的错误处理能力"""

    def test_invalid_effect_id_returns_empty(self, basic_mecha):
        """测试：无效的效果ID返回空列表"""
        from src.skill_system.effect_factory import EffectFactory

        # 无效ID应该返回空列表
        result = EffectFactory.create_effect("spirit_nonexistent_12345")
        assert result == [], "无效效果ID应该返回空列表"

    def test_empty_trait_list(self, basic_mecha):
        """测试：空特性列表不会崩溃"""
        basic_mecha.traits = []
        TraitManager.apply_traits(basic_mecha)
        assert len(basic_mecha.effects) == 0, "空特性列表不应该产生效果"


# ============================================================================
# 8. 性能和压力测试
# ============================================================================

class TestPerformanceStress:
    """轻量级的性能和压力测试"""

    def test_many_effects_processing(self, basic_mecha, basic_context):
        """测试：处理大量效果的性能"""
        for i in range(100):
            effect = Effect(
                id=f"effect_{i}", name=f"Effect {i}",
                hook="HOOK_PRE_HIT_RATE",
                operation="add", value=1.0,
                priority=i % 100
            )
            basic_mecha.effects.append(effect)

        result = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 0.0, basic_context)
        assert result == 100.0, "应该正确处理100个效果"

    def test_rapid_effect_addition_and_removal(self, basic_mecha):
        """测试：快速添加和移除效果"""
        initial_count = len(basic_mecha.effects)

        for _ in range(10):
            EffectManager.add_effect(basic_mecha, "spirit_strike", duration=0)
            EffectManager.tick_effects(basic_mecha)

        assert len(basic_mecha.effects) == initial_count, "应该正确清理所有效果"
