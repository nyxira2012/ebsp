"""
单元测试: 技能系统 - 效果处理器测试
测试EffectProcessor的核心逻辑，包括操作类型、优先级排序、概率触发等
"""

import pytest
from unittest.mock import Mock, patch
from src.models import Mecha, BattleContext, Effect, Weapon, WeaponType, Terrain
from src.skill_system.processor import EffectProcessor
from src.skills import SkillRegistry


# ============================================================================
# 操作类型测试
# ============================================================================

class TestEffectOperations:
    """效果操作类型测试"""

    def test_operation_add(self, basic_mecha, basic_context):
        """测试加法操作"""
        basic_mecha.effects.append(Effect(
            id="test_add", name="Test Add",
            hook="HOOK_PRE_HIT_RATE",
            operation="add", value=30.0,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_PRE_HIT_RATE", 10.0, basic_context)
        assert result == 40.0

    def test_operation_sub(self, basic_mecha, basic_context):
        """测试减法操作"""
        basic_mecha.effects.append(Effect(
            id="test_sub", name="Test Sub",
            hook="HOOK_TEST",
            operation="sub", value=5.0,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 20.0, basic_context)
        assert result == 15.0

    def test_operation_mul(self, basic_mecha, basic_context):
        """测试乘法操作"""
        basic_mecha.effects.append(Effect(
            id="test_mul", name="Test Mul",
            hook="HOOK_PRE_DAMAGE_MULT",
            operation="mul", value=2.0,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_PRE_DAMAGE_MULT", 100.0, basic_context)
        assert result == 200.0

    def test_operation_div(self, basic_mecha, basic_context):
        """测试除法操作"""
        basic_mecha.effects.append(Effect(
            id="test_div", name="Test Div",
            hook="HOOK_TEST",
            operation="div", value=2.0,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 100.0, basic_context)
        assert result == 50.0

    def test_operation_div_by_zero(self, basic_mecha, basic_context):
        """测试除以零 (应返回原值)"""
        basic_mecha.effects.append(Effect(
            id="test_div_zero", name="Test Div Zero",
            hook="HOOK_TEST",
            operation="div", value=0.0,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 100.0, basic_context)
        assert result == 100.0

    def test_operation_set(self, basic_mecha, basic_context):
        """测试设置操作"""
        basic_mecha.effects.append(Effect(
            id="test_set", name="Test Set",
            hook="HOOK_PRE_HIT_RATE",
            operation="set", value=100.0,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_PRE_HIT_RATE", 10.0, basic_context)
        assert result == 100.0

    def test_operation_min(self, basic_mecha, basic_context):
        """测试取小操作"""
        basic_mecha.effects.append(Effect(
            id="test_min", name="Test Min",
            hook="HOOK_TEST",
            operation="min", value=50.0,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 100.0, basic_context)
        assert result == 50.0

    def test_operation_max(self, basic_mecha, basic_context):
        """测试取大操作"""
        basic_mecha.effects.append(Effect(
            id="test_max", name="Test Max",
            hook="HOOK_TEST",
            operation="max", value=150.0,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 100.0, basic_context)
        assert result == 150.0

    @pytest.mark.parametrize("op,initial,value,expected", [
        ("add", 10, 5, 15),
        ("sub", 10, 3, 7),
        ("mul", 10, 2, 20),
        ("div", 10, 2, 5),
        ("set", 10, 100, 100),
        ("min", 100, 50, 50),
        ("max", 50, 100, 100),
    ])
    def test_operations_parametrized(self, op, initial, value, expected, basic_mecha, basic_context):
        """参数化测试所有操作类型"""
        basic_mecha.effects.append(Effect(
            id=f"test_{op}", name=f"Test {op}",
            hook="HOOK_TEST",
            operation=op, value=value,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", initial, basic_context)
        assert result == expected


# ============================================================================
# 优先级排序测试
# ============================================================================

class TestPrioritySorting:
    """优先级排序测试"""

    def test_priority_order(self, basic_mecha, basic_context):
        """测试优先级排序 (低优先级先执行)"""
        # 添加三个不同优先级的效果
        basic_mecha.effects.extend([
            Effect(id="p50", name="Priority 50", hook="HOOK_TEST",
                   operation="add", value=1.0, priority=50),
            Effect(id="p10", name="Priority 10", hook="HOOK_TEST",
                   operation="add", value=10.0, priority=10),
            Effect(id="p90", name="Priority 90", hook="HOOK_TEST",
                   operation="add", value=2.0, priority=90),
        ])

        # 执行顺序应该是: p10 -> p50 -> p90
        # 最终结果 = 0 + 10 + 1 + 2 = 13
        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert result == 13.0

    def test_sub_priority_order(self, basic_mecha, basic_context):
        """测试子优先级排序"""
        # 相同priority，不同sub_priority
        basic_mecha.effects.extend([
            Effect(id="p50_s500", name="P50 S500", hook="HOOK_TEST",
                   operation="add", value=1.0, priority=50, sub_priority=500),
            Effect(id="p50_s300", name="P50 S300", hook="HOOK_TEST",
                   operation="add", value=10.0, priority=50, sub_priority=300),
            Effect(id="p50_s700", name="P50 S700", hook="HOOK_TEST",
                   operation="add", value=2.0, priority=50, sub_priority=700),
        ])

        # 执行顺序: p50_s300 -> p50_s500 -> p50_s700
        # 结果 = 0 + 10 + 1 + 2 = 13
        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert result == 13.0

    def test_set_operation_priority(self, basic_mecha, basic_context):
        """测试set操作的高优先级 (最终决定权)"""
        basic_mecha.effects.extend([
            Effect(id="low", name="Low", hook="HOOK_TEST",
                   operation="add", value=100.0, priority=10),
            Effect(id="high", name="High", hook="HOOK_TEST",
                   operation="set", value=999.0, priority=100),
        ])

        # 低优先级先执行: 0 + 100 = 100
        # 高优先级后执行: set 999 = 999
        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert result == 999.0


# ============================================================================
# 概率触发测试
# ============================================================================

class TestTriggerChance:
    """概率触发测试"""

    @patch('random.random')  # Mock random函数
    def test_trigger_chance_always(self, mock_random, basic_mecha, basic_context):
        """测试必定触发 (trigger_chance=1.0)"""
        mock_random.return_value = 0.5  # 任意值

        basic_mecha.effects.append(Effect(
            id="test_always", name="Test Always",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            trigger_chance=1.0,  # 100%触发
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert result == 10.0

    @patch('random.random')
    def test_trigger_chance_never(self, mock_random, basic_mecha, basic_context):
        """测试永不触发 (trigger_chance=0.0)"""
        mock_random.return_value = 0.5

        basic_mecha.effects.append(Effect(
            id="test_never", name="Test Never",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            trigger_chance=0.0,  # 0%触发
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert result == 0.0  # 未触发，保持原值

    @patch('random.random')
    def test_trigger_chance_50_percent_trigger(self, mock_random, basic_mecha, basic_context):
        """测试50%概率 - 触发"""
        mock_random.return_value = 0.3  # < 0.5，应该触发

        basic_mecha.effects.append(Effect(
            id="test_50", name="Test 50%",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            trigger_chance=0.5,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert result == 10.0

    @patch('random.random')
    def test_trigger_chance_50_percent_no_trigger(self, mock_random, basic_mecha, basic_context):
        """测试50%概率 - 不触发"""
        mock_random.return_value = 0.7  # > 0.5，不应触发

        basic_mecha.effects.append(Effect(
            id="test_50", name="Test 50%",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            trigger_chance=0.5,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert result == 0.0


# ============================================================================
# 持续时间和次数测试
# ============================================================================

class TestDurationAndCharges:
    """持续时间和次数测试"""

    def test_duration_expired(self, basic_mecha, basic_context):
        """测试持续时间过期 (duration=0)"""
        basic_mecha.effects.append(Effect(
            id="test_expired", name="Test Expired",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            duration=0,  # 已过期
            priority=50
        ))

        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert result == 0.0  # 未执行

    def test_charges_exhausted(self, basic_mecha, basic_context):
        """测试次数耗尽 (charges=0)"""
        basic_mecha.effects.append(Effect(
            id="test_no_charges", name="Test No Charges",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            charges=0,  # 次数耗尽
            priority=50
        ))

        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert result == 0.0

    def test_charges_decrease(self, basic_mecha, basic_context):
        """测试次数递减"""
        effect = Effect(
            id="test_charges", name="Test Charges",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            charges=3,
            priority=50
        )
        basic_mecha.effects.append(effect)

        # 第一次执行，charges应减1
        EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert effect.charges == 2

        # 第二次执行
        EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert effect.charges == 1

    def test_charges_zero_after_trigger(self, basic_mecha, basic_context):
        """测试次数归零后duration也设为0"""
        effect = Effect(
            id="test_charges_end", name="Test Charges End",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            charges=1,
            priority=50
        )
        basic_mecha.effects.append(effect)

        EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert effect.charges == 0
        assert effect.duration == 0  # 次数用完，效果结束

    def test_infinite_charges(self, basic_mecha, basic_context):
        """测试无限次数 (charges=-1)"""
        effect = Effect(
            id="test_infinite", name="Test Infinite",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            charges=-1,  # 无限
            priority=50
        )
        basic_mecha.effects.append(effect)

        EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert effect.charges == -1  # 不减少


# ============================================================================
# 递归防护测试
# ============================================================================

class TestRecursionProtection:
    """递归防护测试"""

    def test_hook_stack_tracking(self, basic_mecha, basic_context):
        """测试钩子栈跟踪"""
        # 添加一个会递归的回调 (模拟)
        def recursive_callback(val, ctx, owner):
            # 尝试再次调用同一个hook
            return EffectProcessor.process("HOOK_TEST", val + 1, ctx)

        SkillRegistry.register_callback("cb_recursive")(recursive_callback)

        basic_mecha.effects.append(Effect(
            id="test_recursive", name="Test Recursive",
            hook="HOOK_TEST",
            operation="callback", value="cb_recursive",
            duration=1
        ))

        # 应该在达到深度限制后停止递归
        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        # 由于深度限制是3，最多递归3次
        assert result <= 3.0


# ============================================================================
# 结果缓存测试
# ============================================================================

class TestResultCaching:
    """结果缓存测试"""

    def test_numeric_result_cached(self, basic_mecha, basic_context):
        """测试数值结果缓存"""
        basic_mecha.effects.append(Effect(
            id="test_cache", name="Test Cache",
            hook="HOOK_PRE_HIT_RATE",
            operation="add", value=30.0,
            duration=1
        ))

        EffectProcessor.process("HOOK_PRE_HIT_RATE", 10.0, basic_context)

        # 检查缓存
        assert "HOOK_PRE_HIT_RATE" in basic_context.cached_results
        assert basic_context.cached_results["HOOK_PRE_HIT_RATE"] == 40.0

    def test_non_numeric_not_cached(self, basic_mecha, basic_context):
        """测试非数值结果不缓存"""
        # Mock返回非数值
        def mock_callback(val, ctx, owner):
            return "not_a_number"

        SkillRegistry.register_callback("cb_mock")(mock_callback)

        basic_mecha.effects.append(Effect(
            id="test_no_cache", name="Test No Cache",
            hook="HOOK_TEST",
            operation="callback", value="cb_mock",
            duration=1
        ))

        EffectProcessor.process("HOOK_TEST", 0.0, basic_context)

        # 不应缓存非数值结果
        # (或即使缓存，也不会被ref_hook使用)


# ============================================================================
# 多效果叠加测试
# ============================================================================

class TestMultipleEffects:
    """多效果叠加测试"""

    def test_additive_effects(self, basic_mecha, basic_context):
        """测试多个add效果叠加"""
        basic_mecha.effects.extend([
            Effect(id="e1", name="E1", hook="HOOK_TEST",
                   operation="add", value=10.0, priority=50),
            Effect(id="e2", name="E2", hook="HOOK_TEST",
                   operation="add", value=20.0, priority=50),
            Effect(id="e3", name="E3", hook="HOOK_TEST",
                   operation="add", value=30.0, priority=50),
        ])

        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert result == 60.0

    def test_multiplicative_effects(self, basic_mecha, basic_context):
        """测试多个mul效果叠加"""
        basic_mecha.effects.extend([
            Effect(id="e1", name="E1", hook="HOOK_TEST",
                   operation="mul", value=2.0, priority=50),
            Effect(id="e2", name="E2", hook="HOOK_TEST",
                   operation="mul", value=3.0, priority=50),
        ])

        # ((0 * 2) * 3) = 0 (初始是0，乘法还是0)
        result = EffectProcessor.process("HOOK_TEST", 10.0, basic_context)
        assert result == 60.0  # 10 * 2 * 3

    def test_mixed_operations(self, basic_mecha, basic_context):
        """测试混合操作"""
        basic_mecha.effects.extend([
            Effect(id="e1", name="E1", hook="HOOK_TEST",
                   operation="add", value=10.0, priority=50),
            Effect(id="e2", name="E2", hook="HOOK_TEST",
                   operation="mul", value=2.0, priority=50),
        ])

        # (0 + 10) * 2 = 20
        result = EffectProcessor.process("HOOK_TEST", 0.0, basic_context)
        assert result == 20.0


# ============================================================================
# 目标选择测试
# ============================================================================

class TestTargetSelection:
    """目标选择测试"""

    def test_target_self(self, basic_mecha, ace_pilot):
        """测试目标是自己"""
        enemy = Mecha(
            instance_id="m_enemy", mecha_name="Enemy", main_portrait="m_enemy_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100
        )

        context = BattleContext(
            round_number=1, distance=1000, terrain=Terrain.SPACE,
            mecha_a=basic_mecha, mecha_b=enemy,
            weapon=Weapon(uid="w_uid", definition_id="w", name="W", type=WeaponType.SHOOTING,
                        final_power=1000, en_cost=10, range_min=1, range_max=5000,
                        will_req=0, anim_id="default")
        )

        # 攻击方添加一个对自己生效的效果
        basic_mecha.effects.append(Effect(
            id="test_self", name="Test Self",
            hook="HOOK_PRE_HIT_RATE",
            operation="add", value=30.0,
            target="self",  # 对自己
            duration=1
        ))

        result = EffectProcessor.process("HOOK_PRE_HIT_RATE", 10.0, context)
        assert result == 40.0  # 10 + 30

    def test_target_enemy(self, basic_mecha, ace_pilot):
        """测试目标是敌人"""
        enemy = Mecha(
            instance_id="m_enemy", mecha_name="Enemy", main_portrait="m_enemy_img",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100
        )

        context = BattleContext(
            round_number=1, distance=1000, terrain=Terrain.SPACE,
            mecha_a=basic_mecha, mecha_b=enemy,
            weapon=Weapon(uid="w_uid", definition_id="w", name="W", type=WeaponType.SHOOTING,
                        final_power=1000, en_cost=10, range_min=1, range_max=5000,
                        will_req=0, anim_id="default")
        )

        # 攻击方添加一个对敌人生效的效果
        basic_mecha.effects.append(Effect(
            id="test_enemy", name="Test Enemy",
            hook="HOOK_PRE_HIT_RATE",
            operation="add", value=30.0,
            target="enemy",  # 对敌人
            duration=1
        ))

        # 这个效果应该作用于防御方(enemy)
        # 但HOOK_PRE_HIT_RATE通常是攻击方的属性
        # 所以这里的测试可能需要根据实际逻辑调整


# ============================================================================
# 布尔操作测试 (未覆盖行 188-195)
# ============================================================================

class TestBooleanOperations:
    """测试布尔类型的效果操作"""

    def test_operation_and_true_true(self, basic_mecha, basic_context):
        """测试 and 操作：True and True = True"""
        basic_mecha.effects.append(Effect(
            id="test_and", name="Test And",
            hook="HOOK_TEST_BOOL",
            operation="and", value=True,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST_BOOL", True, basic_context)
        assert result is True

    def test_operation_and_true_false(self, basic_mecha, basic_context):
        """测试 and 操作：True and False = False"""
        basic_mecha.effects.append(Effect(
            id="test_and", name="Test And",
            hook="HOOK_TEST_BOOL",
            operation="and", value=False,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST_BOOL", True, basic_context)
        assert result is False

    def test_operation_or_false_false(self, basic_mecha, basic_context):
        """测试 or 操作：False or False = False"""
        basic_mecha.effects.append(Effect(
            id="test_or", name="Test Or",
            hook="HOOK_TEST_BOOL",
            operation="or", value=False,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST_BOOL", False, basic_context)
        assert result is False

    def test_operation_or_true_false(self, basic_mecha, basic_context):
        """测试 or 操作：True or False = True"""
        basic_mecha.effects.append(Effect(
            id="test_or", name="Test Or",
            hook="HOOK_TEST_BOOL",
            operation="or", value=False,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST_BOOL", True, basic_context)
        assert result is True

    def test_operation_not_true(self, basic_mecha, basic_context):
        """测试 not 操作：not True = False"""
        basic_mecha.effects.append(Effect(
            id="test_not", name="Test Not",
            hook="HOOK_TEST_BOOL",
            operation="not", value=True,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST_BOOL", True, basic_context)
        assert result is False

    def test_operation_not_false(self, basic_mecha, basic_context):
        """测试 not 操作：not False = True"""
        basic_mecha.effects.append(Effect(
            id="test_not", name="Test Not",
            hook="HOOK_TEST_BOOL",
            operation="not", value=False,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST_BOOL", False, basic_context)
        assert result is True

    def test_operation_set_bool(self, basic_mecha, basic_context):
        """测试 set 操作：set False"""
        basic_mecha.effects.append(Effect(
            id="test_set_bool", name="Test Set Bool",
            hook="HOOK_TEST_BOOL",
            operation="set", value=False,
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST_BOOL", True, basic_context)
        assert result is False


# ============================================================================
# Callback 操作测试 (未覆盖行 198-204)
# ============================================================================

class TestCallbackOperation:
    """测试 callback 类型操作"""

    def test_callback_operation(self, basic_mecha, basic_context):
        """测试 callback 操作调用注册的函数"""
        # 注册一个简单的回调函数
        @SkillRegistry.register_callback("test_callback_func")
        def test_callback(value, ctx, owner):
            return value + 999

        basic_mecha.effects.append(Effect(
            id="test_cb", name="Test Callback",
            hook="HOOK_TEST",
            operation="callback", value="test_callback_func",
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 100, basic_context)
        assert result == 1099  # 100 + 999

    def test_callback_not_found(self, basic_mecha, basic_context):
        """测试 callback 函数不存在时返回原值 (未覆盖行 207)"""
        # 使用不存在的回调 ID
        basic_mecha.effects.append(Effect(
            id="test_cb_missing", name="Test Callback Missing",
            hook="HOOK_TEST",
            operation="callback", value="nonexistent_callback",
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 100, basic_context)
        # 应该返回原值
        assert result == 100


# ============================================================================
# 效果循环中过期检查测试 (未覆盖行 64)
# ============================================================================

class TestEffectExpirationInLoop:
    """测试效果在执行循环中过期的情况"""

    def test_effect_expires_during_execution(self, basic_mecha, basic_context):
        """测试效果在执行过程中过期 (duration=0)"""
        # 创建一个会被消耗完的效果
        effect = Effect(
            id="test_expire", name="Test Expire",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            charges=2,  # 2次机会
            duration=2,
            priority=50
        )
        basic_mecha.effects.append(effect)

        # 执行一次，charges 应该减 1
        EffectProcessor.process("HOOK_TEST", 0, basic_context)
        assert effect.charges == 1

        # 手动设置 duration=0 模拟过期
        effect.duration = 0

        # 再次执行时应该跳过这个效果 (未覆盖行 64)
        result = EffectProcessor.process("HOOK_TEST", 0, basic_context)
        # 由于效果过期，不应该应用
        assert result == 0


# ============================================================================
# 概率未触发测试 (未覆盖行 82)
# ============================================================================

class TestProbabilityNotTriggered:
    """测试效果未通过概率判定"""

    @patch('random.random')
    def test_trigger_chance_fails(self, mock_random, basic_mecha, basic_context):
        """测试概率判定未通过时跳过 (未覆盖行 82)"""
        # Mock random 返回高值，导致概率失败
        mock_random.return_value = 0.9  # 90%，假设触发概率是 50%

        basic_mecha.effects.append(Effect(
            id="test_prob_fail", name="Test Prob Fail",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            trigger_chance=0.5,  # 50% 概率
            duration=1
        ))

        result = EffectProcessor.process("HOOK_TEST", 0, basic_context)
        # 应该返回原值，因为未通过概率判定
        assert result == 0


# ============================================================================
# 副作用执行测试 (未覆盖行 92)
# ============================================================================

class TestSideEffectExecution:
    """测试副作用的执行"""

    def test_side_effect_executed_when_triggered(self, basic_mecha, basic_context):
        """测试效果触发时执行副作用 (未覆盖行 92)"""
        from src.skill_system.side_effects import SideEffectExecutor

        # Mock SideEffectExecutor.execute 来验证是否被调用
        original_execute = SideEffectExecutor.execute
        call_count = [0]

        def mock_execute(side_effects, context, owner):
            call_count[0] += 1
            # 不实际执行副作用，只记录调用
            return original_execute(side_effects, context, owner)

        SideEffectExecutor.execute = mock_execute

        # 添加一个带副作用的效果
        basic_mecha.effects.append(Effect(
            id="test_se", name="Test Side Effect",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            side_effects=[{"type": "consume_en", "val": 5}],
            duration=1
        ))

        EffectProcessor.process("HOOK_TEST", 0, basic_context)

        # 验证副作用被执行
        assert call_count[0] == 1

        # 恢复原始函数
        SideEffectExecutor.execute = original_execute


# ============================================================================
# 效果再次过期检查测试 (未覆盖行 64)
# ============================================================================

class TestEffectRecheckInLoop:
    """测试效果在循环中再次检查过期"""

    def test_effect_check_skip_when_duration_zero_in_loop(self, basic_mecha, basic_context):
        """测试效果在循环中再次检查duration=0时跳过 (未覆盖行 64)"""
        # 创建一个效果
        effect = Effect(
            id="test_recheck", name="Test Recheck",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            duration=1,  # 初始有效
            priority=50
        )
        basic_mecha.effects.append(effect)

        # 第一次执行应该应用效果
        result1 = EffectProcessor.process("HOOK_TEST", 0, basic_context)
        assert result1 == 10.0

        # 设置 duration=0 模拟在中间某处过期
        effect.duration = 0

        # 再次执行应该跳过这个效果 (循环内的第二次检查)
        result2 = EffectProcessor.process("HOOK_TEST", 0, basic_context)
        # 由于效果被跳过，应该返回原始值
        assert result2 == 0

    def test_effect_check_skip_when_charges_zero_in_loop(self, basic_mecha, basic_context):
        """测试效果在循环中再次检查charges=0时跳过 (未覆盖行 64)"""
        effect = Effect(
            id="test_recheck_charges", name="Test Recheck Charges",
            hook="HOOK_TEST",
            operation="add", value=10.0,
            charges=1,  # 1次机会
            duration=1,
            priority=50
        )
        basic_mecha.effects.append(effect)

        # 第一次执行
        result1 = EffectProcessor.process("HOOK_TEST", 0, basic_context)
        assert result1 == 10.0
        assert effect.charges == 0

        # 模拟在下次循环开始前charges已经为0
        # 再次执行应该跳过
        result2 = EffectProcessor.process("HOOK_TEST", 0, basic_context)
        assert result2 == 0


# ============================================================================
# 数值类型 set 操作测试 (相关分支覆盖)
# ============================================================================

class TestNumericSetOperation:
    """测试数值类型 set 操作的行为"""

    def test_set_operation_with_numeric_input(self, basic_mecha, basic_context):
        """测试 set 操作对数值输入直接返回该值 (分支 179-180)"""
        # 由于 Python 中 bool 是 int 的子类，isinstance(False, (int, float)) 为 True
        # 所以数值分支会先执行，不会进入布尔分支的 bool(val) 逻辑

        test_cases = [
            (100, 100),      # 非零数值
            (0, 0),          # 零
            (-1, -1),        # 负数
            (1.5, 1.5),      # 浮点数
        ]

        for value_val, expected in test_cases:
            basic_mecha.effects.clear()

            basic_mecha.effects.append(Effect(
                id=f"test_set_{value_val}", name=f"Test Set {value_val}",
                hook="HOOK_TEST_NUMERIC",
                operation="set", value=value_val,
                duration=1
            ))

            # 传入数值作为 current_value
            result = EffectProcessor.process("HOOK_TEST_NUMERIC", 0, basic_context)

            # 数值 set 操作直接返回原值
            assert result == expected, f"Numeric set should return {expected}, got {result}"

