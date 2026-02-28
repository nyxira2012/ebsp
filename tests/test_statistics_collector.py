"""
测试: 战斗统计收集器 (StatisticsCollector)
提高 statistics_collector.py 的覆盖率 (0% -> 目标 >90%)
"""

import pytest
from src.combat.statistics_collector import (
    StatisticsCollector,
    AttackRecord,
    RoundSnapshot,
    BattleStatistics
)
from src.presentation.models import RawAttackEvent
from src.models import AttackResult


class TestBattleStatistics:
    """BattleStatistics 数据类测试"""

    def test_finalize_with_no_damage(self):
        """测试 finalize: 无伤害时将 min_single_damage 设为 0"""
        stats = BattleStatistics()
        stats.finalize()
        assert stats.min_single_damage == 0

    def test_finalize_with_damage(self):
        """测试 finalize: 有伤害时保持 min_single_damage"""
        stats = BattleStatistics()
        stats.min_single_damage = 100
        stats.finalize()
        assert stats.min_single_damage == 100


class TestStatisticsCollectorInit:
    """统计收集器初始化测试"""

    def test_default_init(self):
        """测试默认初始化"""
        collector = StatisticsCollector()
        assert collector.battle_id == 0
        assert collector.mecha_a_id == ""
        assert collector.mecha_b_id == ""
        assert collector.enable_detailed_records is False
        assert collector._roll_value == 0.0

    def test_custom_init(self):
        """测试自定义初始化"""
        collector = StatisticsCollector(
            battle_id=1,
            mecha_a_id="mech_a",
            mecha_b_id="mech_b",
            enable_detailed_records=True
        )
        assert collector.battle_id == 1
        assert collector.mecha_a_id == "mech_a"
        assert collector.mecha_b_id == "mech_b"
        assert collector.enable_detailed_records is True


class TestStatisticsCollectorRoundContext:
    """回合上下文测试"""

    def test_set_round_context(self):
        """测试设置回合上下文"""
        collector = StatisticsCollector()
        collector.set_round_context(
            round_number=5,
            distance=3,
            first_mover="mech_a",
            initiative_reason="PERFORMANCE"
        )
        assert collector._current_round == 5
        assert collector._current_distance == 3
        assert collector._current_first_mover == "mech_a"
        assert collector._current_initiative_reason == "PERFORMANCE"

    def test_set_roll_value(self):
        """测试设置 roll 值"""
        collector = StatisticsCollector()
        collector.set_roll_value(75.5)
        assert collector._roll_value == 75.5


