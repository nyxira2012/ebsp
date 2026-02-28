"""
EventManager 实例隔离与向后兼容测试

验证：
1. EventManager 实例状态完全隔离（多战斗并行支持）
2. 类级别调用向后兼容（旧代码无需修改）
3. BattleContext 正确绑定和路由 EventManager
4. AttackEventBuilder 正确构建 RawAttackEvent
"""

import pytest
from unittest.mock import MagicMock

from src.skill_system.event_manager import EventManager
from src.models import TriggerEvent, BattleContext, AttackResult
from src.presentation.event_builder import AttackEventBuilder
from src.presentation.models import RawAttackEvent


class TestEventManagerIsolation:
    """EventManager 实例隔离测试 - 验证多战斗并行时状态不互相干扰"""

    def test_instance_state_isolation(self):
        """两个 EventManager 实例的状态完全独立"""
        em1 = EventManager()
        em2 = EventManager()

        # em1 注册回调
        calls1 = []
        em1.register_callback(lambda e: calls1.append(e))

        # em2 注册不同回调
        calls2 = []
        em2.register_callback(lambda e: calls2.append(e))

        # 只通过 em1 发布事件
        event = TriggerEvent(
            skill_id="test_skill",
            owner=None,
            hook_name="TEST",
            effect_text="测试",
            old_value=100,
            new_value=130,
            triggered=True
        )
        em1.publish_event(event)

        # em1 的回调应该被触发
        assert len(calls1) == 1
        assert calls1[0].skill_id == "test_skill"

        # em2 的回调不应该被触发
        assert len(calls2) == 0

    def test_statistics_not_shared(self):
        """统计数据在实例间不共享"""
        em1 = EventManager()
        em2 = EventManager()

        event = TriggerEvent(
            skill_id="shared_skill",
            owner=None,
            hook_name="TEST",
            effect_text="测试",
            old_value=0,
            new_value=0,
            triggered=True
        )

        # 只在 em1 发布事件
        em1.publish_event(event)

        # em1 应该有统计
        stats1 = em1.get_statistics("shared_skill")
        assert stats1["attempts"] == 1

        # em2 应该没有统计
        stats2 = em2.get_statistics("shared_skill")
        assert stats2 == {}

    def test_attack_events_not_shared(self):
        """攻击级事件缓存在实例间隔离"""
        em1 = EventManager()
        em2 = EventManager()

        # em1 开始攻击并发布事件
        em1.begin_attack()
        event1 = TriggerEvent(
            skill_id="skill_a",
            owner=None,
            hook_name="TEST",
            effect_text="em1事件",
            old_value=0,
            new_value=0,
            triggered=True
        )
        em1.publish_event(event1)
        events1 = em1.end_attack()

        # em2 开始攻击并发布事件
        em2.begin_attack()
        event2 = TriggerEvent(
            skill_id="skill_b",
            owner=None,
            hook_name="TEST",
            effect_text="em2事件",
            old_value=0,
            new_value=0,
            triggered=True
        )
        em2.publish_event(event2)
        events2 = em2.end_attack()

        # 各自只收到自己的事件
        assert len(events1) == 1
        assert events1[0].skill_id == "skill_a"

        assert len(events2) == 1
        assert events2[0].skill_id == "skill_b"

    def test_reset_is_instance_local(self):
        """reset() 只影响当前实例"""
        em1 = EventManager()
        em2 = EventManager()

        # 两个实例都发布事件
        event = TriggerEvent(
            skill_id="test",
            owner=None,
            hook_name="TEST",
            effect_text="测试",
            old_value=0,
            new_value=0,
            triggered=True
        )
        em1.publish_event(event)
        em2.publish_event(event)

        # 重置 em1
        em1.reset()

        # em1 统计被清空
        assert em1.get_statistics() == {}

        # em2 统计仍然存在
        stats2 = em2.get_statistics("test")
        assert stats2["attempts"] == 1


