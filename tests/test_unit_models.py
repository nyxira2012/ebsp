"""
单元测试: 数据模型测试
测试所有数据类的基础功能和边界条件
"""

import pytest
from src.models import (
    Mecha, Pilot, Weapon, WeaponType,
    BattleContext, Effect, Terrain, AttackResult
)


# ============================================================================
# Pilot 模型测试
# ============================================================================

class TestPilot:
    """驾驶员模型测试"""

    def test_pilot_initialization(self, basic_pilot):
        """测试驾驶员初始化"""
        assert basic_pilot.id == "p_test"
        assert basic_pilot.name == "TestPilot"
        assert basic_pilot.stat_shooting == 100
        assert basic_pilot.stat_melee == 100
        assert basic_pilot.stat_reaction == 100
        assert basic_pilot.stat_awakening == 100
        assert basic_pilot.stat_defense == 100

    def test_get_effective_stat_no_modifier(self, basic_pilot):
        """测试无修正时的属性获取"""
        assert basic_pilot.get_effective_stat('stat_shooting') == 100
        assert basic_pilot.get_effective_stat('stat_melee') == 100

    def test_get_effective_stat_with_modifier(self, basic_pilot):
        """测试有修正时的属性获取"""
        basic_pilot.stat_modifiers['stat_shooting'] = 20.0
        assert basic_pilot.get_effective_stat('stat_shooting') == 120

    def test_get_effective_stat_nonexistent(self, basic_pilot):
        """测试获取不存在的属性"""
        assert basic_pilot.get_effective_stat('nonexistent') == 0

    def test_hooks_initialization(self, basic_pilot):
        """测试钩子字典初始化"""
        assert 'HOOK_HIT_ADD' in basic_pilot.hooks
        assert 'HOOK_EVA_ADD' in basic_pilot.hooks
        assert basic_pilot.hooks['HOOK_HIT_ADD'] == 0.0


# ============================================================================
# Mecha 模型测试
# ============================================================================

class TestMecha:
    """机体模型测试"""

    def test_mecha_initialization(self, basic_mecha):
        """测试机体初始化"""
        assert basic_mecha.id == "m_test"
        assert basic_mecha.name == "TestMecha"
        assert basic_mecha.max_hp == 5000
        assert basic_mecha.current_hp == 5000
        assert basic_mecha.max_en == 100
        assert basic_mecha.current_en == 100

    def test_is_alive_true(self, basic_mecha):
        """测试存活状态 (HP>0)"""
        assert basic_mecha.is_alive() is True

    def test_is_alive_false(self):
        """测试死亡状态 (HP=0)"""
        pilot = Pilot(id="p_dead", name="DeadPilot",
                     stat_shooting=100, stat_melee=100, stat_reaction=100,
                     stat_awakening=100, stat_defense=100)
        mecha = Mecha(id="m_dead", name="DeadMecha", pilot=pilot,
                     max_hp=5000, current_hp=0,
                     max_en=100, current_en=100,
                     hit_rate=10.0, precision=10.0, crit_rate=5.0,
                     dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
                     defense_level=1000, mobility=100)
        assert mecha.is_alive() is False

    def test_get_hp_percentage(self, basic_mecha):
        """测试HP百分比计算"""
        assert basic_mecha.get_hp_percentage() == 100.0

        basic_mecha.current_hp = 2500
        assert basic_mecha.get_hp_percentage() == 50.0

        basic_mecha.current_hp = 1500
        assert basic_mecha.get_hp_percentage() == 30.0

    def test_can_attack_true(self, basic_mecha, basic_weapon):
        """测试可攻击状态 (EN足够)"""
        assert basic_mecha.can_attack(basic_weapon) is True

    def test_can_attack_false(self, basic_mecha, basic_weapon):
        """测试不可攻击状态 (EN不足)"""
        basic_mecha.current_en = 5
        assert basic_mecha.can_attack(basic_weapon) is False

    def test_consume_en_normal(self, basic_mecha):
        """测试EN消耗"""
        basic_mecha.consume_en(30)
        assert basic_mecha.current_en == 70

    def test_consume_en_to_zero(self, basic_mecha):
        """测试EN消耗到0"""
        basic_mecha.consume_en(100)
        assert basic_mecha.current_en == 0

    def test_consume_en_overdraft(self, basic_mecha):
        """测试EN过度消耗 (最低为0)"""
        basic_mecha.consume_en(150)
        assert basic_mecha.current_en == 0

    def test_take_damage_normal(self, basic_mecha):
        """测试受到伤害"""
        basic_mecha.take_damage(1000)
        assert basic_mecha.current_hp == 4000

    def test_take_damage_to_zero(self, basic_mecha):
        """测试受到伤害到0"""
        basic_mecha.take_damage(5000)
        assert basic_mecha.current_hp == 0

    def test_take_damage_overkill(self, basic_mecha):
        """测试过度伤害 (HP最低为0)"""
        basic_mecha.take_damage(10000)
        assert basic_mecha.current_hp == 0

    def test_modify_will_increase(self, basic_mecha):
        """测试气力增加"""
        initial_will = basic_mecha.current_will
        basic_mecha.modify_will(10)
        assert basic_mecha.current_will == initial_will + 10

    def test_modify_will_decrease(self, basic_mecha):
        """测试气力减少"""
        basic_mecha.modify_will(-20)
        assert basic_mecha.current_will == 100 - 20

    def test_modify_will_clamp_min(self, basic_mecha):
        """测试气力下限限制"""
        from src.config import Config
        basic_mecha.modify_will(-200)
        assert basic_mecha.current_will == Config.WILL_MIN

    def test_modify_will_clamp_max(self, basic_mecha):
        """测试气力上限限制"""
        from src.config import Config
        basic_mecha.modify_will(200)
        assert basic_mecha.current_will == Config.WILL_MAX


