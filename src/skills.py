"""
技能与效果系统
负责管理所有战斗技能、精神指令和状态效果的注册与执行
"""

from typing import Any, TypeAlias, Callable
from .models import Mecha, BattleContext, AttackResult, WeaponType, TriggerEvent
from .skill_system.processor import EffectProcessor
from .skill_system.effect_factory import EffectFactory
from .skill_system.event_manager import EventManager

# Hook 回调函数签名: (当前值, 上下文) -> 修改后的值
HookCallback: TypeAlias = Any


class SkillRegistry:
    """技能注册表"""
    _hooks: dict[str, list] = {}
    _callbacks: dict[str, Callable] = {}

    @classmethod
    def register_hook(cls, hook_point: str) -> Callable:
        """装饰器：注册传统的钩子处理函数。

        Args:
            hook_point: 钩子点名称。

        Returns:
            装饰器函数。
        """
        def decorator(func: HookCallback) -> HookCallback:
            if hook_point not in cls._hooks:
                cls._hooks[hook_point] = []
            cls._hooks[hook_point].append(func)
            return func
        return decorator

    @classmethod
    def register_callback(cls, callback_id: str) -> Callable:
        """装饰器：注册供 Effect 使用的回调函数。

        Args:
            callback_id: 回调函数的唯一标识符 (对应 JSON 中的 value)。

        Returns:
            装饰器函数。
        """
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
        """执行指定钩子点的所有逻辑，返回最终计算结果。

        处理流程：
        1. 执行传统的修饰器钩子库 (_hooks)。
        2. 委托给 EffectProcessor 处理机体携带的动态 Effect。

        Args:
            hook_point: 钩子点名称。
            initial_value: 初始数值。
            context: 战斗上下文快照。

        Returns:
            经过流水线处理后的最终数值。
        """
        value = initial_value

        # 1. 遍历全局/被动钩子 (Global/Passive hooks)
        if hook_point in cls._hooks:
            for callback in cls._hooks[hook_point]:
                try:
                    value = callback(value, context)
                except Exception as e:
                    print(f"Error in legacy hook {hook_point}: {e}")

        # 2. 调用通用的 EffectProcessor
        return EffectProcessor.process(hook_point, value, context)


# ============================================================================
# 回调函数定义
# ============================================================================

@SkillRegistry.register_callback("cb_potential")
def cb_potential(val: Any, ctx: BattleContext, owner: Mecha) -> Any:
    """底力回调：根据当前 HP 百分比提升数值 (减伤等)。

    公式: bonus = 0.5 * ((1 - HP_ratio) ^ 2)
    """
    ratio = 1.0 - (owner.current_hp / owner.final_max_hp)
    return val + 0.5 * (ratio ** 2)


@SkillRegistry.register_callback("cb_learning")
def cb_learning(val, ctx, owner):
    """学习电脑: 随回合数提升命中"""
    return val + ctx.round_number * 5.0


@SkillRegistry.register_callback("cb_gn_recover")
def cb_gn_recover(val, ctx, owner):
    """GN炉: 每回合回复 EN（永久特性，不产生事件）"""
    owner.current_en = min(owner.final_max_en, owner.current_en + 10)
    return val


@SkillRegistry.register_callback("cb_miracle_hit")
def cb_miracle_hit(val, ctx, owner):
    """奇迹: 强制命中 (将 HOOK_OVERRIDE_RESULT 设为 HIT)"""
    if val is None or val == AttackResult.MISS:
        return AttackResult.HIT
    return val


@SkillRegistry.register_callback("cb_instinct_dodge")
def cb_instinct_dodge(val, ctx, owner):
    """本能: 30%概率将 HIT 扭转为 DODGE"""
    import random

    if val == AttackResult.HIT:
        triggered = random.random() < 0.3
        EventManager.publish_event(TriggerEvent(
            skill_id="spirit_instinct",
            owner=owner,
            hook_name="OVERRIDE_RESULT",
            effect_text="本能闪避" if triggered else "本能未触发",
            old_value=AttackResult.HIT,
            new_value=AttackResult.DODGE if triggered else AttackResult.HIT,
            probability=0.3,
            triggered=triggered
        ))
        return AttackResult.DODGE if triggered else val
    return val


@SkillRegistry.register_callback("cb_auto_repair")
def cb_auto_repair(damage, ctx, owner):
    """自动修复: 受到伤害后回复 HP（永久特性，不产生事件）"""
    heal = int(damage * 0.2)
    owner.current_hp = min(owner.final_max_hp, owner.current_hp + heal)
    return damage


@SkillRegistry.register_callback("cb_ablat")
def cb_ablat(damage, ctx, owner):
    """烧蚀装甲: 对光束伤害减少200点（永久特性，不产生事件）"""
    if ctx.weapon and ctx.weapon.weapon_type in (WeaponType.SHOOTING, WeaponType.MELEE):
        damage = max(0, damage - 200)
    return damage


@SkillRegistry.register_callback("cb_rage_will")
def cb_rage_will(damage, ctx, owner):
    """气魄: 造成伤害时气力+3（永久特性，不产生事件）"""
    owner.modify_will(3)
    return damage


@SkillRegistry.register_callback("cb_vampirism")
def cb_vampirism(damage, ctx, owner):
    """吸血: 回复造成伤害的10% HP（永久特性，不产生事件）"""
    heal = int(damage * 0.1)
    owner.current_hp = min(owner.final_max_hp, owner.current_hp + heal)
    return damage


