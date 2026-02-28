"""
测试: 战斗引擎边界情况和完整流程
提高 engine.py 的覆盖率，特别是先手判定和边界情况
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from src.combat.engine import InitiativeCalculator, InitiativeReason
from src.models import Mecha


class TestInitiativeResolverSkillHooks:
    """先手判定技能钩子测试"""

    @patch('src.combat.engine.SkillRegistry')
    def test_force_initiative_a(self, mock_registry):
        """测试技能强制先手 - A方"""
        resolver = InitiativeCalculator()
        mecha_a = MagicMock(spec=Mecha)
        mecha_b = MagicMock(spec=Mecha)

        # 模拟技能强制先手
        mock_registry.process_hook.side_effect = lambda hook, val, ctx: True if hook == "HOOK_INITIATIVE_CHECK" and ctx.mecha_a == mecha_a else val

        result = resolver.resolve(mecha_a, mecha_b, round_number=1)

        assert result[0] == mecha_a
        assert result[2] == InitiativeReason.PERFORMANCE

    @patch('src.combat.engine.SkillRegistry')
    def test_force_initiative_b(self, mock_registry):
        """测试技能强制先手 - B方"""
        resolver = InitiativeCalculator()
        mecha_a = MagicMock(spec=Mecha)
        mecha_b = MagicMock(spec=Mecha)

        # 模拟 B 方技能强制先手
        def side_effect(hook, val, ctx):
            if hook == "HOOK_INITIATIVE_CHECK" and ctx.mecha_a == mecha_b:
                return True
            return val

        mock_registry.process_hook.side_effect = side_effect

        result = resolver.resolve(mecha_a, mecha_b, round_number=1)

        assert result[0] == mecha_b
        assert result[2] == InitiativeReason.PERFORMANCE


class TestInitiativeResolverScoreCalculation:
    """先手得分计算测试"""

    @patch('src.combat.engine.SkillRegistry')
    @patch('random.uniform')
    def test_initiative_score_calculation(self, mock_uniform, mock_registry):
        """测试先手得分计算"""
        mock_uniform.return_value = 0
        mock_registry.process_hook.side_effect = lambda h, v, c: v

        resolver = InitiativeCalculator()
        mecha_a = MagicMock(spec=Mecha)
        mecha_a.final_mobility = 100
        mecha_a.pilot_stats_backup = {'stat_reaction': 50}
        mecha_a.current_will = 110

        mecha_b = MagicMock(spec=Mecha)
        mecha_b.final_mobility = 80
        mecha_b.pilot_stats_backup = {'stat_reaction': 40}
        mecha_b.current_will = 100

        result = resolver.resolve(mecha_a, mecha_b, round_number=1)

        # A 应该获胜 (更高的机动和反应)
        assert result[0] == mecha_a

    @patch('src.combat.engine.SkillRegistry')
    @patch('random.uniform')
    def test_initiative_b_wins_by_score(self, mock_uniform, mock_registry):
        """测试 B 方通过得分获胜"""
        mock_uniform.return_value = 0
        mock_registry.process_hook.side_effect = lambda h, v, c: v

        resolver = InitiativeCalculator()
        mecha_a = MagicMock(spec=Mecha)
        mecha_a.final_mobility = 80
        mecha_a.pilot_stats_backup = {'stat_reaction': 40}
        mecha_a.current_will = 100

        mecha_b = MagicMock(spec=Mecha)
        mecha_b.final_mobility = 100
        mecha_b.pilot_stats_backup = {'stat_reaction': 50}
        mecha_b.current_will = 110

        result = resolver.resolve(mecha_a, mecha_b, round_number=1)

        # B 应该获胜
        assert result[0] == mecha_b


class TestInitiativeReasonDetermination:
    """先手原因判定测试"""

    @patch('src.combat.engine.SkillRegistry')
    @patch('random.uniform')
    def test_reason_by_mobility(self, mock_uniform, mock_registry):
        """测试机动性差异导致的先手"""
        mock_uniform.return_value = 0
        mock_registry.process_hook.side_effect = lambda h, v, c: v

        resolver = InitiativeCalculator()
        mecha_a = MagicMock(spec=Mecha)
        mecha_a.final_mobility = 150  # 高机动
        mecha_a.pilot_stats_backup = {'stat_reaction': 50}
        mecha_a.current_will = 100

        mecha_b = MagicMock(spec=Mecha)
        mecha_b.final_mobility = 100  # 低 50 点
        mecha_b.pilot_stats_backup = {'stat_reaction': 50}
        mecha_b.current_will = 100

        result = resolver.resolve(mecha_a, mecha_b, round_number=1)

        assert result[2] == InitiativeReason.PERFORMANCE

    @patch('src.combat.engine.SkillRegistry')
    @patch('random.uniform')
    def test_reason_by_reaction(self, mock_uniform, mock_registry):
        """测试反应值差异导致的先手"""
        mock_uniform.return_value = 0
        mock_registry.process_hook.side_effect = lambda h, v, c: v

        resolver = InitiativeCalculator()
        mecha_a = MagicMock(spec=Mecha)
        mecha_a.final_mobility = 100
        mecha_a.pilot_stats_backup = {'stat_reaction': 80}  # 高反应
        mecha_a.current_will = 100

        mecha_b = MagicMock(spec=Mecha)
        mecha_b.final_mobility = 100
        mecha_b.pilot_stats_backup = {'stat_reaction': 60}  # 低 20 点 (超过 15)
        mecha_b.current_will = 100

        result = resolver.resolve(mecha_a, mecha_b, round_number=1)

        assert result[2] == InitiativeReason.PILOT

    @patch('src.combat.engine.SkillRegistry')
    @patch('random.uniform')
    def test_reason_by_will(self, mock_uniform, mock_registry):
        """测试气力差异导致的先手"""
        mock_uniform.return_value = 0
        mock_registry.process_hook.side_effect = lambda h, v, c: v

        resolver = InitiativeCalculator()
        mecha_a = MagicMock(spec=Mecha)
        mecha_a.final_mobility = 100
        mecha_a.pilot_stats_backup = {'stat_reaction': 50}
        mecha_a.current_will = 150  # 高气力

        mecha_b = MagicMock(spec=Mecha)
        mecha_b.final_mobility = 100
        mecha_b.pilot_stats_backup = {'stat_reaction': 50}
        mecha_b.current_will = 120  # 低 30 点 (超过 20)

        result = resolver.resolve(mecha_a, mecha_b, round_number=1)

        assert result[2] == InitiativeReason.ADVANTAGE


class TestInitiativeTieBreaking:
    """先手平局处理测试"""

    @patch('src.combat.engine.SkillRegistry')
    @patch('random.uniform')
    def test_tie_breaker_counter_first_round(self, mock_uniform, mock_registry):
        """测试第一回合平局处理"""
        mock_uniform.return_value = 0
        mock_registry.process_hook.side_effect = lambda h, v, c: v

        resolver = InitiativeCalculator()
        # 相同属性导致平局
        mecha_a = MagicMock(spec=Mecha)
        mecha_a.final_mobility = 100
        mecha_a.pilot_stats_backup = {'stat_reaction': 50}
        mecha_a.current_will = 100

        mecha_b = MagicMock(spec=Mecha)
        mecha_b.final_mobility = 100
        mecha_b.pilot_stats_backup = {'stat_reaction': 50}
        mecha_b.current_will = 100

        result = resolver.resolve(mecha_a, mecha_b, round_number=1)

        # 第一回合平局后，A 获得先手 (因为 last_winner 默认为 '')
        assert result[2] == InitiativeReason.COUNTER

    @patch('src.combat.engine.SkillRegistry')
    @patch('random.uniform')
    def test_tie_breaker_alternates(self, mock_uniform, mock_registry):
        """测试平局交替处理"""
        mock_uniform.return_value = 0
        mock_registry.process_hook.side_effect = lambda h, v, c: v

        resolver = InitiativeCalculator()
        mecha_a = MagicMock(spec=Mecha)
        mecha_a.final_mobility = 100
        mecha_a.pilot_stats_backup = {'stat_reaction': 50}
        mecha_a.current_will = 100

        mecha_b = MagicMock(spec=Mecha)
        mecha_b.final_mobility = 100
        mecha_b.pilot_stats_backup = {'stat_reaction': 50}
        mecha_b.current_will = 100

        # 第一回合 A 获胜
        result1 = resolver.resolve(mecha_a, mecha_b, round_number=1)
        resolver._update_winner('A')

        # 第二回合平局，B 应该获得先手
        result2 = resolver.resolve(mecha_a, mecha_b, round_number=2)
        assert result2[0] == mecha_b


class TestInitiativeResolverUpdateWinner:
    """胜利者更新测试"""

    def test_update_winner_a(self):
        """测试更新 A 为胜者"""
        resolver = InitiativeCalculator()
        resolver._update_winner('A')
        assert resolver.last_winner == 'A'

    def test_update_winner_b(self):
        """测试更新 B 为胜者"""
        resolver = InitiativeCalculator()
        resolver._update_winner('B')
        assert resolver.last_winner == 'B'

    def test_winner_persists_across_rounds(self):
        """测试胜者记录跨回合保持"""
        resolver = InitiativeCalculator()
        resolver._update_winner('A')
        resolver._update_winner('B')
        assert resolver.last_winner == 'B'