# ============================================================================
# Weapon 模型测试
# ============================================================================

class TestWeapon:
    """武器模型测试"""

    def test_weapon_initialization(self, basic_weapon):
        """测试武器初始化"""
        assert basic_weapon.id == "w_rifle"
        assert basic_weapon.name == "Beam Rifle"
        assert basic_weapon.weapon_type == WeaponType.RIFLE
        assert basic_weapon.power == 1000
        assert basic_weapon.en_cost == 10

    def test_can_use_at_distance_in_range(self, basic_weapon):
        """测试射程内可用"""
        assert basic_weapon.can_use_at_distance(3000) is True

    def test_can_use_at_distance_below_min(self, basic_weapon):
        """测试低于最小射程"""
        assert basic_weapon.can_use_at_distance(500) is False

    def test_can_use_at_distance_above_max(self, basic_weapon):
        """测试超过最大射程"""
        assert basic_weapon.can_use_at_distance(7000) is False

    def test_can_use_at_distance_boundary(self, basic_weapon):
        """测试射程边界"""
        assert basic_weapon.can_use_at_distance(1000) is True  # 最小射程
        assert basic_weapon.can_use_at_distance(6000) is True  # 最大射程

    def test_get_hit_modifier_normal(self, basic_weapon):
        """测试正常距离下的命中修正"""
        assert basic_weapon.get_hit_modifier_at_distance(3000) == 0.0

    def test_get_hit_modifier_out_of_range(self, basic_weapon):
        """测试超出射程的命中修正"""
        assert basic_weapon.get_hit_modifier_at_distance(8000) == -999.0

    def test_get_hit_modifier_rifle_out_of_range_low(self, rifle_weapon):
        """测试RIFLE超出射程下限（不可用）"""
        # rifle_weapon射程是1000-6000m
        result = rifle_weapon.get_hit_modifier_at_distance(800)  # 低于最小射程
        assert result == -999.0  # 超出射程，不可用

    def test_get_hit_modifier_rifle_out_of_range_high(self, rifle_weapon):
        """测试RIFLE超出射程上限（不可用）"""
        # rifle_weapon射程是1000-6000m
        result = rifle_weapon.get_hit_modifier_at_distance(7000)  # 高于最大射程
        assert result == -999.0  # 超出射程，不可用


# ============================================================================
# Effect 模型测试
# ============================================================================

