"""
测试: 技能回调函数
提高 skills.py 中回调函数的覆盖率
"""

import pytest
from unittest.mock import MagicMock, patch
from src.skills import (
    cb_potential,
    cb_learning,
    cb_gn_recover,
    cb_miracle_hit,
    cb_instinct_dodge,
    cb_auto_repair,
    cb_ablat,
    cb_vampirism,
    cb_rage_will,
    cb_regen_hp,
    _restore_en,
)
from src.models import AttackResult, BattleContext, WeaponType


class TestCbPotential:
    """底力回调测试"""

    def test_full_hp_no_bonus(self):
        """满 HP 时无加成"""
        owner = MagicMock()
        owner.current_hp = 1000
        owner.final_max_hp = 1000

        result = cb_potential(100, None, owner)
        assert result == 100

    def test_half_hp_some_bonus(self):
        """半血时有部分加成"""
        owner = MagicMock()
        owner.current_hp = 500
        owner.final_max_hp = 1000

        result = cb_potential(100, None, owner)
        # ratio = 0.5, bonus = 0.5 * (0.5^2) = 0.125
        assert result == pytest.approx(100.125, abs=0.01)

    def test_low_hp_max_bonus(self):
        """低血量时加成最大"""
        owner = MagicMock()
        owner.current_hp = 100
        owner.final_max_hp = 1000

        result = cb_potential(100, None, owner)
        # ratio = 0.9, bonus = 0.5 * (0.9^2) = 0.405
        assert result == pytest.approx(100.405, abs=0.01)

    def test_zero_hp_bonus(self):
        """HP 为 0 时最大加成"""
        owner = MagicMock()
        owner.current_hp = 0
        owner.final_max_hp = 1000

        result = cb_potential(100, None, owner)
        # ratio = 1.0, bonus = 0.5
        assert result == 100.5


class TestCbLearning:
    """学习电脑回调测试"""

    def test_learning_round_1(self):
        """第 1 回合"""
        ctx = MagicMock()
        ctx.round_number = 1

        result = cb_learning(50, ctx, None)
        assert result == 55  # 50 + 1 * 5

    def test_learning_round_10(self):
        """第 10 回合"""
        ctx = MagicMock()
        ctx.round_number = 10

        result = cb_learning(50, ctx, None)
        assert result == 100  # 50 + 10 * 5


class TestCbGnRecover:
    """GN炉回复测试"""

    def test_gn_recover_below_max(self):
        """EN 未满时回复"""
        owner = MagicMock()
        owner.current_en = 50
        owner.final_max_en = 100

        result = cb_gn_recover(0, None, owner)
        assert owner.current_en == 60  # 50 + 10
        assert result == 0

    def test_gn_recover_near_max(self):
        """EN 接近最大值时不会溢出"""
        owner = MagicMock()
        owner.current_en = 95
        owner.final_max_en = 100

        result = cb_gn_recover(0, None, owner)
        assert owner.current_en == 100  # min(100, 95 + 10)
        assert result == 0

    def test_gn_recover_at_max(self):
        """EN 已满时不变"""
        owner = MagicMock()
        owner.current_en = 100
        owner.final_max_en = 100

        result = cb_gn_recover(0, None, owner)
        assert owner.current_en == 100
        assert result == 0


class TestCbMiracleHit:
    """奇迹命中回调测试"""

    def test_miracle_converts_miss(self):
        """将 MISS 转为 HIT"""
        result = cb_miracle_hit(AttackResult.MISS, None, None)
        assert result == AttackResult.HIT

    def test_miracle_converts_none(self):
        """将 None 转为 HIT"""
        result = cb_miracle_hit(None, None, None)
        assert result == AttackResult.HIT

    def test_miracle_keeps_other_results(self):
        """其他结果保持不变"""
        assert cb_miracle_hit(AttackResult.HIT, None, None) == AttackResult.HIT
        assert cb_miracle_hit(AttackResult.CRIT, None, None) == AttackResult.CRIT
        assert cb_miracle_hit(AttackResult.DODGE, None, None) == AttackResult.DODGE


class TestCbInstinctDodge:
    """本能闪避回调测试"""

    def test_instinct_converts_hit_when_triggered(self):
        """触发时将 HIT 转为 DODGE"""
        ctx = MagicMock()

        with patch('random.random', return_value=0.1):  # < 0.3, 触发
            result = cb_instinct_dodge(AttackResult.HIT, ctx, None)
            assert result == AttackResult.DODGE

    def test_instinct_keeps_hit_when_not_triggered(self):
        """未触发时保持 HIT"""
        ctx = MagicMock()

        with patch('random.random', return_value=0.5):  # > 0.3, 未触发
            result = cb_instinct_dodge(AttackResult.HIT, ctx, None)
            assert result == AttackResult.HIT

    def test_instinct_keeps_other_results(self):
        """非 HIT 结果不受影响"""
        ctx = MagicMock()

        with patch('random.random', return_value=0.1):
            assert cb_instinct_dodge(AttackResult.CRIT, ctx, None) == AttackResult.CRIT
            assert cb_instinct_dodge(AttackResult.MISS, ctx, None) == AttackResult.MISS
            assert cb_instinct_dodge(AttackResult.DODGE, ctx, None) == AttackResult.DODGE

    def test_instinct_publishes_event(self):
        """触发时发布事件"""
        ctx = MagicMock()

        with patch('random.random', return_value=0.1):
            cb_instinct_dodge(AttackResult.HIT, ctx, None)

        ctx.publish_event.assert_called_once()
        event = ctx.publish_event.call_args[0][0]
        assert event.skill_id == "spirit_instinct"
        assert event.triggered is True
        assert event.effect_text == "本能闪避"


