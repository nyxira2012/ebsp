"""
Condition Checker System
处理效果触发条件的检查逻辑
"""

from typing import Any, Callable, TYPE_CHECKING
from ..models import BattleContext, Mecha, Weapon, WeaponType, AttackResult

if TYPE_CHECKING:
    from ..models import Condition

class ConditionChecker:
    """条件检查器"""
    
    @staticmethod
    def check(conditions: list[dict], context: BattleContext, owner: Mecha) -> bool:
        """检查所有条件是否满足"""
        for cond in conditions:
            if not ConditionChecker._check_single(cond, context, owner):
                return False
        return True
    
    @staticmethod
    def _check_single(condition: dict, context: BattleContext, owner: Mecha) -> bool:
        """检查单个条件"""
        cond_type = condition.get("type")
        
        # 获取条件检查函数 (例如 hp_threshold -> _check_hp_threshold)
        checker_func = getattr(ConditionChecker, f"_check_{cond_type}", None)
        if checker_func:
            return checker_func(condition, context, owner)
        return False

    @staticmethod
    def _get_target(condition: dict, context: BattleContext, owner: Mecha) -> Mecha | None:
        """获取条件检查的目标机体 (self/enemy)"""
        target_type = condition.get("target", "self")
        
        if target_type == "self":
            return owner
        elif target_type == "enemy":
            # 如果 owner 是 attacker，目标就是 defender，反之亦然
            if owner == context.attacker:
                return context.defender
            elif owner == context.defender:
                return context.attacker
        
        return None

    # --- 具体检查实现 ---

    @staticmethod
    def _check_hp_threshold(condition: dict, context: BattleContext, owner: Mecha) -> bool:
        """HP 阈值检查 (hp_threshold)"""
        target = ConditionChecker._get_target(condition, context, owner)
        if not target: return False
        
        current_ratio = target.current_hp / target.max_hp
        threshold = condition.get("val", 0.0)
        op = condition.get("op", "<")
        
        return ConditionChecker._compare(current_ratio, threshold, op)

    @staticmethod
    def _check_will_threshold(condition: dict, context: BattleContext, owner: Mecha) -> bool:
        """气力阈值检查 (will_threshold)"""
        target = ConditionChecker._get_target(condition, context, owner)
        if not target: return False
        
        current_will = target.current_will
        threshold = condition.get("val", 100)
        op = condition.get("op", ">=")
        
        return ConditionChecker._compare(current_will, threshold, op)

    @staticmethod
    def _check_round_number(condition: dict, context: BattleContext, owner: Mecha) -> bool:
        """回合数检查 (round_number)"""
        current_round = context.round_number
        threshold = condition.get("val", 1)
        op = condition.get("op", "==")
        return ConditionChecker._compare(current_round, threshold, op)

    @staticmethod
    def _check_attack_result(condition: dict, context: BattleContext, owner: Mecha) -> bool:
        """攻击结果检查 (attack_result)"""
        current_result = context.attack_result
        if current_result is None: return False
        
        target_result = condition.get("val") 
        op = condition.get("op", "==")
        current_result_str = current_result.name
        
        if isinstance(target_result, list):
             return current_result_str in target_result
        return ConditionChecker._compare(current_result_str, target_result, op)

    @staticmethod
    def _check_enemy_will_threshold(condition: dict, context: BattleContext, owner: Mecha) -> bool:
        """检查敌方气力 (enemy_will_threshold)"""
        opponent = context.defender if owner == context.attacker else context.attacker
        
        current_will = opponent.current_will
        threshold = condition.get("val", 100)
        op = condition.get("op", ">=")
        
        return ConditionChecker._compare(current_will, threshold, op)

    @staticmethod
    def _check_enemy_stat_check(condition: dict, context: BattleContext, owner: Mecha) -> bool:
        """检查敌方基础属性 (enemy_stat_check)"""
        opponent = context.defender if owner == context.attacker else context.attacker
        stat_name = condition.get("stat")
        
        if stat_name and hasattr(opponent.pilot, stat_name):
            val = getattr(opponent.pilot, stat_name)
        elif stat_name and hasattr(opponent, stat_name):
            val = getattr(opponent, stat_name)
        else:
            return False
            
        threshold = condition.get("val", 0)
        op = condition.get("op", ">")
        
        return ConditionChecker._compare(val, threshold, op)


    @staticmethod
    def _check_ref_hook(condition: dict, context: BattleContext, owner: Mecha) -> bool:
         """引用其他钩子的计算结果 (ref_hook)
         
         例如: 检查 HOOK_PRE_HIT_RATE 的结果是否 > 80
         """
         target_hook = condition.get("ref_hook")
         if not target_hook: return False
         
         # 注意: 只有之前执行过的钩子才会在 cached_results 中
         # 如果是未来的钩子，这里取不到值（或者取到上回合的旧值，这可能有误用风险）
         # 此处假设 cached_results 只存储本回合已计算的值
         if target_hook not in context.cached_results:
             return False
             
         result_val = context.cached_results[target_hook]
         threshold = condition.get("val", 0)
         op = condition.get("op", ">")
         
         return ConditionChecker._compare(result_val, threshold, op)

    @staticmethod
    def _check_weapon_type(condition: dict, context: BattleContext, owner: Mecha) -> bool:
        """武器类型检查 (weapon_type)"""
        target = ConditionChecker._get_target(condition, context, owner)
        # 获取当前使用的武器
        weapon = context.weapon
        
        # 必须是攻击方在使用武器
        if not weapon: return False
        
        weapon_type_str = weapon.weapon_type.name # MELEE, RIFLE...
        target_type = condition.get("val")
        op = condition.get("op", "==")
        
        return ConditionChecker._compare(weapon_type_str, target_type, op)

    @staticmethod
    def _check_damage_type(condition: dict, context: BattleContext, owner: Mecha) -> bool:
        """伤害类型检查 (damage_type)"""
        # 暂未实现伤害类型细分，目前假设所有 RIFLE/HEAVY 都是 BEAM，MELEE 是 PHYSICAL
        # 或者增加 Weapon.damage_type 字段
        # 这里仅作占位
        return True

    @staticmethod
    def _check_damage_below(condition: dict, context: BattleContext, owner: Mecha) -> bool:
        """伤害阈值检查 (damage_below)"""
        # 检查当前 context 中的 damage
        current_damage = context.damage
        threshold = condition.get("val", 0)
        return current_damage < threshold

    @staticmethod
    def _compare(val1: Any, val2: Any, op: str = ">") -> bool:
        """通用比较函数"""
        try:
            if op == ">": return val1 > val2
            if op == "<": return val1 < val2
            if op == "==": return val1 == val2
            if op == ">=": return val1 >= val2
            if op == "<=": return val1 <= val2
            if op == "!=": return val1 != val2
            return False
        except TypeError:
            return False
