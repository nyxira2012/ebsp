"""
Effect Processor System
技能效果的核心处理引擎，负责钩子触发、条件检查、副作用执行和冲突与叠加处理。
"""

import random
from typing import Any
from ..models import BattleContext, Mecha, Effect, TriggerEvent
from .conditions import ConditionChecker
from .side_effects import SideEffectExecutor
from .event_manager import EventManager


def _collect_effects(context: BattleContext) -> list[tuple[Effect, Mecha]]:
    """从战场上下文中收集所有相关的效果及其持有者。

    当前收集范围包括攻击方和防御方的所有当前效果。使用 set 防止
    同一机体在复杂测试场景下被重复处理。

    Args:
        context: 战斗上下文快照

    Returns:
        效果及其持有机体的元组列表
    """
    effects = []
    processed_mechas = set()

    for mecha in (context.mecha_a, context.mecha_b):
        if mecha and id(mecha) not in processed_mechas:
            for effect in mecha.effects:
                effects.append((effect, mecha))
            processed_mechas.add(id(mecha))

    return effects


def _apply_numeric_operation(current_value: float, op: str, val: float) -> float | None:
    """应用数值运算操作。

    Args:
        current_value: 当前值
        op: 操作类型
        val: 操作值

    Returns:
        运算后的新值，若操作不匹配则返回 None
    """
    match op:
        case "add": return current_value + val
        case "sub": return current_value - val
        case "mul": return current_value * val
        case "div": return current_value / val if val != 0 else current_value
        case "set": return val
        case "min": return min(current_value, val)
        case "max": return max(current_value, val)
        case _: return None


def _apply_bool_operation(current_value: bool, op: str, val: bool) -> bool | None:
    """应用布尔运算操作。

    Args:
        current_value: 当前值
        op: 操作类型
        val: 操作值

    Returns:
        运算后的新值，若操作不匹配则返回 None
    """
    match op:
        case "and": return current_value and val
        case "or": return current_value or val
        case "not": return not current_value
        case "set": return bool(val)
        case _: return None


class EffectProcessor:
    """效果处理器"""

    # 递归保护阈值
    _MAX_RECURSION_DEPTH = 3

    @staticmethod
    def process(hook_name: str, input_value: Any, context: BattleContext) -> Any:
        """处理指定钩子上的所有相关效果。

        按照优先级和子优先级对所有有效效果进行排序并依次应用。支持数值运算、
        布尔运算和回调函数。包含递归保护机制。

        Args:
            hook_name: 钩子点名称 (例如 'HOOK_PRE_DAMAGE_MULT')
            input_value: 初始数值或对象
            context: 战斗上下文快照

        Returns:
            经过所有效果处理后的最终值
        """
        # 递归保护
        if context.hook_stack.count(hook_name) >= EffectProcessor._MAX_RECURSION_DEPTH:
            return input_value

        context.hook_stack.append(hook_name)

        try:
            all_effects = _collect_effects(context)

            # 筛选并排序有效效果
            valid_effects = [
                (effect, owner)
                for effect, owner in all_effects
                if effect.duration != 0 and effect.charges != 0
                and effect.hook == hook_name
                and ConditionChecker.check(effect.conditions, context, owner)
            ]

            # 排序: priority 升序, sub_priority 升序, id 升序
            # 高优先级的 Effect 会最后执行，拥有"最终决定权"
            valid_effects.sort(key=lambda x: (x[0].priority, x[0].sub_priority, x[0].id))

            current_value = input_value

            for effect, owner in valid_effects:
                # 再次检查状态 (可能被副作用修改)
                if effect.duration == 0 or effect.charges == 0:
                    continue

                # 概率判定
                if effect.trigger_chance < 1.0 and random.random() >= effect.trigger_chance:
                    EventManager.publish_event(TriggerEvent(
                        skill_id=effect.id,
                        owner=owner,
                        hook_name=hook_name,
                        effect_text=f"{effect.name} 未触发",
                        old_value=current_value,
                        new_value=current_value,
                        probability=effect.trigger_chance,
                        triggered=False
                    ))
                    continue

                old_value = current_value
                new_value = EffectProcessor._apply_operation(effect, current_value, context, owner)

                # 判断是否触发
                is_triggered = new_value != current_value or effect.operation == 'callback'

                if is_triggered:
                    current_value = new_value

                    EventManager.publish_event(TriggerEvent(
                        skill_id=effect.id,
                        owner=owner,
                        hook_name=hook_name,
                        effect_text=effect.name,
                        old_value=old_value,
                        new_value=current_value,
                        probability=effect.trigger_chance if effect.trigger_chance < 1.0 else None,
                        triggered=True
                    ))

                    if effect.side_effects:
                        from dataclasses import asdict
                        side_effects_dicts = [
                            asdict(se) if not isinstance(se, dict) else se
                            for se in effect.side_effects
                        ]
                        SideEffectExecutor.execute(side_effects_dicts, context, owner)

                    # 消耗次数
                    if effect.charges > 0:
                        effect.charges -= 1
                        if effect.charges == 0:
                            effect.duration = 0
                            EventManager.publish_event(TriggerEvent(
                                skill_id=effect.id,
                                owner=owner,
                                hook_name=hook_name,
                                effect_text=f"{effect.name} 次数耗尽",
                                old_value=current_value,
                                new_value=current_value,
                                probability=None,
                                triggered=True
                            ))

            # 缓存结果 (用于 ref_hook)
            if isinstance(current_value, (int, float, bool, str)):
                context.cached_results[hook_name] = current_value

            return current_value

        finally:
            context.hook_stack.pop()

    @staticmethod
    def _apply_operation(effect: Effect, current_value: Any, context: BattleContext, owner: Mecha) -> Any:
        """应用单个效果的具体操作逻辑。

        支持以下操作类型：
        - 数值: add, sub, mul, div, set, min, max
        - 布尔: and, or, not, set
        - 回调: callback (通过 SkillRegistry 查找)

        Args:
            effect: 效果对象
            current_value: 当前值
            context: 战斗上下文
            owner: 效果持有机体

        Returns:
            操作执行后的新数值
        """
        op = effect.operation
        val = effect.value

        # 布尔运算（必须在数值运算之前检查，因为 bool 是 int 的子类）
        if isinstance(current_value, bool):
            result = _apply_bool_operation(current_value, op, bool(val))
            if result is not None:
                return result

        # 数值运算
        if isinstance(current_value, (int, float)) and isinstance(val, (int, float)):
            result = _apply_numeric_operation(float(current_value), op, float(val))
            if result is not None:
                # set 操作保留 val 的原始类型，其他操作保留 current_value 的类型
                if op == "set":
                    return int(val) if isinstance(val, int) else val
                return int(result) if isinstance(current_value, int) else result

        # 回调函数
        if op == 'callback':
            from ..skills import SkillRegistry
            callback_func = SkillRegistry.get_callback(str(val))
            if callback_func:
                return callback_func(current_value, context, owner)

        # 类型不匹配或未知操作，返回原值
        return current_value
