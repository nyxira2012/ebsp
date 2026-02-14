"""
Condition Checker System
处理效果触发条件的检查逻辑
"""

from ..models import BattleContext, Mecha
from ._utils import get_target


def _get_target(condition: dict, context: BattleContext, owner: Mecha) -> Mecha | None:
    """根据条件配置获取检查的目标对象。

    支持 "self" (效果持有人) 和 "enemy" (持有人的对手)。

    Args:
        condition: 条件配置字典
        context: 战斗上下文快照
        owner: 效果持有人

    Returns:
        目标机体对象，若无法识别则返回 None
    """
    return get_target(condition.get("target", "self"), context, owner)


def _compare(val1, val2, op: str = ">") -> bool:
    """通用的数值比较逻辑。

    Args:
        val1: 左操作数
        val2: 右操作数
        op: 比较运算符 (">", "<", "==", ">=", "<=", "!=")

    Returns:
        比较结果，若类型不匹配引发异常则返回 False
    """
    try:
        match op:
            case ">": return val1 > val2
            case "<": return val1 < val2
            case "==": return val1 == val2
            case ">=": return val1 >= val2
            case "<=": return val1 <= val2
            case "!=": return val1 != val2
            case _: return False
    except TypeError:
        return False


def _check_hp_threshold(condition: dict, context: BattleContext, owner: Mecha) -> bool:
    """HP 阈值检查 (hp_threshold)"""
    target = _get_target(condition, context, owner)
    if not target:
        return False

    current_ratio = target.current_hp / target.final_max_hp
    return _compare(current_ratio, condition.get("val", 0.0), condition.get("op", "<"))


def _check_will_threshold(condition: dict, context: BattleContext, owner: Mecha) -> bool:
    """气力阈值检查 (will_threshold)"""
    target = _get_target(condition, context, owner)
    return _compare(
        target.current_will if target else 0,
        condition.get("val", 100),
        condition.get("op", ">=")
    ) if target else False


def _check_round_number(condition: dict, context: BattleContext, owner: Mecha) -> bool:
    """回合数检查 (round_number)"""
    return _compare(
        context.round_number,
        condition.get("val", 1),
        condition.get("op", "==")
    )


def _check_attack_result(condition: dict, context: BattleContext, owner: Mecha) -> bool:
    """攻击结果检查 (attack_result)"""
    current_result = context.attack_result
    if current_result is None:
        return False

    target_result = condition.get("val")
    current_result_str = current_result.name

    if isinstance(target_result, list):
        return current_result_str in target_result
    return _compare(current_result_str, target_result, condition.get("op", "=="))


def _check_enemy_will_threshold(condition: dict, context: BattleContext, owner: Mecha) -> bool:
    """检查敌方气力 (enemy_will_threshold)"""
    opponent = context.defender if owner == context.attacker else context.attacker
    if opponent is None:
        return False

    return _compare(
        opponent.current_will,
        condition.get("val", 100),
        condition.get("op", ">=")
    )


def _check_enemy_stat_check(condition: dict, context: BattleContext, owner: Mecha) -> bool:
    """检查敌方基础属性 (enemy_stat_check)"""
    opponent = context.defender if owner == context.attacker else context.attacker
    if opponent is None:
        return False

    stat_name = condition.get("stat")
    if stat_name and stat_name in opponent.pilot_stats_backup:
        val = opponent.pilot_stats_backup[stat_name]
    elif stat_name and hasattr(opponent, stat_name):
        val = getattr(opponent, stat_name)
    else:
        return False

    return _compare(val, condition.get("val", 0), condition.get("op", ">"))


def _check_ref_hook(condition: dict, context: BattleContext, owner: Mecha) -> bool:
    """引用其他钩子的计算结果 (ref_hook)

    例如: 检查 HOOK_PRE_HIT_RATE 的结果是否 > 80
    """
    target_hook = condition.get("ref_hook")
    if not target_hook or target_hook not in context.cached_results:
        return False

    return _compare(
        context.cached_results[target_hook],
        condition.get("val", 0),
        condition.get("op", ">")
    )


def _check_weapon_type(condition: dict, context: BattleContext, owner: Mecha) -> bool:
    """武器类型检查 (weapon_type)"""
    weapon = context.weapon
    if not weapon:
        return False

    return _compare(
        weapon.weapon_type.name,
        condition.get("val"),
        condition.get("op", "==")
    )


def _check_damage_type(condition: dict, context: BattleContext, owner: Mecha) -> bool:
    """伤害类型检查 (damage_type)

    暂未实现伤害类型细分，返回 True 作为占位
    """
    return True


def _check_damage_below(condition: dict, context: BattleContext, owner: Mecha) -> bool:
    """伤害阈值检查 (damage_below)"""
    return context.damage < condition.get("val", 0)


# 条件类型到检查函数的映射
_CONDITION_CHECKERS = {
    "hp_threshold": _check_hp_threshold,
    "will_threshold": _check_will_threshold,
    "round_number": _check_round_number,
    "attack_result": _check_attack_result,
    "enemy_will_threshold": _check_enemy_will_threshold,
    "enemy_stat_check": _check_enemy_stat_check,
    "ref_hook": _check_ref_hook,
    "weapon_type": _check_weapon_type,
    "damage_type": _check_damage_type,
    "damage_below": _check_damage_below,
}


class ConditionChecker:
    """条件检查器"""

    @staticmethod
    def check(conditions: list[dict] | list, context: BattleContext, owner: Mecha) -> bool:
        """检查效果的所有触发条件是否满足。

        Args:
            conditions: 条件配置字典列表 (来自 JSON 或 Effect.dataclass)
            context: 战斗上下文快照
            owner: 效果持有人 (机体)

        Returns:
            所有条件均满足返回 True，否则返回 False
        """
        return all(
            _check_single(cond, context, owner)
            for cond in conditions
        )


def _check_single(condition: dict, context: BattleContext, owner: Mecha) -> bool:
    """检查单个条件是否满足。

    根据条件类型调用对应的检查函数。

    Args:
        condition: 单个条件配置字典
        context: 战斗上下文快照
        owner: 效果持有人

    Returns:
        该条件满足返回 True，否则返回 False
    """
    cond_type = condition.get("type")
    if cond_type is None:
        return False
    checker_func = _CONDITION_CHECKERS.get(cond_type)
    return checker_func(condition, context, owner) if checker_func else False
