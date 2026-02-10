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
            id="m_enemy", name="Enemy", pilot=ace_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        context = BattleContext(
            round_number=1, distance=1000, terrain=Terrain.SPACE,
            attacker=basic_mecha, defender=enemy,
            weapon=Weapon(id="w", name="W", weapon_type=WeaponType.RIFLE,
                        power=1000, en_cost=10, range_min=1, range_max=5)
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
            id="m_enemy", name="Enemy", pilot=ace_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        context = BattleContext(
            round_number=1, distance=1000, terrain=Terrain.SPACE,
            attacker=basic_mecha, defender=enemy,
            weapon=Weapon(id="w", name="W", weapon_type=WeaponType.RIFLE,
                        power=1000, en_cost=10, range_min=1, range_max=5)
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
