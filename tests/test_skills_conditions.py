"""
单元测试: 技能系统 - 条件检查器测试
测试所有条件类型的触发逻辑和边界条件
"""

import pytest
from src.models import Mecha, BattleContext, Effect, AttackResult, Weapon, WeaponType, Terrain
from src.skill_system.conditions import ConditionChecker


# ============================================================================
# HP阈值条件测试
# ============================================================================

class TestHPThresholdCondition:
    """HP阈值条件测试"""

    def test_hp_below_threshold(self, low_hp_mecha, basic_context):
        """测试HP低于阈值 (30% HP, 条件<30%应触发)"""
        # low_hp_mecha has 30% HP
        low_hp_mecha.current_hp = 1400  # 28%

        condition = {"type": "hp_threshold", "val": 0.3, "op": "<"}
        assert ConditionChecker.check([condition], basic_context, low_hp_mecha) is True

    def test_hp_equals_threshold(self, low_hp_mecha, basic_context):
        """测试HP等于阈值"""
        low_hp_mecha.current_hp = 1500  # 30%

        condition = {"type": "hp_threshold", "val": 0.3, "op": "<"}
        assert ConditionChecker.check([condition], basic_context, low_hp_mecha) is False

    def test_hp_above_threshold(self, low_hp_mecha, basic_context):
        """测试HP高于阈值"""
        low_hp_mecha.current_hp = 2000  # 40%

        condition = {"type": "hp_threshold", "val": 0.3, "op": "<"}
        assert ConditionChecker.check([condition], basic_context, low_hp_mecha) is False

    def test_hp_greater_than_or_equal(self, low_hp_mecha, basic_context):
        """测试HP大于等于阈值"""
        low_hp_mecha.current_hp = 1500  # 30%

        condition = {"type": "hp_threshold", "val": 0.3, "op": ">="}
        assert ConditionChecker.check([condition], basic_context, low_hp_mecha) is True

    @pytest.mark.parametrize("hp_pct,threshold,op,expected", [
        (0.25, 0.3, "<", True),   # 25% < 30%
        (0.30, 0.3, "<", False),  # 30% < 30% (false)
        (0.35, 0.3, "<", False),  # 35% < 30% (false)
        (0.35, 0.3, ">=", True),  # 35% >= 30%
        (0.30, 0.3, ">=", True),  # 30% >= 30%
        (0.25, 0.3, ">=", False), # 25% >= 30% (false)
    ])
    def test_hp_threshold_parametrized(self, hp_pct, threshold, op, expected, basic_mecha, basic_context):
        """参数化测试HP阈值条件"""
        basic_mecha.current_hp = int(basic_mecha.max_hp * hp_pct)
        condition = {"type": "hp_threshold", "val": threshold, "op": op}
        assert ConditionChecker.check([condition], basic_context, basic_mecha) == expected


# ============================================================================
# 气力阈值条件测试
# ============================================================================

class TestWillThresholdCondition:
    """气力阈值条件测试"""

    def test_will_above_threshold(self, high_will_mecha, basic_context):
        """测试气力高于阈值"""
        condition = {"type": "will_threshold", "val": 130, "op": ">="}
        assert ConditionChecker.check([condition], basic_context, high_will_mecha) is True

    def test_will_below_threshold(self, basic_mecha, basic_context):
        """测试气力低于阈值"""
        condition = {"type": "will_threshold", "val": 130, "op": ">="}
        assert ConditionChecker.check([condition], basic_context, basic_mecha) is False

    @pytest.mark.parametrize("will,threshold,op,expected", [
        (150, 130, ">=", True),
        (130, 130, ">=", True),
        (129, 130, ">=", False),
        (100, 130, "<", True),
        (130, 130, "<", False),
    ])
    def test_will_threshold_parametrized(self, will, threshold, op, expected, basic_mecha, basic_context):
        """参数化测试气力阈值条件"""
        basic_mecha.current_will = will
        condition = {"type": "will_threshold", "val": threshold, "op": op}
        assert ConditionChecker.check([condition], basic_context, basic_mecha) == expected


# ============================================================================
# 回合数条件测试
# ============================================================================

