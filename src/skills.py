"""
技能与效果系统
负责管理所有战斗技能、精神指令和状态效果的注册与执行
"""

from typing import Callable, Any, TypeAlias
from .models import Mecha, BattleContext, Effect, Modifier

# Hook 回调函数签名: (当前值, 上下文) -> 修改后的值
HookCallback: TypeAlias = Callable[[Any, BattleContext], Any]

class SkillRegistry:
    """技能注册表"""
    _hooks: dict[str, list[HookCallback]] = {}
    _skills: dict[str, Callable] = {}

    @classmethod
    def register_hook(cls, hook_point: str) -> Callable:
        """装饰器: 注册钩子处理函数"""
        def decorator(func: HookCallback) -> HookCallback:
            if hook_point not in cls._hooks:
                cls._hooks[hook_point] = []
            cls._hooks[hook_point].append(func)
            return func
        return decorator

    @classmethod
    def process_hook(cls, hook_point: str, initial_value: Any, context: BattleContext) -> Any:
        """执行指定钩子点的所有回调，流水线式处理数值"""
        value = initial_value
        
        # 1. 遍历全局/被动钩子
        if hook_point in cls._hooks:
            for callback in cls._hooks[hook_point]:
                try:
                    value = callback(value, context)
                except Exception as e:
                    print(f"Error in hook {hook_point}: {e}")

        # 2. 遍历 Buff/Debuff 带来的动态钩子 (Effect Hooks)
        # 注意: 这里需要 Effect 本身能提供 Hook 逻辑，或者我们在 Effect payload 里定义 Hook
        # 简化实现: 硬编码常见 Effect 的处理逻辑，或者让 Effect 注册临时 Hook
        
        # 临时方案: 检查 context 中相关角色的 effects
        # 攻击方 Effect
        if context.attacker:
            value = cls._process_entity_effects(context.attacker, hook_point, value, context)
        
        # 防御方 Effect (如果不仅是自己回合)
        if context.defender:
            value = cls._process_entity_effects(context.defender, hook_point, value, context)

        return value

    @staticmethod
    def _process_entity_effects(entity: Mecha, hook_point: str, current_value: Any, context: BattleContext) -> Any:
        """处理实体的状态效果对钩子的影响"""
        for effect in entity.effects:
            # 精神指令处理
            if effect.id == "spirit_strike" and hook_point == "PRE_HIT_RATE":
                # 必中: 如果是攻击方，命中率设为 100 (暂不考虑对方必闪，下一层处理)
                if entity == context.attacker:
                    return 100.0
            
            elif effect.id == "spirit_alert" and hook_point == "PRE_HIT_RATE":
                # 必闪: 如果是防御方，攻击方命中率设为 0
                if entity == context.defender:
                    return 0.0
            
            elif effect.id == "spirit_valor" and hook_point == "PRE_DAMAGE_CALC":
                # 热血: 伤害 x2
                if entity == context.attacker:
                    return current_value * 2.0
            
            elif effect.id == "spirit_iron_wall" and hook_point == "PRE_MITIGATION":
                # 铁壁: 最终受到伤害 x0.25
                if entity == context.defender:
                    return current_value * 0.25

            elif effect.id == "spirit_focus":
                # 集中: 命中+30%, 闪避+30%
                if hook_point == "PRE_HIT_RATE" and entity == context.attacker:
                    return current_value + 30.0
                if hook_point == "PRE_EVADE_RATE" and entity == context.defender:
                    return current_value + 30.0

        return current_value