# ============================================================================
# 优先级 2 — 之前未覆盖的回调函数测试
# ============================================================================

class TestCbAutoRepair:
    """自动修复回调测试: 受到伤害后回复 20% HP"""

    def test_repairs_20_percent_of_damage(self):
        """回复造成伤害的 20%"""
        owner = MagicMock()
        owner.current_hp = 3000
        owner.final_max_hp = 5000

        result = cb_auto_repair(1000, None, owner)

        # heal = int(1000 * 0.2) = 200
        assert owner.current_hp == 3200
        assert result == 1000  # 伤害数值本身不变

    def test_repair_does_not_exceed_max_hp(self):
        """回复不超过最大 HP"""
        owner = MagicMock()
        owner.current_hp = 4900
        owner.final_max_hp = 5000

        result = cb_auto_repair(5000, None, owner)

        # heal = int(5000 * 0.2) = 1000，min(5000, 4900+1000) = 5000
        assert owner.current_hp == 5000
        assert result == 5000

    def test_repair_with_zero_damage(self):
        """零伤害时不回复"""
        owner = MagicMock()
        owner.current_hp = 2000
        owner.final_max_hp = 5000

        result = cb_auto_repair(0, None, owner)

        assert owner.current_hp == 2000
        assert result == 0


class TestCbAblat:
    """烧蚀装甲回调测试: 对特定武器类型减少 200 点伤害"""

    def test_reduces_shooting_damage(self):
        """对射击武器减少 200 伤害"""
        ctx = MagicMock()
        ctx.weapon.weapon_type = WeaponType.SHOOTING

        result = cb_ablat(1000, ctx, None)
        assert result == 800

    def test_reduces_melee_damage(self):
        """对格斗武器减少 200 伤害"""
        ctx = MagicMock()
        ctx.weapon.weapon_type = WeaponType.MELEE

        result = cb_ablat(500, ctx, None)
        assert result == 300

    def test_does_not_go_below_zero(self):
        """伤害不低于 0"""
        ctx = MagicMock()
        ctx.weapon.weapon_type = WeaponType.SHOOTING

        result = cb_ablat(100, ctx, None)
        assert result == 0

    def test_no_reduction_for_awakening_weapon(self):
        """觉醒武器不减少伤害"""
        ctx = MagicMock()
        ctx.weapon.weapon_type = WeaponType.AWAKENING

        result = cb_ablat(1000, ctx, None)
        assert result == 1000

    def test_no_weapon_in_ctx(self):
        """ctx.weapon 为 None 时不减少伤害"""
        ctx = MagicMock()
        ctx.weapon = None

        result = cb_ablat(1000, ctx, None)
        assert result == 1000


class TestCbVampirism:
    """吸血回调测试: 回复造成伤害的 10% HP"""

    def test_lifesteals_10_percent(self):
        """回复伤害的 10%"""
        owner = MagicMock()
        owner.current_hp = 2000
        owner.final_max_hp = 5000

        result = cb_vampirism(1000, None, owner)

        # heal = int(1000 * 0.1) = 100
        assert owner.current_hp == 2100
        assert result == 1000

    def test_lifesteal_does_not_exceed_max(self):
        """回复不超过最大 HP"""
        owner = MagicMock()
        owner.current_hp = 4980
        owner.final_max_hp = 5000

        result = cb_vampirism(2000, None, owner)

        # heal = 200，min(5000, 4980+200) = 5000
        assert owner.current_hp == 5000

    def test_lifesteal_zero_damage(self):
        """零伤害不回复"""
        owner = MagicMock()
        owner.current_hp = 1000
        owner.final_max_hp = 5000

        result = cb_vampirism(0, None, owner)

        assert owner.current_hp == 1000
        assert result == 0


class TestCbRageWill:
    """气魄回调测试: 造成伤害时气力+3"""

    def test_increases_will_by_3(self):
        """造成伤害时气力+3"""
        owner = MagicMock()

        result = cb_rage_will(1500, None, owner)

        owner.modify_will.assert_called_once_with(3)
        assert result == 1500  # 伤害值不变

    def test_still_calls_will_on_zero_damage(self):
        """零伤害时也触发气力增加"""
        owner = MagicMock()

        cb_rage_will(0, None, owner)
        owner.modify_will.assert_called_once_with(3)


class TestCbRegenHp:
    """再生回调测试: 每回合回复 5% HP"""

    def test_heals_5_percent_of_max_hp(self):
        """回复最大 HP 的 5%"""
        owner = MagicMock()
        owner.max_hp = 5000
        owner.final_max_hp = 5000
        owner.current_hp = 3000

        result = cb_regen_hp(0, None, owner)

        # heal = int(5000 * 0.05) = 250
        assert owner.current_hp == 3250
        assert result == 0

    def test_regen_does_not_exceed_max_hp(self):
        """回复不超过最大 HP"""
        owner = MagicMock()
        owner.max_hp = 5000
        owner.final_max_hp = 5000
        owner.current_hp = 4900

        cb_regen_hp(0, None, owner)

        # heal = 250，min(5000, 4900+250) = 5000
        assert owner.current_hp == 5000


class TestRestoreEn:
    """_restore_en 辅助函数测试"""

    def test_restores_en_below_max(self):
        """EN 未满时正常回复"""
        owner = MagicMock()
        owner.max_en = 100
        owner.current_en = 60

        _restore_en(owner, 15)

        assert owner.current_en == 75

    def test_restores_en_caps_at_max(self):
        """EN 已满时不超过上限"""
        owner = MagicMock()
        owner.max_en = 100
        owner.current_en = 90

        _restore_en(owner, 30)

        assert owner.current_en == 100
