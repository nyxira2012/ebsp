"""
技能事件管理器 - 轻量级事件发布/订阅系统

设计说明：
  EventManager 采用"实例优先 + 全局默认"模式：
  - 每个 BattleSimulator 持有自己的 EventManager 实例，保证并行战斗模拟时状态完全隔离。
  - 模块末尾的 _default_em 供旧代码/测试使用的 @classmethod shims 委托调用，
    保证向后兼容，无需修改任何已有代码。
"""

from typing import Callable, List, Dict, Any

# Type alias for DualMethod attributes (suppresses pyright type checking)
DualMethodAttr = Any


class DualMethod:
    """
    描述符：允许同一个方法名既作为实例方法使用，又作为类方法（自动委托给默认实例）使用。
    解决 EventManager 实例化后的命名冲突和递归调用问题。
    """
    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner):
        if instance is None:
            # 类级别调用：EventManager.method(...) -> _default_em.method(...)
            def class_shim(*args, **kwargs):
                return self.func(owner._get_default(), *args, **kwargs)
            return class_shim
        # 实例级别调用：em.method(...)
        def instance_method(*args, **kwargs):
            return self.func(instance, *args, **kwargs)
        return instance_method


class EventManager:
    """
    事件管理器（实例级）

    设计说明：
      EventManager 采用"实例优先 + 自动全局委托"模式：
      - 每个 BattleSimulator 持有自己的 EventManager 实例，保证并行战斗模拟时状态完全隔离。
      - 类级别的方法通过 DualMethod 描述符自动委托给模块级私有的 _default_em 实例，
        从而维持对旧代码和测试的完全向后兼容。
    """

    def __init__(self) -> None:
        self._callbacks: List[Callable[[Any], None]] = []
        self._statistics: Dict[str, Dict[str, int]] = {}
        self._current_round_events: List[Any] = []
        self._current_attack_events: List[Any] = []
        self._in_attack: bool = False

    @classmethod
    def _get_default(cls) -> "EventManager":
        """获取模块级默认实例"""
        return _default_em

    # ------------------------------------------------------------------ #
    #  核心属性方法（由 DualMethod 包装，支持类和实例双向访问）                 #
    # ------------------------------------------------------------------ #

    def register_callback(self, callback: Callable[[Any], None]) -> None:
        """注册事件回调（用于前端演出、日志记录等）"""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[Any], None]) -> None:
        """取消注册回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def begin_attack(self) -> None:
        """标记单次攻击开始，清空本次攻击的事件缓存。"""
        self._current_attack_events = []
        self._in_attack = True

    def end_attack(self) -> List[Any]:
        """标记单次攻击结束，返回本次攻击期间触发的所有事件，并清空缓存。"""
        events = list(self._current_attack_events)
        self._current_attack_events = []
        self._in_attack = False
        return events

    def publish_event(self, event: Any) -> None:
        """发布触发事件（所有订阅者都会收到）"""
        skill_id = getattr(event, 'skill_id', 'unknown')
        if skill_id not in self._statistics:
            self._statistics[skill_id] = {"attempts": 0, "success": 0}

        self._statistics[skill_id]["attempts"] += 1
        is_triggered = getattr(event, 'triggered', False)
        if is_triggered:
            self._statistics[skill_id]["success"] += 1
            self._current_round_events.append(event)
            if self._in_attack:
                self._current_attack_events.append(event)

        if is_triggered:
            for callback in self._callbacks:
                try:
                    callback(event)
                except Exception as e:
                    print(f"[ERROR] Event callback failed: {e}")

    def get_current_round_events(self) -> List[Any]:
        """获取当前回合积攒的事件，并清空缓存。"""
        events = list(self._current_round_events)
        self._current_round_events.clear()
        return events

    def get_statistics(self, skill_id: str | None = None) -> Dict:
        """获取统计数据"""
        if skill_id:
            return self._statistics.get(skill_id, {})
        return self._statistics.copy()

    def clear_statistics(self) -> None:
        """清空统计数据"""
        self._statistics.clear()

    def reset(self) -> None:
        """重置所有状态（用于测试或战斗结束后清理）"""
        self._callbacks.clear()
        self._statistics.clear()
        self._current_round_events.clear()
        self._current_attack_events.clear()
        self._in_attack = False

    # --- 使用 DualMethod 包装上述方法，实现"类级调用->默认实例"的自动转换 ---
    # 这样 EventManager.publish_event(e) 等价于 _default_em.publish_event(e)
    # 而 em.publish_event(e) 仍然作用于 em 实例本身。
    register_callback = DualMethod(register_callback)  # type: ignore
    unregister_callback = DualMethod(unregister_callback)  # type: ignore
    begin_attack = DualMethod(begin_attack)  # type: ignore
    end_attack = DualMethod(end_attack)  # type: ignore
    publish_event = DualMethod(publish_event)  # type: ignore
    get_current_round_events = DualMethod(get_current_round_events)  # type: ignore
    get_statistics = DualMethod(get_statistics)  # type: ignore
    clear_statistics = DualMethod(clear_statistics)  # type: ignore
    reset = DualMethod(reset)  # type: ignore


# 模块级私有默认实例，作为类级调用的幕后委托者
_default_em = EventManager()