class TestEffect:
    """效果模型测试"""

    def test_effect_initialization_minimal(self):
        """测试最小参数初始化"""
        effect = Effect(
            id="test_minimal",
            name="Minimal Effect",
            hook="HOOK_TEST",
            operation="add",
            value=0.0
        )
        assert effect.id == "test_minimal"
        assert effect.priority == 50  # 默认值
        assert effect.sub_priority == 500  # 默认值
        assert effect.trigger_chance == 1.0  # 默认值
        assert effect.duration == 1  # 默认值
        assert effect.charges == -1  # 默认值

    def test_effect_full_fields(self):
        """测试完整字段初始化"""
        effect = Effect(
            id="test_full",
            name="Full Effect",
            hook="HOOK_TEST",
            operation="mul",
            value=2.0,
            priority=80,
            sub_priority=600,
            trigger_chance=0.5,
            target="enemy",
            duration=3,
            charges=5,
            conditions=[{"type": "hp_threshold", "val": 0.3}],
            side_effects=[{"type": "consume_en", "val": 10}]
        )
        assert effect.priority == 80
        assert effect.sub_priority == 600
        assert effect.trigger_chance == 0.5
        assert effect.target == "enemy"
        assert effect.duration == 3
        assert effect.charges == 5
        assert len(effect.conditions) == 1
        assert len(effect.side_effects) == 1


# ============================================================================
# BattleContext 模型测试
# ============================================================================

class TestBattleContext:
    """战斗上下文测试"""

    def test_context_initialization(self, basic_context):
        """测试上下文初始化"""
        assert basic_context.round_number == 1
        assert basic_context.distance == 1000
        assert basic_context.terrain == Terrain.SPACE
        assert basic_context.attack_result is None
        assert basic_context.damage == 0

    def test_shared_state_empty_initially(self, basic_context):
        """测试共享状态初始为空"""
        assert len(basic_context.shared_state) == 0

    def test_hook_stack_empty_initially(self, basic_context):
        """测试钩子栈初始为空"""
        assert len(basic_context.hook_stack) == 0

    def test_cached_results_empty_initially(self, basic_context):
        """测试缓存结果初始为空"""
        assert len(basic_context.cached_results) == 0

    def test_shared_state_can_store(self, basic_context):
        """测试共享状态存储"""
        key = ("test_effect", "counter", "BATTLE_BASED")
        basic_context.shared_state[key] = 5
        assert basic_context.shared_state[key] == 5

    def test_hook_stack_can_push(self, basic_context):
        """测试钩子栈压入"""
        basic_context.hook_stack.append("HOOK_TEST")
        assert len(basic_context.hook_stack) == 1
        assert basic_context.hook_stack[0] == "HOOK_TEST"

    def test_cached_results_can_store(self, basic_context):
        """测试缓存结果存储"""
        basic_context.cached_results["HOOK_PRE_HIT_RATE"] = 80.0
        assert basic_context.cached_results["HOOK_PRE_HIT_RATE"] == 80.0


# ============================================================================
# 边界条件测试
# ============================================================================

class TestEdgeCases:
    """边界条件和异常情况测试"""

    def test_hp_boundary_one(self):
        """测试HP=1的边界情况"""
        pilot = Pilot(id="p_test", name="Test",
                     stat_shooting=100, stat_melee=100, stat_reaction=100,
                     stat_awakening=100, stat_defense=100)
        mecha = Mecha(id="m_test", name="Test", pilot=pilot,
                     max_hp=5000, current_hp=1,
                     max_en=100, current_en=100,
                     hit_rate=10.0, precision=10.0, crit_rate=5.0,
                     dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
                     defense_level=1000, mobility=100)
        assert mecha.is_alive() is True
        assert mecha.get_hp_percentage() == pytest.approx(0.02, rel=0.01)

    def test_en_boundary_one(self):
        """测试EN=1的边界情况"""
        pilot = Pilot(id="p_test", name="Test",
                     stat_shooting=100, stat_melee=100, stat_reaction=100,
                     stat_awakening=100, stat_defense=100)
        mecha = Mecha(id="m_test", name="Test", pilot=pilot,
                     max_hp=5000, current_hp=5000,
                     max_en=100, current_en=1,
                     hit_rate=10.0, precision=10.0, crit_rate=5.0,
                     dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
                     defense_level=1000, mobility=100)

        weapon = Weapon(id="w_test", name="Test", weapon_type=WeaponType.RIFLE,
                       power=1000, en_cost=10, range_min=1, range_max=5)
        assert mecha.can_attack(weapon) is False

    def test_negative_stat_modifier(self):
        """测试负数属性修正"""
        pilot = Pilot(id="p_test", name="Test",
                     stat_shooting=100, stat_melee=100, stat_reaction=100,
                     stat_awakening=100, stat_defense=100)
        pilot.stat_modifiers['stat_shooting'] = -30.0
        assert pilot.get_effective_stat('stat_shooting') == 70