@SkillRegistry.register_callback("cb_effort_exp")
def cb_effort_exp(val, ctx, owner):
    """努力: 击坠时获得双倍经验（纯日志，不产生事件）"""
    return val


@SkillRegistry.register_callback("cb_mercy_will")
def cb_mercy_will(val, ctx, owner):
    """慈悲: 击坠时回复20点气力（永久特性，不产生事件）"""
    owner.modify_will(20)
    return val


@SkillRegistry.register_callback("cb_reunion")
def cb_reunion(val, ctx, owner):
    """再动: 概率获得额外行动机会（纯日志，不产生事件）"""
    return val


def _restore_en(owner: Mecha, amount: int) -> None:
    """辅助函数：回复 EN"""
    owner.current_en = min(owner.max_en, owner.current_en + amount)


@SkillRegistry.register_callback("cb_quick_reload_en")
def cb_quick_reload_en(val, ctx, owner):
    """快速装填: 攻击结束回复15 EN（永久特性，不产生事件）"""
    _restore_en(owner, 15)
    return val


@SkillRegistry.register_callback("cb_energy_save")
def cb_energy_save(val, ctx, owner):
    """省能源: 每回合回复5 EN（永久特性，不产生事件）"""
    _restore_en(owner, 5)
    return val


@SkillRegistry.register_callback("cb_regen_hp")
def cb_regen_hp(val, ctx, owner):
    """再生: 每回合回复5% HP（永久特性，不产生事件）"""
    heal = int(owner.max_hp * 0.05)
    owner.current_hp = min(owner.final_max_hp, owner.current_hp + heal)
    return val


@SkillRegistry.register_callback("cb_spirit_boost")
def cb_spirit_boost(val, ctx, owner):
    """精神增幅: 战斗结束回复50% SP（纯日志，不产生事件）"""
    return val


@SkillRegistry.register_callback("cb_morale_en")
def cb_morale_en(val, ctx, owner):
    """士气: 战斗结束回复30 EN（永久特性，不产生事件）"""
    _restore_en(owner, 30)
    return val


class EffectManager:
    """效果管理器"""
    
    @staticmethod
    def add_effect(target: Mecha, effect_id: str, duration: int = 1) -> None:
        """为目标机体添加状态效果。

        如果目标已存在同名效果，则取两者的最大剩余时长进行刷新。

        Args:
            target: 目标机体。
            effect_id: 效果 ID (来自配置)。
            duration: 持续回合数。
        """
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
        """更新机体所有效果的持续时间，并在过期时移除。

        永久效果 (duration = -1) 不受影响。

        Args:
            target: 目标机体。
        """
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
        """初始化机体自带的特性，将其转化为持久效果 (Effect)。

        Args:
            mecha: 目标机体。
        """
        if not mecha.skills:
            return
            
        print(f"   [System] 为 {mecha.name} 初始化特性效果...")
        
        # 避免重复初始化
        existing_trait_ids = {e.id for e in mecha.effects}
        
        from .skill_system.effect_factory import EffectFactory
        
        for trait_id in mecha.skills:
            # 从工厂获取特性对应的效果
            new_effects = EffectFactory.create_trait_effects(trait_id)
            
            if not new_effects:
                print(f"      [WARNING] 特性 [{trait_id}] 未定义或无动态效果")
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

    @staticmethod
    def activate_dream(user: Mecha):
        """梦境: 强制先手"""
        EffectManager.add_effect(user, "spirit_dream", duration=1)

    @staticmethod
    def activate_suppress(user: Mecha):
        """威压: 强制先手"""
        EffectManager.add_effect(user, "spirit_suppress", duration=1)

    @staticmethod
    def activate_confuse(user: Mecha):
        """搅乱: 敌人命中率降低"""
        EffectManager.add_effect(user, "spirit_confuse", duration=1)

    @staticmethod
    def activate_miracle(user: Mecha):
        """奇迹: 下次攻击必定命中"""
        EffectManager.add_effect(user, "spirit_miracle", duration=1)

    @staticmethod
    def activate_instinct(user: Mecha):
        """本能: 30%概率闪避攻击"""
        EffectManager.add_effect(user, "spirit_instinct", duration=1)

    @staticmethod
    def activate_fury(user: Mecha):
        """激怒: 暴击倍率×1.5"""
        EffectManager.add_effect(user, "spirit_fury", duration=1)

    @staticmethod
    def activate_rage(user: Mecha):
        """气魄: 造成伤害时气力+3"""
        EffectManager.add_effect(user, "spirit_rage", duration=1)

    @staticmethod
    def activate_effort(user: Mecha):
        """努力: 击坠时获得双倍经验"""
        EffectManager.add_effect(user, "spirit_effort", duration=1)

    @staticmethod
    def activate_protract(user: Mecha):
        """拖延: 战斗回合+5"""
        EffectManager.add_effect(user, "spirit_protract", duration=1)

    @staticmethod
    def activate_determination(user: Mecha):
        """执念: 战斗强制继续1次"""
        EffectManager.add_effect(user, "spirit_determination", duration=1)

    @staticmethod
    def activate_reunion(user: Mecha):
        """再动: 概率获得额外行动"""
        EffectManager.add_effect(user, "spirit_reunion", duration=1)
