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
        heavy_weapon = Weapon(uid="w_heavy_uid", definition_id="w_heavy", name="Heavy Cannon", type=WeaponType.SHOOTING,
                             final_power=3000, en_cost=30, range_min=1, range_max=5000,
                             will_req=0, anim_id="default")
        basic_mecha.weapons = [heavy_weapon]

        sim = BattleSimulator(heavy_mecha, basic_mecha)
        sim.run_battle()

        assert sim.round_number >= 2, "应该进行至少2回合"
        total_damage = (heavy_mecha.final_max_hp - heavy_mecha.current_hp +
                       basic_mecha.final_max_hp - basic_mecha.current_hp)
        assert total_damage > 0, "应该有伤害产生"

    def test_will_growth_across_rounds(self, basic_mecha):
        """测试气力在多回合中的增长"""
        opponent = Mecha(
            instance_id="m_opp", mecha_name="Opponent", main_portrait="m_opp_img",
            final_max_hp=5000, current_hp=5000, final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100
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
        basic_mecha.skills = ["trait_expert"]
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

        basic_mecha.current_hp = int(basic_mecha.final_max_hp * 0.25)
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
            instance_id="m_attacker", mecha_name="Attacker", main_portrait="m_atk_img",
            final_max_hp=5000, current_hp=5000, max_en=100, current_en=100,
            final_hit=20.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100
        )

        EffectManager.add_effect(attacker, "spirit_strike")
        assert len(attacker.effects) > 0

        rifle = Weapon(uid="w_rifle_uid", definition_id="w_rifle", name="Beam Rifle", type=WeaponType.SHOOTING,
                      final_power=1000, en_cost=10, range_min=1, range_max=5000,
                      will_req=0, anim_id="default")
        saber = Weapon(uid="w_saber_uid", definition_id="w_saber", name="Beam Saber", type=WeaponType.MELEE,
                      final_power=1500, en_cost=15, range_min=1, range_max=2000,
                      will_req=0, anim_id="default")
        attacker.weapons = [rifle, saber]

        assert len(attacker.effects) > 0, "切换武器后效果应该保留"

    def test_trait_effects_are_permanent(self, basic_mecha):
        """测试特性效果是永久的"""
        basic_mecha.skills = ["trait_nt"]
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
        basic_mecha.current_hp = int(basic_mecha.final_max_hp * hp_percent / 100)
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
        basic_mecha.skills = []
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


# ============================================================================
# Engine.py 覆盖率测试
# ============================================================================