class TestStatisticsCollectorAttackEvent:
    """攻击事件处理测试"""

    def create_test_event(self, **kwargs) -> RawAttackEvent:
        """创建测试用的 RawAttackEvent"""
        defaults = {
            'round_number': 1,
            'attacker_id': 'mech_a',
            'defender_id': 'mech_b',
            'attacker_name': 'Attacker',
            'defender_name': 'Defender',
            'weapon_id': 'wpn_001',
            'weapon_name': 'Beam Rifle',
            'weapon_type': 'beam',
            'weapon_tags': ['ranged', 'beam'],
            'attack_result': 'HIT',
            'damage': 1000,
            'distance': 2,
            'attacker_will_delta': 1,
            'defender_will_delta': -1,
            'triggered_skills': ['skill_1'],
            'is_first_attack': True,
            'initiative_holder': 'mech_a'
        }
        defaults.update(kwargs)
        return RawAttackEvent(**defaults)

    def test_on_attack_event_basic(self):
        """测试基础攻击事件处理"""
        collector = StatisticsCollector(mecha_a_id='mech_a', mecha_b_id='mech_b')
        event = self.create_test_event()

        collector.on_attack_event(event)

        assert collector.stats.attack_results['HIT'] == 1
        assert collector.stats.total_damage_dealt == 1000
        assert collector.stats.max_single_damage == 1000
        assert collector.stats.min_single_damage == 1000

    def test_on_attack_event_boss_damage(self):
        """测试 Boss 攻击造成的伤害统计"""
        collector = StatisticsCollector(mecha_a_id='mech_a', mecha_b_id='mech_b')
        event = self.create_test_event(
            attacker_id='mech_b',
            defender_id='mech_a',
            attack_result='CRIT',
            damage=2000
        )

        collector.on_attack_event(event)

        assert collector.stats.boss_attack_results['CRIT'] == 1
        assert collector.stats.total_damage_taken == 2000
        assert collector.stats.challenger_attack_results['CRIT'] == 0

    def test_on_attack_event_multiple_results(self):
        """测试多种攻击结果统计"""
        collector = StatisticsCollector(mecha_a_id='mech_a', mecha_b_id='mech_b')

        # 多种攻击结果
        results = ['HIT', 'HIT', 'CRIT', 'MISS', 'DODGE']
        for i, result in enumerate(results):
            event = self.create_test_event(
                attack_result=result,
                damage=500 if result in ['HIT', 'CRIT'] else 0
            )
            collector.on_attack_event(event)

        assert collector.stats.attack_results['HIT'] == 2
        assert collector.stats.attack_results['CRIT'] == 1
        assert collector.stats.attack_results['MISS'] == 1
        assert collector.stats.attack_results['DODGE'] == 1

    def test_on_attack_event_damage_bounds(self):
        """测试伤害极值记录"""
        collector = StatisticsCollector(mecha_a_id='mech_a', mecha_b_id='mech_b')

        # 最小伤害
        event1 = self.create_test_event(damage=100)
        collector.on_attack_event(event1)

        # 最大伤害
        event2 = self.create_test_event(damage=5000)
        collector.on_attack_event(event2)

        # 中间伤害
        event3 = self.create_test_event(damage=1000)
        collector.on_attack_event(event3)

        assert collector.stats.max_single_damage == 5000
        assert collector.stats.min_single_damage == 100

    def test_on_attack_event_skill_stats(self):
        """测试技能触发统计"""
        collector = StatisticsCollector(mecha_a_id='mech_a', mecha_b_id='mech_b')
        event = self.create_test_event(triggered_skills=['skill_a', 'skill_b'])

        collector.on_attack_event(event)

        assert 'skill_a' in collector.stats.skill_trigger_stats
        assert 'skill_b' in collector.stats.skill_trigger_stats
        assert collector.stats.skill_trigger_stats['skill_a']['success'] == 1

    def test_on_attack_event_no_skills(self):
        """测试无技能触发的情况"""
        collector = StatisticsCollector(mecha_a_id='mech_a', mecha_b_id='mech_b')
        event = self.create_test_event(triggered_skills=[])

        collector.on_attack_event(event)

        assert collector.stats.skill_trigger_stats == {}

    def test_on_attack_event_detailed_records(self):
        """测试详细攻击记录"""
        collector = StatisticsCollector(
            mecha_a_id='mech_a',
            mecha_b_id='mech_b',
            enable_detailed_records=True
        )
        collector.set_roll_value(88.5)
        event = self.create_test_event()

        collector.on_attack_event(event)

        assert len(collector.stats.attack_records) == 1
        record = collector.stats.attack_records[0]
        assert record.round_number == 1
        assert record.attacker_id == 'mech_a'
        assert record.damage == 1000
        assert record.roll_value == 88.5

    def test_on_attack_event_no_detailed_records(self):
        """测试关闭详细记录时"""
        collector = StatisticsCollector(
            mecha_a_id='mech_a',
            mecha_b_id='mech_b',
            enable_detailed_records=False
        )
        event = self.create_test_event()

        collector.on_attack_event(event)

        assert len(collector.stats.attack_records) == 0


