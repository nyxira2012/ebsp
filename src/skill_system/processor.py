"""
Effect Processor System
技能效果的核心处理引擎，负责钩子触发、条件检查、副作用执行和冲突与叠加处理。
"""

from typing import Any, Callable, List, Dict
from ..models import BattleContext, Mecha, Effect, Condition, SideEffect
from .conditions import ConditionChecker
from .side_effects import SideEffectExecutor

class EffectProcessor:
    """效果处理器"""
    
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
            Any: 经过所有效果处理后的最终值
        """

        # 1. 防止无限递归 (如果 hook_stack 中出现超过阈值的同名 hook)
        if context.hook_stack.count(hook_name) >= 3:
            # print(f"WARNING: Hook recursion detected: {hook_name}")
            return input_value
        
        context.hook_stack.append(hook_name)
        
        try:
            # 2. 收集所有相关 Effect
            all_effects: List[tuple[Effect, Mecha]] = EffectProcessor._collect_effects(context)
            
            # 3. 筛选并排序 (priority 高 -> 低, id 字典序)
            valid_effects = []
            for effect, owner in all_effects:
                # 检查是否过期 (duration=0 或 charges=0)
                if effect.duration == 0 or effect.charges == 0:
                    continue
                
                if effect.hook == hook_name:
                    # 检查条件
                    if ConditionChecker.check(effect.conditions, context, owner):
                        valid_effects.append((effect, owner))
            
            # 排序: priority 升序, sub_priority 升序, id 升序
            # 这样高优先级的 Effect 会最后执行，从而拥有“最终决定权” (特别是对于 set, max, min 等覆盖性操作)
            valid_effects.sort(key=lambda x: (x[0].priority, x[0].sub_priority, x[0].id))
            
            current_value = input_value
            
            # 4. 依次执行 Effect
            import random
            for effect, owner in valid_effects:
                # 再次检查 (防止副作用修改了后面 Effect 的状态?)
                if effect.duration == 0 or effect.charges == 0:
                    continue

                # 检查触发概率
                if effect.trigger_chance < 1.0:
                    if random.random() >= effect.trigger_chance:
                        continue  # 未通过概率判定，跳过

                # 记录旧值用于显示
                old_value = current_value

                # 执行修改逻辑
                new_value = EffectProcessor._apply_operation(effect, current_value, context, owner)
                
                # 确定是否触发 (数值改变或者是 callback)
                is_triggered = False
                if new_value != current_value:
                    is_triggered = True
                elif effect.operation == 'callback':
                    is_triggered = True # Callback 默认视为触发
                
                if is_triggered:
                    current_value = new_value
                    
                    # 透明化输出
                    print(f"   [Skill] {owner.name}: '{effect.name}' 触发! ({hook_name}: {old_value} -> {current_value})")
                    
                    # 执行副作用
                    if effect.side_effects:
                        SideEffectExecutor.execute(effect.side_effects, context, owner)
                    
                    # 消耗次数 (仅当 > 0 时)
                    if effect.charges > 0:
                        effect.charges -= 1
                        if effect.charges == 0:
                            effect.duration = 0
                            print(f"   [Skill] '{effect.name}' 次数耗尽，效果结束。")

            
            # 5. 缓存结果 (用于 ref_hook)
            # 注意: 如果返回值是复杂对象 (e.g. Mecha), 缓存引用可能不安全
            # 但主要是为了数值检查
            if isinstance(current_value, (int, float, bool, str)):
                 context.cached_results[hook_name] = current_value
            
            return current_value
            
        finally:
            context.hook_stack.pop()

    @staticmethod
    def _collect_effects(context: BattleContext) -> List[tuple[Effect, Mecha]]:
        """从战场上下文中收集所有相关的效果及其持有者。

        当前收集范围包括攻击方和防御方的所有当前效果。使用 set 防止
        同一机体在复杂测试场景下被重复处理。

        Args:
            context: 战斗上下文快照

        Returns:
            List[tuple[Effect, Mecha]]: 效果及其持有机体的元组列表
        """
        effects = []

        # 使用 set 记录已处理的机体，防止同一机体参与多个角色(如测试场景)导致效果重复触发
        processed_mechas = set()

        # 1. 收集 mecha_a
        if context.mecha_a and id(context.mecha_a) not in processed_mechas:
            for effect in context.mecha_a.effects:
                effects.append((effect, context.mecha_a))
            processed_mechas.add(id(context.mecha_a))

        # 2. 收集 mecha_b
        if context.mecha_b and id(context.mecha_b) not in processed_mechas:
            for effect in context.mecha_b.effects:
                effects.append((effect, context.mecha_b))
            processed_mechas.add(id(context.mecha_b))

        # 3. 收集全局效果 (可以通过 context.global_effects 传入)
        # 例如地形、指挥官灵气等

        return effects

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
            Any: 操作执行后的新数值
        """
        op = effect.operation
        val = effect.value
        
        # 数值运算
        if isinstance(current_value, (int, float)) and isinstance(val, (int, float)):
             if op == "add":
                 return current_value + val
             elif op == "sub":
                 return current_value - val
             elif op == "mul":
                 return current_value * val
             elif op == "div":
                 return current_value / val if val != 0 else current_value
             elif op == "set": # 强制设定
                 return val
             elif op == "min": # 取小 (如受到的最大伤害限制)
                 return min(current_value, val)
             elif op == "max": # 取大
                 return max(current_value, val)

        # 布尔运算 (用于 check 钩子)
        if isinstance(current_value, bool):
             if op == "and":
                 return current_value and val
             elif op == "or":
                 return current_value or val
             elif op == "not":
                 return not current_value
             elif op == "set":
                 return bool(val)

        # 回调函数 (callback)
        if op == 'callback':
            # value 是 callback_id 字符串
            # 需要在 CallbackRegistry 中查找
             from ..skills import SkillRegistry
             callback_func = SkillRegistry.get_callback(str(val))
             if callback_func:
                 return callback_func(current_value, context, owner)
        
        # 如果类型不匹配或未知操作，返回原值
        return current_value
