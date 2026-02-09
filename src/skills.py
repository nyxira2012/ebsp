"""
技能与效果系统
负责管理所有战斗技能、精神指令和状态效果的注册与执行
"""

from typing import Callable, Any, TypeAlias, List
from .models import Mecha, BattleContext, Effect, Modifier
from .skill_system.processor import EffectProcessor
from .skill_system.effect_factory import EffectFactory

# Hook 回调函数签名: (当前值, 上下文) -> 修改后的值
HookCallback: TypeAlias = Callable[[Any, BattleContext], Any]

class SkillRegistry:
    """技能注册表"""
    _hooks: dict[str, list[HookCallback]] = {}
    _skills: dict[str, Callable] = {}
    _callbacks: dict[str, Callable] = {} # 注册的回调函数 (op=callback)

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
    def register_callback(cls, callback_id: str) -> Callable:
        """注册回调函数 (供 Effect operation='callback' 使用)"""
        def decorator(func: Callable) -> Callable:
            cls._callbacks[callback_id] = func
            return func
        return decorator

    @classmethod
    def get_callback(cls, callback_id: str) -> Callable | None:
        """获取回调函数"""
        return cls._callbacks.get(callback_id)

    @classmethod
    def process_hook(cls, hook_point: str, initial_value: Any, context: BattleContext) -> Any:
        """执行指定钩子点的所有回调，流水线式处理数值 (委托给 EffectProcessor)"""
        
        # 1. 遍历全局/被动钩子 (Legacy support)
        value = initial_value
        if hook_point in cls._hooks:
            for callback in cls._hooks[hook_point]:
                try:
                    value = callback(value, context)
                except Exception as e:
                    print(f"Error in legacy hook {hook_point}: {e}")

        # 2. 调用通用的 EffectProcessor
        value = EffectProcessor.process(hook_point, value, context)
        
        return value

@SkillRegistry.register_callback("cb_potential")
def cb_potential(val, ctx, owner):
    """底力: HP越低减伤越高"""
    ratio = 1.0 - (owner.current_hp / owner.max_hp)
    bonus = 0.5 * (ratio ** 2)
    return val + bonus

@SkillRegistry.register_callback("cb_learning")
def cb_learning(val, ctx, owner):
    """学习电脑: 随回合数提升命中"""
    bonus = ctx.round_number * 5.0
    return val + bonus

@SkillRegistry.register_callback("cb_gn_recover")
def cb_gn_recover(val, ctx, owner):
    """GN炉: 每回合回复 EN"""
    owner.current_en = min(owner.max_en, owner.current_en + 10)
    print(f"   [Trait] {owner.name} GN炉回复了 10 EN")
    return val


class EffectManager:
    """效果管理器"""
    
    @staticmethod
    def add_effect(target: Mecha, effect_id: str, duration: int = 1) -> None:
        """添加状态效果 (通过 EffectFactory 创建)"""
        # 使用工厂创建标准 Effect 列表
        new_effects = EffectFactory.create_effect(effect_id, duration)
        
        for new_eff in new_effects:
            # 检查互斥或覆盖逻辑
            found = False
            for existing in target.effects:
                # 注意: 同名 Effect (id相同) 应该刷新 duration?
                # 对于 spirit_focus 会生成 spirit_focus_hit, spirit_focus_dodge
                if existing.id == new_eff.id:
                    existing.duration = max(existing.duration, duration)
                    print(f"   [Update] {target.name} 的 [{new_eff.id}] 持续时间刷新为 {existing.duration}")
                    found = True
                    break
            
            if not found:
                target.effects.append(new_eff)
                print(f"   [Added] {target.name} 获得了 [{new_eff.id}] (持续 {duration} 回合)")

    @staticmethod
    def tick_effects(target: Mecha) -> None:
        """回合结束/开始时更新效果持续时间"""
        active_effects = []
        for effect in target.effects:
            # 永久效果 (-1) 不减少
            if effect.duration != -1:
                # 只在 duration > 0 时减少
                if effect.duration > 0:
                   effect.duration -= 1
            
            # 检查是否过期
            # 注意: duration=0 意味着本回合结束过期
            # 我们在这里 tick，如果减完是 0，说明刚刚过期？
            # 或者我们在使用时检查 duration > 0?
            # 通常 tick 是回合结束做。如果减为0，则移除。
            
            if effect.duration != 0: 
                active_effects.append(effect)
            else:
                print(f"   [Expired] {target.name} 的 [{effect.id}] 效果结束了")
        
        target.effects = active_effects


class TraitManager:
    """特性管理器 - 负责机体和驾驶员特性的初始化"""
    
    @staticmethod
    def apply_traits(mecha: Mecha) -> None:
        """为机体应用所有特性效果 (数据驱动)"""
        if not mecha.traits:
            return
            
        print(f"   [System] 为 {mecha.name} 初始化特性效果...")
        
        # 避免重复初始化
        existing_trait_ids = {e.id for e in mecha.effects}
        
        from .skill_system.effect_factory import EffectFactory
        
        for trait_id in mecha.traits:
            # 从工厂获取特性对应的效果
            new_effects = EffectFactory.create_trait_effects(trait_id)
            
            if not new_effects:
                print(f"      ⚠️  警告: 特性 [{trait_id}] 未定义或无动态效果")
                continue

            for eff in new_effects:
                # 检查是否已存在同名效果 (避免多次 apply)
                if eff.id not in existing_trait_ids:
                    mecha.effects.append(eff)
                    print(f"      - 激活永久特性: {eff.name} ({eff.id})")


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
