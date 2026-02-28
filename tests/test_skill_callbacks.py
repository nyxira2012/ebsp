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
    cb_instinct_dodge
)
from src.models import AttackResult, BattleContext


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
