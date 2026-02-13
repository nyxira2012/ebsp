"""
Side Effect Executor System
处理效果触发后的副作用执行 (如消耗EN、改变气力、施加Buff等)
"""

from typing import Any, Callable
from ..models import BattleContext, Mecha, SideEffect, Effect

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
            SideEffectExecutor._execute_single(effect_data, context, owner)
    
    @staticmethod
    def _execute_single(effect_data: dict, context: BattleContext, owner: Mecha) -> None:
        """执行单个副作用。

        根据副作用类型动态调用对应的执行函数。

        Args:
            effect_data: 单个副作用配置字典
            context: 战斗上下文快照
            owner: 效果持有人
        """
        effect_type = effect_data.get("type")
        
        # 获取执行函数
        executor_func = getattr(SideEffectExecutor, f"_exec_{effect_type}", None)
        if executor_func:
            executor_func(effect_data, context, owner)

    @staticmethod
    def _get_target(effect_data: dict, context: BattleContext, owner: Mecha) -> Mecha | None:
        """获取副作用作用的目标机体。

        Args:
            effect_data: 副作用配置字典
            context: 战斗上下文快照
            owner: 效果持有人

        Returns:
            Mecha | None: 目标机体对象
        """
        target_type = effect_data.get("target", "self")

        if target_type == "self":
            return owner
        elif target_type == "enemy":
            # 如果 owner 是当前攻击方，目标就是当前防御方，反之亦然
            attacker = context.get_attacker()
            defender = context.get_defender()
            if owner == attacker:
                return defender
            elif owner == defender:
                return attacker

        return None

    # --- 具体副作用实现 ---

    @staticmethod
    def _exec_consume_en(data: dict, context: BattleContext, owner: Mecha) -> None:
        """消耗目标机体的 EN 资源。

        Args:
            data: 配置数据，包含 'val' 消耗量
            context: 战斗上下文
            owner: 效果持有人
        """
        target = SideEffectExecutor._get_target(data, context, owner)
        if not target: return
        
        val = data.get("val", 0)
        target.consume_en(val)
        print(f"   [Effect] {target.name} 消耗了 {val} EN (副作用)")

    @staticmethod
    def _exec_consume_charges(data: dict, context: BattleContext, owner: Mecha) -> None:
        """消耗次数 (consume_charges)"""
        pass

    @staticmethod
    def _exec_modify_will(data: dict, context: BattleContext, owner: Mecha) -> None:
        """修改目标机体的气力值。

        Args:
            data: 配置数据，包含 'val' 变化量
            context: 战斗上下文
            owner: 效果持有人
        """
        target = SideEffectExecutor._get_target(data, context, owner)
        if not target: return
        
        val = data.get("val", 0)
        target.modify_will(val)

    @staticmethod
    def _exec_modify_stat(data: dict, context: BattleContext, owner: Mecha) -> None:
        """修改属性 (modify_stat)
        
        通常用于战斗中的永久/半永久属性变化 (Debuff)。
        这应该通过施加一个新的 Buff (Effect) 来实现，而不是直接改属性。
        直接改属性会破坏 "属性 = 基础 + 修正" 的计算逻辑。
        
        如果非要直接改，那只能改 base stat，这通常是永久性的 (比如成长)。
        
        如果是临时 Debuff (如 "护甲破碎")，应该使用 apply_effect。
        """
        pass

    @staticmethod
    def _exec_apply_effect(data: dict, context: BattleContext, owner: Mecha) -> None:
        """为目标机体施加新的状态效果 (Buff/Debuff)。

        Args:
            data: 配置数据，包含 'effect_id' 效果 ID 和可选的 'duration'
            context: 战斗上下文
            owner: 效果持有人
        """
        target = SideEffectExecutor._get_target(data, context, owner)
        if not target: return
        
        effect_id = data.get("effect_id")
        if not effect_id: return
        
        from .effect_factory import EffectFactory
        # 创建效果并注入
        new_effects = EffectFactory.create_effect(effect_id, duration=data.get("duration", 1))
        for eff in new_effects:
            target.effects.append(eff)
            print(f"   [Effect] 副作用触发: 为 {target.name} 施加了 [{eff.name}] ({eff.id})")