class TestEventManagerBackwardCompatibility:
    """向后兼容测试 - 验证类级别调用仍委托给全局默认实例"""

    def setup_method(self):
        """每个测试前重置全局默认实例"""
        EventManager.reset()

    def teardown_method(self):
        """每个测试后清理"""
        EventManager.reset()

    def test_class_level_delegates_to_default(self):
        """类级别调用自动委托给全局默认实例"""
        calls = []

        # 通过类级别注册回调（旧代码风格）
        EventManager.register_callback(lambda e: calls.append(e))

        # 通过类级别发布事件
        event = TriggerEvent(
            skill_id="class_level_test",
            owner=None,
            hook_name="TEST",
            effect_text="类级别调用",
            old_value=0,
            new_value=0,
            triggered=True
        )
        EventManager.publish_event(event)

        # 回调应该被触发
        assert len(calls) == 1
        assert calls[0].skill_id == "class_level_test"

    def test_class_level_begin_end_attack(self):
        """类级别 begin_attack/end_attack 正常工作"""
        # 类级别开始攻击
        EventManager.begin_attack()

        event = TriggerEvent(
            skill_id="attack_event",
            owner=None,
            hook_name="TEST",
            effect_text="攻击事件",
            old_value=0,
            new_value=0,
            triggered=True
        )
        EventManager.publish_event(event)

        # 类级别结束攻击
        events = EventManager.end_attack()

        assert len(events) == 1
        assert events[0].skill_id == "attack_event"

    def test_mixed_class_and_instance_calls(self):
        """混合类级别和实例级别调用不会冲突"""
        # 创建独立实例
        em_instance = EventManager()

        instance_calls = []
        class_calls = []

        em_instance.register_callback(lambda e: instance_calls.append(e))
        EventManager.register_callback(lambda e: class_calls.append(e))

        # 实例级别发布
        event1 = TriggerEvent(
            skill_id="instance_event",
            owner=None,
            hook_name="TEST",
            effect_text="实例事件",
            old_value=0,
            new_value=0,
            triggered=True
        )
        em_instance.publish_event(event1)

        # 类级别发布
        event2 = TriggerEvent(
            skill_id="class_event",
            owner=None,
            hook_name="TEST",
            effect_text="类事件",
            old_value=0,
            new_value=0,
            triggered=True
        )
        EventManager.publish_event(event2)

        # 实例回调只收到实例事件
        assert len(instance_calls) == 1
        assert instance_calls[0].skill_id == "instance_event"

        # 类回调只收到类事件
        assert len(class_calls) == 1
        assert class_calls[0].skill_id == "class_event"

    def test_existing_code_pattern_still_works(self):
        """模拟旧代码使用模式 - 无需修改即可工作"""
        # 典型的旧代码模式
        EventManager.clear_statistics()

        # 发布一些事件
        for i in range(3):
            EventManager.publish_event(TriggerEvent(
                skill_id="old_pattern_skill",
                owner=None,
                hook_name="TEST",
                effect_text=f"事件{i}",
                old_value=0,
                new_value=0,
                triggered=True
            ))

        # 获取统计
        stats = EventManager.get_statistics("old_pattern_skill")
        assert stats["attempts"] == 3
        assert stats["success"] == 3


class TestBattleContextEventManager:
    """BattleContext EventManager 绑定测试"""

    def test_publish_event_routes_to_bound_manager(self):
        """绑定时路由到正确的 EventManager 实例"""
        em = EventManager()
        calls = []
        em.register_callback(lambda e: calls.append(e))

        # 创建绑定 EventManager 的上下文
        ctx = BattleContext(
            round_number=1,
            distance=100,
            mecha_a=None,
            mecha_b=None,
            event_manager=em
        )

        # 通过上下文发布事件
        event = TriggerEvent(
            skill_id="routed_event",
            owner=None,
            hook_name="TEST",
            effect_text="路由事件",
            old_value=0,
            new_value=0,
            triggered=True
        )
        ctx.publish_event(event)

        # 应该路由到绑定的 em
        assert len(calls) == 1
        assert calls[0].skill_id == "routed_event"

    def test_publish_event_fallback_to_global(self):
        """未绑定时回退到全局默认实例"""
        # 确保全局默认实例有回调
        global_calls = []
        EventManager.register_callback(lambda e: global_calls.append(e))

        # 创建未绑定 EventManager 的上下文
        ctx = BattleContext(
            round_number=1,
            distance=100,
            mecha_a=None,
            mecha_b=None,
            event_manager=None  # 未绑定
        )

        # 通过上下文发布事件
        event = TriggerEvent(
            skill_id="fallback_event",
            owner=None,
            hook_name="TEST",
            effect_text="回退事件",
            old_value=0,
            new_value=0,
            triggered=True
        )
        ctx.publish_event(event)

        # 应该回退到全局默认实例
        assert len(global_calls) == 1
        assert global_calls[0].skill_id == "fallback_event"