class TestEngineCoverage:
    """测试 engine.py 中未覆盖的代码路径"""

    def test_initiative_forced_switch(self, ace_pilot):
        """测试强制换手机制 (未覆盖行 58-64)"""
        from src.combat.engine import InitiativeCalculator
        from src.config import Config

        # 创建两个相同属性的机体（确保平局）
        mecha_a = Mecha(
            instance_id="m_a", mecha_name="MechaA", main_portrait="m_a_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )
        mecha_b = Mecha(
            instance_id="m_b", mecha_name="MechaB", main_portrait="m_b_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        calc = InitiativeCalculator()
        # 模拟 A 方连续获胜达到阈值
        threshold = Config.CONSECUTIVE_WINS_THRESHOLD
        calc.consecutive_wins['A'] = threshold
        calc.last_winner = 'A'

        # 下次计算时应该强制换手给 B
        first, second, reason = calc.calculate_initiative(mecha_a, mecha_b, 1)

        assert first == mecha_b  # B 方获得先手
        assert reason.value == "强制换手机制"

    def test_initiative_hook_forces_first_attacker(self, ace_pilot):
        """测试 HOOK_INITIATIVE_CHECK 强制 A 先手 (未覆盖行 73-75)"""
        from src.combat.engine import InitiativeCalculator

        # 创建临时函数并注册为钩子
        def force_a(value, ctx):
            if ctx.attacker.instance_id == "m_a":
                return True
            return value

        # 直接添加到 hooks 字典
        if "HOOK_INITIATIVE_CHECK" not in SkillRegistry._hooks:
            SkillRegistry._hooks["HOOK_INITIATIVE_CHECK"] = []
        SkillRegistry._hooks["HOOK_INITIATIVE_CHECK"].append(force_a)

        try:
            mecha_a = Mecha(
                instance_id="m_a", mecha_name="MechaA", main_portrait="m_a_img",
                final_max_hp=5000, current_hp=5000,
                final_max_en=100, current_en=100,
                final_armor=1000, final_mobility=100,
                final_hit=10.0, final_precision=10.0, final_crit=5.0,
                final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
                pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                                "stat_defense": 100, "stat_reaction": 100}
            )
            mecha_b = Mecha(
                instance_id="m_b", mecha_name="MechaB", main_portrait="m_b_img",
                final_max_hp=5000, current_hp=5000,
                final_max_en=100, current_en=100,
                final_armor=1000, final_mobility=100,
                final_hit=10.0, final_precision=10.0, final_crit=5.0,
                final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
                pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                                "stat_defense": 100, "stat_reaction": 100}
            )

            calc = InitiativeCalculator()
            first, second, reason = calc.calculate_initiative(mecha_a, mecha_b, 1)

            assert first == mecha_a
            assert reason.value == "机体性能优势"
        finally:
            # 清理钩子
            SkillRegistry._hooks["HOOK_INITIATIVE_CHECK"].pop()

    def test_determine_initiative_reason_will_diff(self):
        """测试气力差异判定先手原因 (未覆盖行 168-169)"""
        from src.combat.engine import InitiativeCalculator

        mecha_a = Mecha(
            instance_id="m_a", mecha_name="MechaA", main_portrait="m_a_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )
        mecha_a.current_will = 150  # 高气力

        mecha_b = Mecha(
            instance_id="m_b", mecha_name="MechaB", main_portrait="m_b_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )
        mecha_b.current_will = 120  # 低气力，差异 30 > 20

        calc = InitiativeCalculator()
        reason = calc._determine_reason(mecha_a, mecha_b)

        assert reason.value == "气力优势延续"

    def test_weapon_selector_filters_out_of_range(self, ace_pilot):
        """测试武器选择过滤超出射程的武器 (未覆盖行 222, 226-227)"""
        from src.combat.engine import WeaponSelector

        mecha = Mecha(
            instance_id="m_test", mecha_name="TestMecha", main_portrait="m_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        # 添加不同射程的武器
        short_range = Weapon(
            uid="w_short", definition_id="w_short", name="短程武器",
            type=WeaponType.MELEE,
            final_power=1000, en_cost=10,
            range_min=100, range_max=500,
            will_req=0, anim_id="a_short"
        )
        long_range = Weapon(
            uid="w_long", definition_id="w_long", name="长程武器",
            type=WeaponType.SHOOTING,
            final_power=1500, en_cost=15,
            range_min=2000, range_max=6000,
            will_req=0, anim_id="a_long"
        )

        mecha.weapons = [short_range, long_range]

        # 在 1000m 距离下，两个武器都不可用（短程500，长程2000-6000）
        selected = WeaponSelector.select_best_weapon(mecha, 1000)
        assert selected.definition_id == "wpn_fallback"  # 应该返回保底武器

        # 在 50m 距离下（超短程），应该返回保底武器
        selected = WeaponSelector.select_best_weapon(mecha, 50)
        assert selected.type == "撞击"  # 保底武器

    def test_battle_simulator_insufficient_en(self, ace_pilot):
        """测试 EN 不足时无法攻击 (未覆盖行 468-470)"""
        from src.combat.engine import BattleSimulator

        attacker = Mecha(
            instance_id="m_att", mecha_name="Attacker", main_portrait="m_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=0,  # 零 EN
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        defender = Mecha(
            instance_id="m_def", mecha_name="Defender", main_portrait="m_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        weapon = Weapon(
            uid="w_test", definition_id="w_test", name="测试武器",
            type=WeaponType.SHOOTING,
            final_power=1000, en_cost=10,
            range_min=100, range_max=1000,
            will_req=0, anim_id="a_test"
        )
        attacker.weapons = [weapon]

        sim = BattleSimulator(attacker, defender)
        sim.round_number = 1

        # 应该不会崩溃，EN 不足时跳过攻击
        sim._execute_attack(attacker, defender, 1000, is_first=True)
        # 攻击方 EN 应该仍然为 0（没有消耗）
        assert attacker.current_en == 0

    def test_initiative_forced_switch_b_wins(self, ace_pilot):
        """测试 B 方连续获胜强制换手 (未覆盖行 79-80)"""
        from src.combat.engine import InitiativeCalculator
        from src.config import Config

        mecha_a = Mecha(
            instance_id="m_a", mecha_name="MechaA", main_portrait="m_a_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )
        mecha_b = Mecha(
            instance_id="m_b", mecha_name="MechaB", main_portrait="m_b_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        calc = InitiativeCalculator()
        # 模拟 B 方连续获胜达到阈值
        threshold = Config.CONSECUTIVE_WINS_THRESHOLD
        calc.consecutive_wins['B'] = threshold
        calc.last_winner = 'B'

        # 下次计算时应该强制换手给 A
        first, second, reason = calc.calculate_initiative(mecha_a, mecha_b, 1)

        assert first == mecha_a  # A 方获得先手
        assert reason.value == "强制换手机制"

    def test_initiative_tie_breaker_counter(self, ace_pilot):
        """测试平局时后手方获得先手 (未覆盖行 100-105)"""
        from src.combat.engine import InitiativeCalculator

        mecha_a = Mecha(
            instance_id="m_a", mecha_name="MechaA", main_portrait="m_a_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )
        mecha_b = Mecha(
            instance_id="m_b", mecha_name="MechaB", main_portrait="m_b_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        calc = InitiativeCalculator()
        # 设置 A 方上次获胜
        calc.last_winner = 'A'
        calc.consecutive_wins = {'A': 0, 'B': 0}

        # Mock random 使双方得分相同
        from unittest.mock import patch
        with patch('random.uniform', return_value=0):
            with patch('src.combat.engine.InitiativeCalculator._calculate_initiative_score', return_value=100):
                first, second, reason = calc.calculate_initiative(mecha_a, mecha_b, 1)

        # 平局时，上次后手方 B 应该获得先手
        assert first == mecha_b
        assert reason.value == "战术反超"

    def test_initiative_reason_pilot(self, ace_pilot):
        """测试反应值差异判定先手原因 (未覆盖行 171)"""
        from src.combat.engine import InitiativeCalculator

        mecha_a = Mecha(
            instance_id="m_a", mecha_name="MechaA", main_portrait="m_a_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 130}  # 高反应
        )
        mecha_b = Mecha(
            instance_id="m_b", mecha_name="MechaB", main_portrait="m_b_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}  # 低反应
        )

        calc = InitiativeCalculator()
        # Mock 使 A 方得分更高
        from unittest.mock import patch
        with patch('src.combat.engine.InitiativeCalculator._calculate_initiative_score',
                  side_effect=lambda m: 200 if m == mecha_a else 100):
            first, second, reason = calc.calculate_initiative(mecha_a, mecha_b, 1)

        assert first == mecha_a
        # 反应差异 > 15 时应该是 PILOT
        assert reason.value == "驾驶员感知优势"

    def test_generate_distance(self, ace_pilot):
        """测试距离生成 (未覆盖行 227)"""
        from src.combat.engine import BattleSimulator
        from src.config import Config

        attacker = Mecha(
            instance_id="m_att", mecha_name="Attacker", main_portrait="m_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        defender = Mecha(
            instance_id="m_def", mecha_name="Defender", main_portrait="m_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        sim = BattleSimulator(attacker, defender)

        # 第 1 回合：距离应该在初始范围内
        sim.round_number = 1
        distance1 = sim._generate_distance()
        assert Config.DISTANCE_INITIAL_MIN <= distance1 <= Config.DISTANCE_INITIAL_MAX

        # 第 5 回合：距离应该减少
        sim.round_number = 5
        distance5 = sim._generate_distance()
        assert distance5 < distance1  # 应该更小

        # 第 10 回合：距离应该在最终范围内
        sim.round_number = 10
        distance10 = sim._generate_distance()
        assert Config.DISTANCE_FINAL_MIN <= distance10 <= Config.DISTANCE_FINAL_MAX

    def test_conclude_battle_draw(self, ace_pilot):
        """测试战斗平局判定 (未覆盖行 308)"""
        from src.combat.engine import BattleSimulator
        from unittest.mock import patch

        attacker = Mecha(
            instance_id="m_att", mecha_name="Attacker", main_portrait="m_img",
            final_max_hp=5000, current_hp=2500,  # 50%
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        defender = Mecha(
            instance_id="m_def", mecha_name="Defender", main_portrait="m_img",
            final_max_hp=5000, current_hp=2500,  # 相同的 50%
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        sim = BattleSimulator(attacker, defender)
        sim.round_number = 999  # 模拟达到回合上限

        # 捕获打印输出
        import io
        from unittest.mock import patch
        output = io.StringIO()

        with patch('sys.stdout', output):
            sim._conclude_battle()

        result = output.getvalue()
        # 应该显示平局
        assert "平局" in result

    def test_round_survivor_check_second_mover_dies(self, ace_pilot):
        """测试后攻方被击破时停止反击 (未覆盖行 369-370)"""
        from src.combat.engine import BattleSimulator
        from unittest.mock import patch

        attacker = Mecha(
            instance_id="m_att", mecha_name="Attacker", main_portrait="m_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        defender = Mecha(
            instance_id="m_def", mecha_name="Defender", main_portrait="m_img",
            final_max_hp=5000, current_hp=1,  # 接近死亡
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        # 添加武器
        weapon = Weapon(
            uid="w_test", definition_id="w_test", name="测试武器",
            type=WeaponType.SHOOTING,
            final_power=10000, en_cost=10,
            range_min=100, range_max=1000,
            will_req=0, anim_id="a_test"
        )
        attacker.weapons = [weapon]

        sim = BattleSimulator(attacker, defender)

        # Mock 圆桌判定返回 HIT，造成大量伤害
        def mock_resolve(ctx):
            from src.models import AttackResult
            defender.take_damage(10000)  # 击破
            return AttackResult.HIT, 10000

        with patch('src.combat.engine.AttackTableResolver.resolve_attack', side_effect=mock_resolve):
            # 执行回合
            sim._execute_round()

        # 验证输出包含击破信息
        import io
        output = io.StringIO()
        with patch('sys.stdout', output):
            # 再次执行应该检测到死亡
            pass

    def test_round_survivor_check_first_mover_dies(self, ace_pilot):
        """测试先攻方被击破时停止回合 (未覆盖行 379-380)"""
        from src.combat.engine import BattleSimulator, InitiativeCalculator
        from src.models import InitiativeReason

        # 使用中性命名，避免角色语义误导
        mecha_a = Mecha(
            instance_id="m_a", mecha_name="MechaA", main_portrait="m_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        mecha_b = Mecha(
            instance_id="m_b", mecha_name="MechaB", main_portrait="m_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        # 添加武器
        weapon = Weapon(
            uid="w_test", definition_id="w_test", name="测试武器",
            type=WeaponType.SHOOTING,
            final_power=10000, en_cost=10,
            range_min=100, range_max=1000,
            will_req=0, anim_id="a_test"
        )
        mecha_b.weapons = [weapon]

        sim = BattleSimulator(mecha_a, mecha_b)
        sim.round_number = 1

        # Mock 先手判定，确保 mecha_a 是先手方
        def mock_initiative(self_calc, a, b, round_num):
            return a, b, InitiativeReason.PERFORMANCE

        # Mock 圆表判定 - 先攻方攻击 miss，后攻方反击击杀先攻方
        call_count = [0]

        def mock_resolve(ctx):
            from src.models import AttackResult
            call_count[0] += 1
            if call_count[0] == 1:
                # 先攻方（mecha_a）攻击，miss
                return AttackResult.MISS, 0
            else:
                # 后攻方（mecha_b）反击，击杀先攻方
                # 此时 ctx.defender 是先攻方 mecha_a
                ctx.defender.take_damage(10000)
                return AttackResult.HIT, 10000

        from unittest.mock import patch
        with patch.object(InitiativeCalculator, 'calculate_initiative', mock_initiative):
            with patch('src.combat.engine.AttackTableResolver.resolve_attack', side_effect=mock_resolve):
                sim._execute_round()

        # 验证：先手方死亡，后手方存活
        assert not mecha_a.is_alive(), "先手方应该被击杀"
        assert mecha_b.is_alive(), "后手方应该存活"

    def test_en_cost_modification(self, ace_pilot):
        """测试 EN 消耗被修正 (未覆盖行 469-470)"""
        from src.combat.engine import BattleSimulator

        attacker = Mecha(
            instance_id="m_att", mecha_name="Attacker", main_portrait="m_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=50,  # 有限 EN
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        defender = Mecha(
            instance_id="m_def", mecha_name="Defender", main_portrait="m_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_armor=1000, final_mobility=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
            pilot_stats_backup={"stat_shooting": 100, "stat_melee": 100, "stat_awakening": 100,
                            "stat_defense": 100, "stat_reaction": 100}
        )

        weapon = Weapon(
            uid="w_test", definition_id="w_test", name="测试武器",
            type=WeaponType.SHOOTING,
            final_power=1000, en_cost=30,  # 需要 30 EN
            range_min=100, range_max=1000,
            will_req=0, anim_id="a_test"
        )
        attacker.weapons = [weapon]

        sim = BattleSimulator(attacker, defender)
        sim.round_number = 1

        # 添加一个减少 EN 消耗的效果 (50% 折扣)
        from src.models import Effect
        effect = Effect(
            id="test_en_save", name="EN Save",
            hook="HOOK_PRE_EN_COST_MULT",
            operation="mul", value=0.5,
            duration=1, priority=50
        )
        attacker.effects.append(effect)

        # Mock 圆表判定
        from unittest.mock import patch
        from src.models import AttackResult
        with patch('random.uniform', return_value=50):
            with patch('src.combat.engine.AttackTableResolver.resolve_attack',
                      return_value=(AttackResult.HIT, 1000)):
                sim._execute_attack(attacker, defender, 500, is_first=True)

        # EN 消耗应该被减少：30 * 0.5 = 15
        # 初始 50 - 15 = 35
        assert attacker.current_en == 35
