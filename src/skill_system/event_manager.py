"""
技能事件管理器 - 轻量级事件发布/订阅系统
"""

from typing import Callable, List, Dict, Any

class EventManager:
    """事件管理器"""

    # 类变量定义
    _callbacks: List[Callable[[Any], None]] = []
    _statistics: Dict[str, Dict[str, int]] = {}
    _current_round_events: List[Any] = []

    @classmethod
    def register_callback(cls, callback: Callable[[Any], None]) -> None:
        """注册事件回调（用于前端演出、日志记录等）"""
        if callback not in cls._callbacks:
            cls._callbacks.append(callback)

    @classmethod
    def unregister_callback(cls, callback: Callable[[Any], None]) -> None:
        """取消注册回调"""
        if callback in cls._callbacks:
            cls._callbacks.remove(callback)

    @classmethod
    def publish_event(cls, event: Any) -> None:
        """发布触发事件（所有订阅者都会收到）"""
        # 更新统计数据
        skill_id = getattr(event, 'skill_id', 'unknown')
        if skill_id not in cls._statistics:
            cls._statistics[skill_id] = {"attempts": 0, "success": 0}

        cls._statistics[skill_id]["attempts"] += 1
        is_triggered = getattr(event, 'triggered', False)
        if is_triggered:
            cls._statistics[skill_id]["success"] += 1
            # 存入回合缓存
            cls._current_round_events.append(event)

        # 只通知成功触发的事件
        if is_triggered:
            for callback in cls._callbacks:
                try:
                    callback(event)
                except Exception as e:
                    print(f"[ERROR] Event callback failed: {e}")

    @classmethod
    def get_current_round_events(cls) -> List[Any]:
        """获取当前回合积攒的事件，并清空缓存。"""
        events = list(cls._current_round_events)
        cls._current_round_events.clear()
        return events

    @classmethod
    def get_statistics(cls, skill_id: str | None = None) -> Dict:
        """获取统计数据"""
        if skill_id:
            return cls._statistics.get(skill_id, {})
        return cls._statistics.copy()

    @classmethod
    def clear_statistics(cls) -> None:
        """清空统计数据"""
        cls._statistics.clear()
