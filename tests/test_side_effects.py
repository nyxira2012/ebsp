"""
测试副作用系统 (side_effects.py)
覆盖 SideEffectExecutor 的各种副作用执行逻辑
"""

import pytest
from src.models import Mecha, Pilot, BattleContext, Effect
from src.skill_system.side_effects import SideEffectExecutor


# ============================================================================
# Fixtures 说明
# ============================================================================
# 所有 fixtures 已移至 conftest.py，包括：
# - basic_pilot: 基础驾驶员（与原 pilot_with_stats 相同）
# - full_mecha: 满资源机体（与原 full_mecha 相同，HP/EN/Will 都是满值）
# - full_context: 满资源战斗上下文（与原 full_context 相同）
#
# 注意：测试中需要更新 fixture 名称：
# - pilot_with_stats → basic_pilot
# - full_mecha → full_mecha
# - full_context → full_context


# ============================================================================
# 测试 consume_en 副作用
# ============================================================================

class TestConsumeENSideEffect:
    """测试消耗EN副作用"""

    def test_consume_en_on_self(self, full_context, full_mecha):
        """测试对自己消耗EN"""
        side_effects = [{"type": "consume_en", "val": 20, "target": "self"}]
        initial_en = full_mecha.current_en

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_en == initial_en - 20

    def test_consume_en_on_enemy(self, full_context, full_mecha):
        """测试对敌人消耗EN"""
        side_effects = [{"type": "consume_en", "val": 15, "target": "enemy"}]
        enemy = full_context.defender
        initial_en = enemy.current_en

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert enemy.current_en == initial_en - 15
        assert full_mecha.current_en == 100  # 攻击者EN不变

    def test_consume_en_with_default_val(self, full_context, full_mecha):
        """测试消耗EN默认值为0"""
        side_effects = [{"type": "consume_en"}]
        initial_en = full_mecha.current_en

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_en == initial_en

    def test_consume_en_to_zero(self, full_context, full_mecha):
        """测试消耗EN到0"""
        full_mecha.current_en = 10
        side_effects = [{"type": "consume_en", "val": 10}]

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_en == 0

    def test_consume_en_overdraft(self, full_context, full_mecha):
        """测试超额消耗EN"""
        full_mecha.current_en = 5
        side_effects = [{"type": "consume_en", "val": 20}]

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_en == 0


# ============================================================================
# 测试 modify_will 副作用
# ============================================================================

class TestModifyWillSideEffect:
    """测试修改气力副作用"""

    def test_increase_will_on_self(self, full_context, full_mecha):
        """测试增加自己气力"""
        side_effects = [{"type": "modify_will", "val": 10, "target": "self"}]
        initial_will = full_mecha.current_will

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_will == initial_will + 10

    def test_decrease_will_on_enemy(self, full_context, full_mecha):
        """测试降低敌人气力"""
        side_effects = [{"type": "modify_will", "val": -15, "target": "enemy"}]
        enemy = full_context.defender
        enemy.current_will = 130
        initial_will = enemy.current_will

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert enemy.current_will == initial_will - 15

    def test_modify_will_clamp_at_max(self, full_context, full_mecha):
        """测试气力上限"""
        from src.config import Config
        full_mecha.current_will = Config.WILL_MAX - 5
        side_effects = [{"type": "modify_will", "val": 10}]

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_will == Config.WILL_MAX

    def test_modify_will_clamp_at_min(self, full_context, full_mecha):
        """测试气力下限"""
        full_mecha.current_will = 50
        side_effects = [{"type": "modify_will", "val": -60}]

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_will == 50  # Config.WILL_MIN

    def test_modify_will_default_val(self, full_context, full_mecha):
        """测试默认值为0"""
        side_effects = [{"type": "modify_will"}]
        initial_will = full_mecha.current_will

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_will == initial_will


# ============================================================================
# 测试 apply_effect 副作用
# ============================================================================

class TestApplyEffectSideEffect:
    """测试施加新效果副作用"""

    def test_apply_effect_on_self(self, full_context, full_mecha):
        """测试对自己施加效果"""
        side_effects = [{"type": "apply_effect", "effect_id": "buff_hit", "duration": 2, "target": "self"}]

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        # 应该添加了 buff_hit 效果（如果EffectFactory有定义）
        # 这里测试不会报错即可

    def test_apply_effect_on_enemy(self, full_context, full_mecha):
        """测试对敌人施加效果"""
        side_effects = [{"type": "apply_effect", "effect_id": "debuff_attack", "target": "enemy"}]
        enemy = full_context.defender
        initial_effects_count = len(enemy.effects)

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        # 效果数量可能增加（如果EffectFactory有定义）

    def test_apply_effect_default_duration(self, full_context, full_mecha):
        """测试默认持续时间"""
        side_effects = [{"type": "apply_effect", "effect_id": "buff_hit"}]

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

    def test_apply_effect_missing_id(self, full_context, full_mecha):
        """测试缺少effect_id不报错"""
        side_effects = [{"type": "apply_effect"}]
        initial_effects_count = len(full_mecha.effects)

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert len(full_mecha.effects) == initial_effects_count


