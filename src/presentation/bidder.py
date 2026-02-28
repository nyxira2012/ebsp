"""
L2 剧本解构层 - 动反双轨独立竞标 (Dual-Track Bidding)

职责：将传统"大一统模板"解耦为 Action（攻击方）与 Reaction（防御方）两段独立剧本。
核心理念：攻守分离，万物皆可组。10种攻击 + 10种受击 = 100种组合。
"""

import random
import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass, field

from .models import RawAttackEvent
from .constants import Channel, VisualIntent
from .template import ActionBone, ReactionBone

logger = logging.getLogger(__name__)


@dataclass
class BidResult:
    """竞标结果"""
    action_bone: Optional[ActionBone] = None
    reaction_bone: Optional[ReactionBone] = None
    action_candidates: int = 0
    reaction_candidates: int = 0


class DualBidder:
    """
    双轨独立竞标器。

    Action 竞标：过滤 intent 匹配 + cooldown 清零的 ActionBone 列表
    Reaction 竞标：过滤 channel 匹配 + physics_class 兼容的 ReactionBone 列表

    两次竞标完全独立，互不影响。
    """

    def __init__(self, action_bones: List[ActionBone], reaction_bones: List[ReactionBone]):
        self.action_bones = action_bones
        self.reaction_bones = reaction_bones
        # 冷却跟踪：bone_id -> 剩余冷却回合
        self._cooldowns: dict[str, int] = {}

    def bid(self, event: RawAttackEvent, channel: Channel) -> Tuple[Optional[ActionBone], Optional[ReactionBone]]:
        """
        执行双轨独立竞标。

        Args:
            event: 原始攻击事件
            channel: L1 层路由决定的频道

        Returns:
            (ActionBone, ReactionBone) 元组，可能为 None
        """
        # Action 竞标：基于意图
        action_bone = self._bid_action(event)

        # Reaction 竞标：基于频道 + 物理类兼容
        reaction_bone = self._bid_reaction(event, channel)

        # 更新冷却
        if action_bone:
            self._cooldowns[action_bone.bone_id] = getattr(action_bone, 'cooldown', 0)
        if reaction_bone:
            self._cooldowns[reaction_bone.bone_id] = getattr(reaction_bone, 'cooldown', 0)

        return action_bone, reaction_bone

    def _bid_action(self, event: RawAttackEvent) -> Optional[ActionBone]:
        """Action 竞标：匹配意图，physics_class 软约束，排除冷却中"""
        from .intent_extractor import IntentExtractor

        intent = IntentExtractor.extract_intent(event.weapon_type, event.weapon_tags)
        physics_class = event.physics_class

        # 首先按 intent 和 cooldown 过滤
        candidates = [
            bone for bone in self.action_bones
            if bone.intent == intent
            and self._cooldowns.get(bone.bone_id, 0) <= 0
        ]

        if not candidates:
            logger.warning(f"[Bidder] Action 竞标失败: 无匹配 intent={intent} 的 ActionBone"
                          f" (总库大小: {len(self.action_bones)})")
            return None

        # physics_class 软约束：匹配者权重 * 2，不匹配者权重 * 0.3
        weights = []
        for bone in candidates:
            base_weight = getattr(bone, 'weight', 1.0)
            if bone.physics_class == physics_class:
                weights.append(base_weight * 2.0)
            else:
                weights.append(base_weight * 0.3)

        # 如果没有高权重候选，发出警告
        if max(weights) < 1.0:
            logger.warning(f"[Bidder] Action 竞标警告: intent={intent} 匹配但 physics_class={physics_class} 不匹配"
                          f" (候选: {[b.physics_class for b in candidates]})")

        # 加权随机选择
        return random.choices(candidates, weights=weights, k=1)[0]

    def _bid_reaction(self, event: RawAttackEvent, channel: Channel) -> Optional[ReactionBone]:
        """Reaction 竞标：匹配频道，physics_class 软约束，排除冷却中"""
        physics_class = event.physics_class
        attack_result = event.attack_result

        # 首先按 channel 和 cooldown 过滤
        candidates = [
            bone for bone in self.reaction_bones
            if bone.channel == channel
            and self._cooldowns.get(bone.bone_id, 0) <= 0
        ]

        if not candidates:
            logger.warning(f"[Bidder] Reaction 竞标失败: 无匹配 channel={channel.value} 的 ReactionBone"
                          f" (总库大小: {len(self.reaction_bones)})")
            return None

        # 进一步按 attack_result 过滤（如果候选中有指定 attack_result 的模板）
        result_filtered = [
            bone for bone in candidates
            if getattr(bone, 'attack_result', None) == attack_result
            or getattr(bone, 'attack_result', None) is None
        ]

        # 如果有匹配 attack_result 的候选，优先使用它们
        exact_match = [bone for bone in result_filtered if getattr(bone, 'attack_result', None) == attack_result]
        if exact_match:
            candidates = exact_match
        else:
            candidates = result_filtered

        # physics_class 软约束：匹配者权重 * 2，不匹配者权重 * 0.5
        weights = []
        for bone in candidates:
            base_weight = getattr(bone, 'weight', 1.0)
            if bone.physics_class == physics_class:
                weights.append(base_weight * 2.0)
            else:
                weights.append(base_weight * 0.5)

        # 如果没有高权重候选，发出警告
        if max(weights) < 1.0:
            logger.warning(f"[Bidder] Reaction 竞标警告: channel={channel.value} 匹配但 physics_class={physics_class} 不匹配"
                          f" (候选: {[b.physics_class for b in candidates]})")

        # 加权随机选择
        return random.choices(candidates, weights=weights, k=1)[0]

    def tick_cooldowns(self):
        """每回合调用，递减所有冷却计数"""
        for bone_id in list(self._cooldowns.keys()):
            if self._cooldowns[bone_id] > 0:
                self._cooldowns[bone_id] -= 1
