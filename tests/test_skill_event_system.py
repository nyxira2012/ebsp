"""
技能事件系统测试
测试 TriggerEvent、BuffState、EventManager 等核心组件
"""

import pytest
from src.models import TriggerEvent, BuffState
from src.skill_system.event_manager import EventManager


class TestTriggerEvent:
    """TriggerEvent 测试"""

    def test_create_event(self):
        """测试事件创建"""
        event = TriggerEvent(
            skill_id="test",
            owner=None,
            hook_name="TEST",
            effect_text="测试效果",
            old_value=100,
            new_value=130,
            probability=0.5,
            triggered=True
        )
        assert event.skill_id == "test"
        assert event.triggered == True

    def test_event_frozen(self):
        """测试事件不可变性"""
        event = TriggerEvent(
            skill_id="test",
            owner=None,
            hook_name="TEST",
            effect_text="测试",
            old_value=100,
            new_value=130,
            triggered=True
        )
        # 尝试修改应该报错
        with pytest.raises(Exception):
            event.skill_id = "modified"


class TestBuffState:
    """BuffState 测试"""

    def test_is_expired(self):
        """测试过期检查"""
        # duration = 0 时过期
        buff = BuffState(skill_id="test", duration=0)
        assert buff.is_expired()

        # charges = 0 时过期
        buff2 = BuffState(skill_id="test", charges=0)
        assert buff2.is_expired()

        # 都不为 0 时不过期
        buff3 = BuffState(skill_id="test", duration=5, charges=3)
        assert not buff3.is_expired()

    def test_tick(self):
        """测试持续时间减少"""
        buff = BuffState(skill_id="test", duration=3)
        buff.tick()
        assert buff.duration == 2

        # tick 对 charges 的影响
        buff2 = BuffState(skill_id="test", charges=5)
        buff2.tick()
        assert buff2.charges == 4

    def test_tick_permanent_buff(self):
        """测试永久 buff (-1) 的 tick"""
        buff = BuffState(skill_id="permanent", duration=-1, charges=-1)
        buff.tick()
        # 永久 buff tick 后仍然是 -1
        assert buff.duration == -1
        assert buff.charges == -1


class TestEventManager:
    """EventManager 测试"""

    def setup_method(self):
        """每个测试前清空统计数据"""
        EventManager.clear_statistics()

    def test_register_callback(self):
        """测试回调注册"""
        calls = []

        def callback(event):
            calls.append(event)

        EventManager.register_callback(callback)

        event = TriggerEvent(
            skill_id="test",
            owner=None,
            hook_name="TEST",
            effect_text="测试",
            old_value=100,
            new_value=130,
            triggered=True
        )

        EventManager.publish_event(event)

        assert len(calls) == 1
        assert calls[0].skill_id == "test"

    def test_statistics(self):
        """测试统计数据"""
        EventManager.clear_statistics()

        # 成功触发
        event1 = TriggerEvent(
            skill_id="test",
            owner=None,
            hook_name="TEST",
            effect_text="成功",
            old_value=100,
            new_value=130,
            probability=0.5,
            triggered=True
        )
        EventManager.publish_event(event1)

        # 失败触发
        event2 = TriggerEvent(
            skill_id="test",
            owner=None,
            hook_name="TEST",
            effect_text="失败",
            old_value=100,
            new_value=100,
            probability=0.5,
            triggered=False
        )
        EventManager.publish_event(event2)

        stats = EventManager.get_statistics("test")
        assert stats["attempts"] == 2
        assert stats["success"] == 1

    def test_multiple_skills_statistics(self):
        """测试多个技能的统计"""
        EventManager.clear_statistics()

        # 技能 A
        for i in range(3):
            EventManager.publish_event(TriggerEvent(
                skill_id="skill_a",
                owner=None,
                hook_name="TEST",
                effect_text=f"a{i}",
                old_value=0,
                new_value=0,
                triggered=True
            ))

        # 技能 B
        for i in range(2):
            EventManager.publish_event(TriggerEvent(
                skill_id="skill_b",
                owner=None,
                hook_name="TEST",
                effect_text=f"b{i}",
                old_value=0,
                new_value=0,
                triggered=True
            ))

        all_stats = EventManager.get_statistics()
        assert len(all_stats) == 2
        assert all_stats["skill_a"]["attempts"] == 3
        assert all_stats["skill_b"]["attempts"] == 2

    def test_failed_event_not_called(self):
        """测试失败事件不触发回调"""
        calls = []

        def callback(event):
            calls.append(event)

        EventManager.register_callback(callback)

        # 失败事件
        event = TriggerEvent(
            skill_id="test",
            owner=None,
            hook_name="TEST",
            effect_text="失败",
            old_value=100,
            new_value=100,
            triggered=False
        )

        EventManager.publish_event(event)

        # 失败事件不应该触发回调
        assert len(calls) == 0

        # 但统计数据应该记录
        stats = EventManager.get_statistics("test")
        assert stats["attempts"] == 1
        assert stats["success"] == 0


