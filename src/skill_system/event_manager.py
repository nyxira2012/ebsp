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

    # --- 单次攻击边界追踪 ---
    # 用于精确捕获单次攻击（而非整个回合）期间触发的技能事件。
    # begin_attack() 开始记录，end_attack() 返回并清空本次记录。
    _current_attack_events: List[Any] = []
    _in_attack: bool = False

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
    def begin_attack(cls) -> None:
        """标记单次攻击开始，清空本次攻击的事件缓存。

        必须在 _execute_attack() 开始时调用，与 end_attack() 配对使用。
        这样可以精确区分先攻方和后攻方各自触发的技能，
        避免将整个回合的事件混入单次攻击的演出数据。
        """
        cls._current_attack_events = []
        cls._in_attack = True

    @classmethod
    def end_attack(cls) -> List[Any]:
        """标记单次攻击结束，返回本次攻击期间触发的所有事件，并清空缓存。

        Returns:
            本次攻击期间成功触发的技能事件列表（已过滤 triggered=False 的事件）。
        """
        events = list(cls._current_attack_events)
        cls._current_attack_events = []
        cls._in_attack = False
        return events

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
            # 存入回合缓存（兼容旧接口）
            cls._current_round_events.append(event)
            # 若当前处于单次攻击追踪中，同时存入攻击级缓存
            if cls._in_attack:
                cls._current_attack_events.append(event)

        # 只通知成功触发的事件
        if is_triggered:
            for callback in cls._callbacks:
                try:
                    callback(event)
                except Exception as e:
                    print(f"[ERROR] Event callback failed: {e}")

    @classmethod
    def get_current_round_events(cls) -> List[Any]:
        """获取当前回合积攒的事件，并清空缓存。

        注意：此方法返回整个回合的事件（先攻+后攻），会清空缓存。
        若需精确区分单次攻击的事件，请使用 begin_attack() / end_attack() 配对。
        """
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
