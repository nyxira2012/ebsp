"""
Side Effect Executor System
处理效果触发后的副作用执行 (如消耗EN、改变气力、施加Buff等)
"""

from ..models import BattleContext, Mecha, TriggerEvent
from .event_manager import EventManager
from ._utils import get_target


def _get_target(effect_data: dict, context: BattleContext, owner: Mecha) -> Mecha | None:
    """获取副作用作用的目标机体。

    Args:
        effect_data: 副作用配置字典
        context: 战斗上下文快照
        owner: 效果持有人

    Returns:
        目标机体对象，若无法识别则返回 None
    """
    return get_target(effect_data.get("target", "self"), context, owner)


class SideEffectExecutor:
    """副作用执行器"""

    @staticmethod
    def execute(side_effects: list[dict], context: BattleContext, owner: Mecha) -> None:
        """执行效果触发后定义的所有副作用。

        Args:
            side_effects: 副作用配置字典列表
            context: 战斗上下文快照
            owner: 效果持有人
        """
        for effect_data in side_effects:
            effect_type = effect_data.get("type")
            if effect_type is None:
                continue
            executor_func = _EXECUTORS.get(effect_type)
            if executor_func:
                executor_func(effect_data, context, owner)


def _exec_consume_en(data: dict, context: BattleContext, owner: Mecha) -> None:
    """消耗目标机体的 EN 资源。

    Args:
        data: 配置数据，包含 'val' 消耗量
        context: 战斗上下文
        owner: 效果持有人
    """
    target = _get_target(data, context, owner)
    if not target:
        return

    val = data.get("val", 0)
    old_en = target.current_en
    target.consume_en(val)
    EventManager.publish_event(TriggerEvent(
        skill_id="side_effect_consume_en",
        owner=target,
        hook_name="SIDE_EFFECT",
        effect_text=f"消耗 {val} EN",
        old_value=old_en,
        new_value=target.current_en,
        probability=None,
        triggered=True
    ))


def _exec_modify_will(data: dict, context: BattleContext, owner: Mecha) -> None:
    """修改目标机体的气力值。

    Args:
        data: 配置数据，包含 'val' 变化量
        context: 战斗上下文
        owner: 效果持有人
    """
    target = _get_target(data, context, owner)
    if target:
        target.modify_will(data.get("val", 0))


def _exec_apply_effect(data: dict, context: BattleContext, owner: Mecha) -> None:
    """为目标机体施加新的状态效果 (Buff/Debuff)。

    Args:
        data: 配置数据，包含 'effect_id' 效果 ID 和可选的 'duration'
        context: 战斗上下文
        owner: 效果持有人
    """
    target = _get_target(data, context, owner)
    if not target:
        return

    effect_id = data.get("effect_id")
    if not effect_id:
        return

    from .effect_factory import EffectFactory

    new_effects = EffectFactory.create_effect(effect_id, duration=data.get("duration", 1))
    for eff in new_effects:
        target.effects.append(eff)
        EventManager.publish_event(TriggerEvent(
            skill_id="side_effect_apply_effect",
            owner=target,
            hook_name="SIDE_EFFECT",
            effect_text=f"施加 {eff.name}",
            old_value=None,
            new_value=eff.id,
            probability=None,
            triggered=True
        ))


# 副作用类型到执行函数的映射
_EXECUTORS = {
    "consume_en": _exec_consume_en,
    "modify_will": _exec_modify_will,
    "apply_effect": _exec_apply_effect,
    # "consume_charges" 和 "modify_stat" 暂未实现，不需要占位
}