class TestStatisticsCollectorResourceTracking:
    """资源追踪测试"""

    def test_on_en_consumed(self):
        """测试 EN 消耗记录"""
        collector = StatisticsCollector()
        collector.on_en_consumed(20)
        collector.on_en_consumed(15)

        assert collector.stats.total_en_consumed == 35

    def test_on_en_regened(self):
        """测试 EN 回复记录"""
        collector = StatisticsCollector()
        collector.on_en_regened(10)
        collector.on_en_regened(5)

        assert collector.stats.total_en_regened == 15

    def test_on_will_changed(self):
        """测试气力变化记录"""
        collector = StatisticsCollector()
        collector.on_will_changed(1, 105)
        collector.on_will_changed(2, 110)
        collector.on_will_changed(3, 115)

        assert len(collector.stats.will_changes) == 3
        assert collector.stats.will_changes[1] == (2, 110)


class TestStatisticsCollectorRoundEnd:
    """回合结束处理测试"""

    def test_on_round_end(self):
        """测试回合结束快照记录"""
        collector = StatisticsCollector()
        collector.set_round_context(
            round_number=3,
            distance=5,
            first_mover="mech_a",
            initiative_reason="PILOT"
        )

        collector.on_round_end(
            mecha_a_hp=5000, mecha_a_en=100, mecha_a_will=120,
            mecha_b_hp=3000, mecha_b_en=80, mecha_b_will=110
        )

        assert len(collector.stats.round_snapshots) == 1
        snapshot = collector.stats.round_snapshots[0]
        assert snapshot.round_number == 3
        assert snapshot.distance == 5
        assert snapshot.mecha_a_hp == 5000
        assert snapshot.mecha_b_will == 110


class TestStatisticsCollectorFinalization:
    """战斗结算测试"""

    def test_finalize_battle(self):
        """测试战斗结算"""
        collector = StatisticsCollector(battle_id=42)

        result = collector.finalize_battle(
            rounds=15,
            winner="mech_a",
            end_reason="KNOCKOUT"
        )

        assert result.battle_id == 42
        assert result.rounds == 15
        assert result.winner == "mech_a"
        assert result.end_reason == "KNOCKOUT"

    def test_get_statistics(self):
        """测试获取统计数据"""
        collector = StatisticsCollector()
        collector.stats.total_damage_dealt = 9999

        stats = collector.get_statistics()

        assert stats.total_damage_dealt == 9999

    def test_reset(self):
        """测试重置收集器"""
        collector = StatisticsCollector(battle_id=5)
        collector.stats.total_damage_dealt = 1000
        collector._roll_value = 50.0

        collector.reset()

        assert collector.stats.total_damage_dealt == 0
        assert collector._roll_value == 0.0
        assert collector.stats.battle_id == 5  # battle_id 保留


class TestAttackRecord:
    """AttackRecord 数据类测试"""

    def test_attack_record_creation(self):
        """测试攻击记录创建"""
        record = AttackRecord(
            round_number=1,
            attacker_id="a",
            defender_id="b",
            attacker_name="A",
            defender_name="B",
            weapon_name="Rifle",
            weapon_type="beam",
            attack_result=AttackResult.HIT,
            damage=500,
            roll_value=75.0,
            distance=3,
            attacker_will_delta=1,
            defender_will_delta=-1,
            triggered_skills=[],
            is_first_attack=True
        )
        assert record.round_number == 1
        assert record.damage == 500
        assert record.attacker_hp_after == 0  # 默认值


class TestRoundSnapshot:
    """RoundSnapshot 数据类测试"""

    def test_round_snapshot_creation(self):
        """测试回合快照创建"""
        snapshot = RoundSnapshot(
            round_number=2,
            distance=4,
            first_mover="mech_b",
            initiative_reason="ADVANTAGE",
            mecha_a_hp=1000,
            mecha_a_en=50,
            mecha_a_will=100,
            mecha_b_hp=800,
            mecha_b_en=60,
            mecha_b_will=105
        )
        assert snapshot.round_number == 2
        assert snapshot.mecha_a_hp == 1000