class EffectManager:
    """效果管理器"""
    
    @staticmethod
    def add_effect(target: Mecha, effect_id: str, duration: int = 1) -> None:
        """添加状态效果"""
        # 检查互斥或覆盖逻辑
        for existing in target.effects:
            if existing.id == effect_id:
                existing.duration = max(existing.duration, duration) # 刷新持续时间
                print(f"   🔄 {target.name} 的 [{effect_id}] 持续时间刷新为 {existing.duration}")
                return

        new_effect = Effect(id=effect_id, name=effect_id, duration=duration)
        target.effects.append(new_effect)
        print(f"   ✨ {target.name} 获得了 [{effect_id}] (持续 {duration} 回合)")

    @staticmethod
    def tick_effects(target: Mecha) -> None:
        """回合结束/开始时更新效果持续时间"""
        active_effects = []
        for effect in target.effects:
            if effect.duration > 0:
                effect.duration -= 1
            
            if effect.duration != 0: # -1 代表无限，正数代表剩余
                active_effects.append(effect)
            else:
                print(f"   💤 {target.name} 的 [{effect.id}] 效果结束了")
        
        target.effects = active_effects


class TraitManager:
    """特性管理器 (Passive Traits)"""
    
    @staticmethod
    def apply_traits(mecha: Mecha) -> None:
        """应用机体的所有特性技能"""
        for trait_id in mecha.traits:
            TraitManager._apply_single_trait(mecha, trait_id)

    @staticmethod
    def _apply_single_trait(mecha: Mecha, trait_id: str) -> None:
        """应用单个特性 (静态修正)"""
        # 示例技能: 学习型计算机
        if trait_id == "trait_learning_computer":
            mecha.stat_modifiers['hit_rate'] = mecha.stat_modifiers.get('hit_rate', 0) + 10.0
            mecha.stat_modifiers['precision'] = mecha.stat_modifiers.get('precision', 0) + 5.0
            print(f"  ✨ 特性 [{trait_id}] 已应用: 命中+10, 精准+5")

        # 示例技能: NT感知
        elif trait_id == "trait_newtype_sense":
            mecha.stat_modifiers['dodge_rate'] = mecha.stat_modifiers.get('dodge_rate', 0) + 15.0
            # 反应值是 Pilot 属性，需要处理
            mecha.pilot.stat_modifiers['stat_reaction'] = mecha.pilot.stat_modifiers.get('stat_reaction', 0) + 10
            print(f"  ✨ 特性 [{trait_id}] 已应用: 躲闪+15, 反应+10")

        # 示例技能: 强化装甲
        elif trait_id == "trait_enhanced_armor":
            mecha.stat_modifiers['defense_level'] = mecha.stat_modifiers.get('defense_level', 0) + 30
            mecha.block_value += 50 # 这里的 block_value 也可以改为 modifier
            print(f"  ✨ 特性 [{trait_id}] 已应用: 装甲+30, 格挡值+50")
            
        else:
            print(f"  ⚠️  警告: 未知特性 [{trait_id}]")

# ============================================================================
# 精神指令 (Spirit Commands) 
# ============================================================================

class SpiritCommands:
    """常见精神指令库"""
    
    @staticmethod
    def activate_strike(user: Mecha):
        """必中: 一回合内命中率 100%"""
        EffectManager.add_effect(user, "spirit_strike", duration=1)

    @staticmethod
    def activate_alert(user: Mecha):
        """必闪: 下一次回避率 100% (触发后消耗)"""
        # 持续时间设为 -1 (无限)，但在回避触发后移除(尚未实现自动移除逻辑)
        # 暂时设为 1 回合
        EffectManager.add_effect(user, "spirit_alert", duration=1)

    @staticmethod
    def activate_valor(user: Mecha):
        """热血: 下一次攻击伤害 2 倍"""
        EffectManager.add_effect(user, "spirit_valor", duration=1)

    @staticmethod
    def activate_iron_wall(user: Mecha):
        """铁壁: 一回合内受到伤害 1/4"""
        EffectManager.add_effect(user, "spirit_iron_wall", duration=1)
        
    @staticmethod
    def activate_focus(user: Mecha):
        """集中: 一回合内命中/回避 +30%"""
        EffectManager.add_effect(user, "spirit_focus", duration=1)