class TestRoundNumberCondition:
    """回合数条件测试"""

    def test_round_equals(self, basic_context):
        """测试回合数等于"""
        condition = {"type": "round_number", "val": 1, "op": "=="}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is True

    def test_round_greater_than(self, basic_context):
        """测试回合数大于"""
        basic_context.round_number = 3
        condition = {"type": "round_number", "val": 2, "op": ">"}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is True

    @pytest.mark.parametrize("round_num,threshold,op,expected", [
        (1, 1, "==", True),
        (1, 2, "==", False),
        (3, 2, ">", True),
        (3, 3, ">", False),
        (3, 5, "<", True),
        (5, 5, "<", False),
    ])
    def test_round_number_parametrized(self, round_num, threshold, op, expected, basic_context):
        """参数化测试回合数条件"""
        basic_context.round_number = round_num
        condition = {"type": "round_number", "val": threshold, "op": op}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) == expected


# ============================================================================
# 攻击结果条件测试
# ============================================================================

class TestAttackResultCondition:
    """攻击结果条件测试"""

    def test_result_single_match(self, basic_context):
        """测试单个结果匹配"""
        basic_context.attack_result = AttackResult.HIT
        condition = {"type": "attack_result", "val": "HIT"}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is True

    def test_result_single_no_match(self, basic_context):
        """测试单个结果不匹配"""
        basic_context.attack_result = AttackResult.MISS
        condition = {"type": "attack_result", "val": "HIT"}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is False

    def test_result_list_match(self, basic_context):
        """测试结果列表匹配"""
        basic_context.attack_result = AttackResult.CRIT
        condition = {"type": "attack_result", "val": ["HIT", "CRIT"]}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is True

    def test_result_list_no_match(self, basic_context):
        """测试结果列表不匹配"""
        basic_context.attack_result = AttackResult.MISS
        condition = {"type": "attack_result", "val": ["HIT", "CRIT"]}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is False

    def test_result_none(self, basic_context):
        """测试结果为None"""
        basic_context.attack_result = None
        condition = {"type": "attack_result", "val": "HIT"}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is False


# ============================================================================
# 敌方气力条件测试
# ============================================================================

class TestEnemyWillThresholdCondition:
    """敌方气力条件测试"""

    def test_enemy_will_low(self, basic_mecha, ace_pilot):
        """测试敌方气力低"""
        # 创建一个低气力的敌方机体
        enemy = Mecha(
            id="m_enemy", name="Enemy", pilot=ace_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100,
            current_will=80  # 低气力
        )

        basic_context = BattleContext(
            round_number=1, distance=1000, terrain=Terrain.SPACE,
            attacker=basic_mecha, defender=enemy,
            weapon=Weapon(id="w", name="W", weapon_type=WeaponType.RIFLE,
                        power=1000, en_cost=10, range_min=1, range_max=5)
        )

        condition = {"type": "enemy_will_threshold", "val": 100, "op": "<"}
        assert ConditionChecker.check([condition], basic_context, basic_mecha) is True


# ============================================================================
# 敌方属性条件测试
# ============================================================================

class TestEnemyStatCheckCondition:
    """敌方属性条件测试"""

    def test_enemy_stat_check(self, basic_mecha, ace_pilot):
        """测试敌方属性检查"""
        # 创建一个高射击的敌方机体
        enemy = Mecha(
            id="m_enemy", name="Enemy", pilot=ace_pilot,  # ace_pilot有180射击
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100
        )

        basic_context = BattleContext(
            round_number=1, distance=1000, terrain=Terrain.SPACE,
            attacker=basic_mecha, defender=enemy,
            weapon=Weapon(id="w", name="W", weapon_type=WeaponType.RIFLE,
                        power=1000, en_cost=10, range_min=1, range_max=5)
        )

        condition = {"type": "enemy_stat_check", "stat": "stat_shooting", "val": 150, "op": ">"}
        assert ConditionChecker.check([condition], basic_context, basic_mecha) is True


# ============================================================================
# 跨钩子引用条件测试
# ============================================================================

class TestRefHookCondition:
    """跨钩子引用条件测试"""

    def test_ref_hook_cached(self, basic_context):
        """测试跨钩子引用 (已缓存)"""
        # 模拟已缓存的结果
        basic_context.cached_results["HOOK_PRE_HIT_RATE"] = 85.0

        condition = {"type": "ref_hook", "ref_hook": "HOOK_PRE_HIT_RATE", "val": 80, "op": ">"}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is True

    def test_ref_hook_not_cached(self, basic_context):
        """测试跨钩子引用 (未缓存)"""
        # 没有缓存这个钩子的结果
        condition = {"type": "ref_hook", "ref_hook": "HOOK_PRE_HIT_RATE", "val": 80, "op": ">"}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is False


# ============================================================================
# 武器类型条件测试
# ============================================================================

