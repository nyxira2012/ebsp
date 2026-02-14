"""
技能事件管理器 - 轻量级事件发布/订阅系统
"""

from typing import Callable, List, Dict, Any

class EventManager:
    """事件管理器"""

    # 已注册的回调列表
    _callbacks: List[Callable[[Any], None]] = []

    # 统计数据：[skill_id] -> {"attempts": int, "success": int}
    _statistics: Dict[str, Dict[str, int]] = {}

    @classmethod
    def register_callback(cls, callback: Callable[[Any], None]) -> None:
        """注册事件回调（用于前端演出、日志记录等）"""
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
        skill_id = event.skill_id
        if skill_id not in cls._statistics:
            cls._statistics[skill_id] = {"attempts": 0, "success": 0}

        cls._statistics[skill_id]["attempts"] += 1
        if event.triggered:
            cls._statistics[skill_id]["success"] += 1

        # 只通知成功触发的事件
        if event.triggered:
            for callback in cls._callbacks:
                callback(event)

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