class TestAttackEventBuilder:
    """AttackEventBuilder 测试 - 验证引擎与表现层解耦"""

    def test_build_basic_fields(self):
        """基本字段正确映射"""
        # 创建模拟对象
        attacker = MagicMock()
        attacker.id = "att_001"
        attacker.name = "攻击者"
        attacker.current_hp = 800
        attacker.current_en = 100
        attacker.current_will = 110

        defender = MagicMock()
        defender.id = "def_001"
        defender.name = "防御者"
        defender.current_hp = 600
        defender.current_en = 80
        defender.current_will = 105
        defender.final_max_hp = 1000

        weapon = MagicMock()
        weapon.id = "wpn_001"
        weapon.name = "光束步枪"
        weapon.type.value = "SHOOTING"
        weapon.tags = ["beam", "rifle"]

        ctx = MagicMock()
        ctx.distance = 500
        ctx.roll = 75.5
        ctx.current_attacker_will_delta = 2
        ctx.current_defender_will_delta = 0

        # 构建事件
        raw_event = AttackEventBuilder.build(
            attacker=attacker,
            defender=defender,
            weapon=weapon,
            ctx=ctx,
            result=AttackResult.HIT,
            damage=1200,
            triggered_skill_ids=["skill_1", "skill_2"],
            spirit_commands=[],
            is_first=True,
            round_number=5,
            en_cost=25
        )

        # 验证基本字段
        assert raw_event.round_number == 5
        assert raw_event.attacker_id == "att_001"
        assert raw_event.defender_id == "def_001"
        assert raw_event.attacker_name == "攻击者"
        assert raw_event.defender_name == "防御者"

    def test_build_weapon_fields(self):
        """武器字段正确映射"""
        attacker = MagicMock()
        attacker.id = "att_001"
        attacker.name = "高达"
        attacker.current_hp = 1000
        attacker.current_en = 100
        attacker.current_will = 120

        defender = MagicMock()
        defender.id = "def_001"
        defender.name = "扎古"
        defender.current_hp = 800
        defender.current_en = 80
        defender.current_will = 100
        defender.final_max_hp = 1200

        weapon = MagicMock()
        weapon.id = "wpn_beam_saber"
        weapon.name = "光束军刀"
        weapon.type.value = "MELEE"
        weapon.tags = ["beam", "sword"]

        ctx = MagicMock()
        ctx.distance = 100
        ctx.roll = 50.0
        ctx.current_attacker_will_delta = 3
        ctx.current_defender_will_delta = -2

        raw_event = AttackEventBuilder.build(
            attacker=attacker,
            defender=defender,
            weapon=weapon,
            ctx=ctx,
            result=AttackResult.CRIT,
            damage=2500,
            triggered_skill_ids=[],
            spirit_commands=[],
            is_first=False,
            round_number=3,
            en_cost=10
        )

        # 验证武器字段
        assert raw_event.weapon_id == "wpn_beam_saber"
        assert raw_event.weapon_name == "光束军刀"
        assert raw_event.weapon_type == "MELEE"
        assert raw_event.weapon_tags == ["beam", "sword"]

    def test_build_result_fields(self):
        """判定结果字段正确映射"""
        attacker = MagicMock()
        attacker.id = "att_001"
        attacker.name = "攻击者"
        attacker.current_hp = 1000
        attacker.current_en = 100
        attacker.current_will = 120

        defender = MagicMock()
        defender.id = "def_001"
        defender.name = "防御者"
        defender.current_hp = 800
        defender.current_en = 80
        defender.current_will = 100
        defender.final_max_hp = 1000

        weapon = MagicMock()
        weapon.id = "wpn_001"
        weapon.name = "测试武器"
        weapon.type.value = "SHOOTING"
        weapon.tags = []

        ctx = MagicMock()
        ctx.distance = 500
        ctx.roll = 85.0
        ctx.current_attacker_will_delta = 0
        ctx.current_defender_will_delta = 0

        raw_event = AttackEventBuilder.build(
            attacker=attacker,
            defender=defender,
            weapon=weapon,
            ctx=ctx,
            result=AttackResult.CRIT,
            damage=3000,
            triggered_skill_ids=["critical_mastery"],
            spirit_commands=[],
            is_first=True,
            round_number=1,
            en_cost=30
        )

        # 验证结果字段
        assert raw_event.attack_result == "CRIT"
        assert raw_event.damage == 3000
        assert raw_event.roll_value == 85.0
        assert raw_event.en_cost == 30
        assert raw_event.triggered_skills == ["critical_mastery"]
        assert raw_event.is_first_attack is True

    def test_build_state_snapshots(self):
        """状态快照字段正确映射"""
        attacker = MagicMock()
        attacker.id = "att_001"
        attacker.name = "高达"
        attacker.current_hp = 800  # 受击后
        attacker.current_en = 90   # 消耗后
        attacker.current_will = 115

        defender = MagicMock()
        defender.id = "def_001"
        defender.name = "扎古"
        defender.current_hp = 200  # 受伤后
        defender.current_en = 85
        defender.current_will = 95
        defender.final_max_hp = 1000

        weapon = MagicMock()
        weapon.id = "wpn_001"
        weapon.name = "光束步枪"
        weapon.type.value = "SHOOTING"
        weapon.tags = []

        ctx = MagicMock()
        ctx.distance = 600
        ctx.roll = 60.0
        ctx.current_attacker_will_delta = 2
        ctx.current_defender_will_delta = -3

        raw_event = AttackEventBuilder.build(
            attacker=attacker,
            defender=defender,
            weapon=weapon,
            ctx=ctx,
            result=AttackResult.HIT,
            damage=800,
            triggered_skill_ids=[],
            spirit_commands=[],
            is_first=False,
            round_number=2,
            en_cost=20
        )

        # 验证状态快照
        assert raw_event.attacker_hp_after == 800
        assert raw_event.attacker_en_after == 90
        assert raw_event.attacker_will_after == 115
        assert raw_event.defender_hp_after == 200
        assert raw_event.defender_en_after == 85
        assert raw_event.defender_will_after == 95
        assert raw_event.defender_max_hp == 1000

    def test_build_returns_raw_attack_event(self):
        """返回类型是 RawAttackEvent"""
        attacker = MagicMock()
        attacker.id = "att_001"
        attacker.name = "攻击者"
        attacker.current_hp = 1000
        attacker.current_en = 100
        attacker.current_will = 120

        defender = MagicMock()
        defender.id = "def_001"
        defender.name = "防御者"
        defender.current_hp = 1000
        defender.current_en = 100
        defender.current_will = 120
        defender.final_max_hp = 1000

        weapon = MagicMock()
        weapon.id = "wpn_001"
        weapon.name = "武器"
        weapon.type.value = "MELEE"
        weapon.tags = []

        ctx = MagicMock()
        ctx.distance = 100
        ctx.roll = 50.0
        ctx.current_attacker_will_delta = 0
        ctx.current_defender_will_delta = 0

        raw_event = AttackEventBuilder.build(
            attacker=attacker,
            defender=defender,
            weapon=weapon,
            ctx=ctx,
            result=AttackResult.HIT,
            damage=500,
            triggered_skill_ids=[],
            spirit_commands=[],
            is_first=True,
            round_number=1,
            en_cost=10
        )

        assert isinstance(raw_event, RawAttackEvent)
