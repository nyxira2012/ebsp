"""
Event Mapper - 演出系统核心编排器 (CPS v5.0)

架构：四层导演金字塔 (4-Layer Pipeline)
    L1: ODR Router → Channel (结局前置路由)
    L2: Dual Bidder → ActionBone + ReactionBone (双轨竞标)
    L3: Assembler → final_text (原子拼装 + SVI + DHL)
    L4: AV Dispatcher → PresentationAttackEvent (视听调度)

入口：map_attack() - 将 RawAttackEvent 转换为 PresentationAttackEvent 序列
"""

from typing import List, Optional

from .models import RawAttackEvent, PresentationAttackEvent
from .constants import PresentationTag, TemplateTier, Channel
from .template import ActionBone, ReactionBone
from .router import OutcomeRouter
from .bidder import DualBidder
from .assembler import TextAssembler
from .av_dispatcher import AVDispatcher
from .scripted_manager import ScriptedPresentationManager


class EventMapper:
    """
    Event Mapper - 战斗事件的导演编排器

    核心职责：
    1. L1 ODR路由 - 根据战斗结局锁定演出频道
    2. L2 双轨竞标 - 独立选择Action和Reaction骨架
    3. L3 原子拼装 - 组装最终文本
    4. L4 AV调度 - 生成视听演出事件

    这是v5.0四层架构的唯一入口，所有旧路径逻辑已被移除。
    """

    def __init__(self, registry: Optional['TemplateRegistry'] = None):
        """
        初始化 EventMapper。

        Args:
            registry: 模板注册表，如果为None则创建默认实例
        """
        if registry is None:
            from .registry import TemplateRegistry
            self.registry = TemplateRegistry()
        else:
            self.registry = registry

        self.scripted_manager = ScriptedPresentationManager()

        # L2-L4 组件
        self._bidder: Optional[DualBidder] = None
        self._assembler = TextAssembler()
        self._av_dispatcher = AVDispatcher()

        # 初始化竞标器
        self._initialize_bidder()

    def _initialize_bidder(self):
        """初始化或重新初始化 DualBidder（在配置加载后调用）"""
        if hasattr(self.registry, 'action_bones') and hasattr(self.registry, 'reaction_bones'):
            action_bones = self.registry.action_bones
            reaction_bones = self.registry.reaction_bones

            # 只有在有数据时才初始化 bidder
            if action_bones or reaction_bones:
                self._bidder = DualBidder(action_bones, reaction_bones)
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"[EventMapper] DualBidder 初始化完成: "
                           f"{len(action_bones)} action_bones, {len(reaction_bones)} reaction_bones")
            else:
                self._bidder = None
                import logging
                logging.getLogger(__name__).warning(
                    "[EventMapper] 注册表中没有 ActionBone 或 ReactionBone，"
                    "将使用默认生成逻辑"
                )

    def map_attack(self, raw_event: RawAttackEvent) -> List[PresentationAttackEvent]:
        """
        主入口：将原始战斗事件转换为演出事件序列

        流程：
        1. L1 ODR路由 - 确定演出频道 (FATAL/EVADE/IMPACT/SPECIAL)
        2. T0拦截检查 - 是否有脚本强制模板
        3. L2 双轨竞标 - 选择 ActionBone + ReactionBone
        4. L3 原子拼装 - 组装最终文本
        5. L4 AV调度 - 生成 PresentationAttackEvent 对

        Returns:
            List[PresentationAttackEvent]: 包含 [Action, Reaction] 的事件列表
        """
        # === L1: 绝对律令层 - 结局前置路由 ===
        channel = OutcomeRouter.route(raw_event)

        # T0 拦截（脚本优先，独立于流水线）
        forced_tmpl = self.scripted_manager.get_forced_template(
            raw_event.round_number,
            raw_event.attacker_id,
            raw_event.defender_id
        )

        if forced_tmpl:
            # T0 脚本事件 - 直接由AVDispatcher处理
            return self._handle_scripted_event(raw_event, forced_tmpl, channel)

        # === L2-L4: 四层架构处理 ===
        return self._execute_pipeline(raw_event, channel)

    def _execute_pipeline(self, raw_event: RawAttackEvent, channel: Channel) -> List[PresentationAttackEvent]:
        """
        执行 L2-L4 的四层架构流水线。

        这是 v5.0 的核心逻辑，替代了旧版的 selector + template 方式。
        """
        # === L2: 双轨独立竞标 ===
        if self._bidder:
            action_bone, reaction_bone = self._bidder.bid(raw_event, channel)
        else:
            # 无竞标器时使用None（Assembler会处理）
            action_bone, reaction_bone = None, None

        # === L3: 原子拼装 ===
        action_text, reaction_text, hit_part = self._assembler.assemble(
            action_bone, reaction_bone, raw_event, channel
        )

        # === L4: AV 调度 ===
        action_event, reaction_event = self._av_dispatcher.dispatch(
            raw_event,
            action_text,
            reaction_text,
            channel,
            action_anim_id=getattr(action_bone, 'anim_id', None) if action_bone else None,
            reaction_anim_id=getattr(reaction_bone, 'anim_id', None) if reaction_bone else None,
            vfx_ids=getattr(reaction_bone, 'vfx_ids', []) if reaction_bone else [],
            sfx_ids=getattr(reaction_bone, 'sfx_ids', []) if reaction_bone else [],
            hit_location=hit_part,
            action_template_id=getattr(action_bone, 'bone_id', None) if action_bone else None,
            reaction_template_id=getattr(reaction_bone, 'bone_id', None) if reaction_bone else None,
        )

        return [action_event, reaction_event]

    def _handle_scripted_event(self, raw_event: RawAttackEvent, tmpl: 'PresentationTemplate',
                               channel: Channel) -> List[PresentationAttackEvent]:
        """
        处理T0脚本强制模板事件。

        T0模板通常是特殊剧情事件，不遵循标准的竞标流程。
        """
        from .template import PresentationTemplate

        # 使用模板中的文本和视觉效果
        action_text = tmpl.content.action_text.format(
            attacker=raw_event.attacker_name,
            defender=raw_event.defender_name,
            weapon=raw_event.weapon_name
        )
        reaction_text = tmpl.content.reaction_text.format(
            attacker=raw_event.attacker_name,
            defender=raw_event.defender_name,
            weapon=raw_event.weapon_name
        )

        # 使用AVDispatcher生成事件，但优先使用模板中的视觉设置
        action_event, reaction_event = self._av_dispatcher.dispatch(
            raw_event,
            action_text,
            reaction_text,
            channel,
            action_anim_id=tmpl.visuals.anim_id,
            reaction_anim_id=tmpl.visuals.anim_id,
            vfx_ids=tmpl.visuals.vfx_ids,
            sfx_ids=tmpl.visuals.sfx_ids,
            hit_location=None,
            action_template_id=tmpl.id,
            reaction_template_id=tmpl.id,
        )

        return [action_event, reaction_event]

    def advance_turn(self):
        """回合推进 - 更新冷却等状态"""
        if self._bidder:
            self._bidder.tick_cooldowns()