# ============================================================================
# 测试目标选择
# ============================================================================

class TestTargetSelection:
    """测试副作用目标选择逻辑"""

    def test_target_self_when_attacker(self, full_context, full_mecha):
        """测试攻击者选择self"""
        side_effects = [{"type": "consume_en", "val": 10, "target": "self"}]
        initial_en = full_mecha.current_en

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_en == initial_en - 10

    def test_target_enemy_when_attacker(self, full_context, full_mecha):
        """测试攻击者选择enemy"""
        side_effects = [{"type": "consume_en", "val": 10, "target": "enemy"}]
        enemy = full_context.defender
        initial_en = enemy.current_en

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert enemy.current_en == initial_en - 10

    def test_target_self_when_defender(self, full_context, full_mecha):
        """测试防御者选择self"""
        enemy = full_context.defender
        side_effects = [{"type": "consume_en", "val": 10, "target": "self"}]
        initial_en = enemy.current_en

        SideEffectExecutor.execute(side_effects, full_context, enemy)

        assert enemy.current_en == initial_en - 10

    def test_target_enemy_when_defender(self, full_context, full_mecha):
        """测试防御者选择enemy"""
        enemy = full_context.defender
        side_effects = [{"type": "consume_en", "val": 10, "target": "enemy"}]
        attacker = full_context.attacker
        initial_en = attacker.current_en

        SideEffectExecutor.execute(side_effects, full_context, enemy)

        assert attacker.current_en == initial_en - 10


# ============================================================================
# 测试多个副作用组合
# ============================================================================

class TestMultipleSideEffects:
    """测试多个副作用组合执行"""

    def test_consume_en_and_modify_will(self, full_context, full_mecha):
        """测试同时消耗EN和修改气力"""
        side_effects = [
            {"type": "consume_en", "val": 15},
            {"type": "modify_will", "val": 10}
        ]
        initial_en = full_mecha.current_en
        initial_will = full_mecha.current_will

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_en == initial_en - 15
        assert full_mecha.current_will == initial_will + 10

    def test_apply_multiple_effects(self, full_context, full_mecha):
        """测试施加多个效果"""
        side_effects = [
            {"type": "consume_en", "val": 10},
            {"type": "modify_will", "val": 5},
            {"type": "consume_en", "val": 5}  # 累计消耗15
        ]
        initial_en = full_mecha.current_en

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_en == initial_en - 15

    def test_empty_side_effects_list(self, full_context, full_mecha):
        """测试空副作用列表"""
        side_effects = []
        initial_en = full_mecha.current_en

        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_en == initial_en


# ============================================================================
# 测试未知副作用类型
# ============================================================================

class TestUnknownSideEffectType:
    """测试未知副作用类型的处理"""

    def test_unknown_effect_type_ignored(self, full_context, full_mecha):
        """测试未知类型不报错"""
        side_effects = [{"type": "unknown_type", "val": 10}]
        initial_en = full_mecha.current_en

        # 应该不报错，只是忽略
        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

        assert full_mecha.current_en == initial_en


# ============================================================================
# 测试未实现的副作用
# ============================================================================

class TestUnimplementedSideEffects:
    """测试未实现的副作用（占位符）"""

    def test_consume_charges_does_nothing(self, full_context, full_mecha):
        """测试consume_charges未实现"""
        side_effects = [{"type": "consume_charges", "val": 1}]

        # 不应该报错
        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

    def test_modify_stat_does_nothing(self, full_context, full_mecha):
        """测试modify_stat未实现"""
        side_effects = [{"type": "modify_stat", "stat": "attack", "val": 10}]

        # 不应该报错
        SideEffectExecutor.execute(side_effects, full_context, full_mecha)


# ============================================================================
# 测试边界条件
# ============================================================================

class TestEdgeCases:
    """测试边界条件"""

    def test_side_effect_with_no_target_available(self, full_context, full_mecha):
        """测试无目标情况"""
        # 创建一个没有明确指向的上下文
        side_effects = [{"type": "consume_en", "val": 10, "target": "invalid_target"}]

        # 应该不报错
        SideEffectExecutor.execute(side_effects, full_context, full_mecha)

    def test_side_effect_with_none_context(self, full_mecha):
        """测试context为None的情况"""
        side_effects = [{"type": "modify_will", "val": 10}]
        initial_will = full_mecha.current_will

        # 应该不报错（虽然可能无法正确处理target=enemy）
        SideEffectExecutor.execute(side_effects, None, full_mecha)

        # self目标应该仍然工作
        assert full_mecha.current_will == initial_will + 10

    def test_side_effect_malformed_data(self, full_context, full_mecha):
        """测试格式错误的副作用数据"""
        side_effects = [{}]  # 完全空的副作用

        # 应该不报错
        SideEffectExecutor.execute(side_effects, full_context, full_mecha)