class TestWeaponTypeCondition:
    """武器类型条件测试"""

    def test_weapon_type_melee(self, basic_context, melee_weapon):
        """测试格斗武器类型"""
        basic_context.weapon = melee_weapon
        condition = {"type": "weapon_type", "val": "MELEE"}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is True

    def test_weapon_type_rifle(self, basic_context, rifle_weapon):
        """测试射击武器类型"""
        basic_context.weapon = rifle_weapon
        condition = {"type": "weapon_type", "val": "RIFLE"}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is True

    def test_weapon_type_no_match(self, basic_context, melee_weapon):
        """测试武器类型不匹配"""
        basic_context.weapon = melee_weapon
        condition = {"type": "weapon_type", "val": "RIFLE"}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is False

    def test_weapon_no_weapon(self, basic_context):
        """测试无武器"""
        basic_context.weapon = None
        condition = {"type": "weapon_type", "val": "RIFLE"}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is False


# ============================================================================
# 伤害阈值条件测试
# ============================================================================

class TestDamageBelowCondition:
    """伤害阈值条件测试"""

    def test_damage_below_threshold(self, basic_context):
        """测试伤害低于阈值"""
        basic_context.damage = 1500
        condition = {"type": "damage_below", "val": 2000}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is True

    def test_damage_above_threshold(self, basic_context):
        """测试伤害高于阈值"""
        basic_context.damage = 2500
        condition = {"type": "damage_below", "val": 2000}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is False

    def test_damage_equals_threshold(self, basic_context):
        """测试伤害等于阈值 (不应触发，因为是<)"""
        basic_context.damage = 2000
        condition = {"type": "damage_below", "val": 2000}
        assert ConditionChecker.check([condition], basic_context, basic_context.attacker) is False


# ============================================================================
# 组合条件测试
# ============================================================================

class TestCombinedConditions:
    """组合条件测试 (AND逻辑)"""

    def test_both_conditions_met(self, low_hp_mecha, basic_context):
        """测试两个条件都满足"""
        low_hp_mecha.current_hp = 1400  # 28%
        low_hp_mecha.current_will = 140

        conditions = [
            {"type": "hp_threshold", "val": 0.3, "op": "<"},
            {"type": "will_threshold", "val": 130, "op": ">="}
        ]
        assert ConditionChecker.check(conditions, basic_context, low_hp_mecha) is True

    def test_one_condition_fails(self, low_hp_mecha, basic_context):
        """测试一个条件不满足"""
        low_hp_mecha.current_hp = 1400  # 28%
        low_hp_mecha.current_will = 120  # 气力不足

        conditions = [
            {"type": "hp_threshold", "val": 0.3, "op": "<"},
            {"type": "will_threshold", "val": 130, "op": ">="}
        ]
        assert ConditionChecker.check(conditions, basic_context, low_hp_mecha) is False

    def test_empty_conditions(self, basic_mecha, basic_context):
        """测试空条件列表 (应返回True)"""
        assert ConditionChecker.check([], basic_context, basic_mecha) is True

    def test_unknown_condition_type(self, basic_mecha, basic_context):
        """测试未知条件类型"""
        condition = {"type": "unknown_type", "val": 100}
        assert ConditionChecker.check([condition], basic_context, basic_mecha) is False


# ============================================================================
# 目标选择测试
# ============================================================================

class TestTargetSelection:
    """目标选择测试"""

    def test_target_self_default(self, basic_mecha, basic_context):
        """测试默认目标是self"""
        basic_mecha.current_will = 150
        condition = {"type": "will_threshold", "val": 130, "op": ">=", "target": "self"}
        assert ConditionChecker.check([condition], basic_context, basic_mecha) is True

    def test_target_enemy_as_attacker(self, basic_mecha, ace_pilot):
        """测试作为攻击方检查敌方"""
        enemy = Mecha(
            id="m_enemy", name="Enemy", pilot=ace_pilot,
            max_hp=5000, current_hp=5000,
            max_en=100, current_en=100,
            hit_rate=10.0, precision=10.0, crit_rate=5.0,
            dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
            defense_level=1000, mobility=100,
            current_will=80
        )

        basic_context = BattleContext(
            round_number=1, distance=1000, terrain=Terrain.SPACE,
            attacker=basic_mecha, defender=enemy,
            weapon=Weapon(id="w", name="W", weapon_type=WeaponType.RIFLE,
                        power=1000, en_cost=10, range_min=1, range_max=5)
        )

        condition = {"type": "will_threshold", "val": 100, "op": "<", "target": "enemy"}
        assert ConditionChecker.check([condition], basic_context, basic_mecha) is True
