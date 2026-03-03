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
from .constants import Channel, MotionStyle, DamageMaterial, TemplateTier
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

    Action 竞标：强制匹配 MotionStyle，DamageMaterial 作为加分项
    Reaction 竞标：强制匹配 DamageMaterial，MotionStyle 作为加分项

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
        """Action 竞标：T2 精确匹配 → T2 降级 → T3 硬编码兜底"""
        motion_style = event.motion_style
        damage_material = event.damage_material

        # 1. T2 精确匹配：动作风格 + 材质
        candidates = [
            bone for bone in self.action_bones
            if bone.motion_style == motion_style
            and bone.damage_material == damage_material
            and self._cooldowns.get(bone.bone_id, 0) <= 0
        ]

        if candidates:
            weights = [getattr(bone, 'weight', 1.0) for bone in candidates]
            return random.choices(candidates, weights=weights, k=1)[0]

        # 2. T2 降级：动作风格 + GENERIC 材质
        candidates = [
            bone for bone in self.action_bones
            if bone.motion_style == motion_style
            and bone.damage_material == "GENERIC"
            and self._cooldowns.get(bone.bone_id, 0) <= 0
        ]

        if candidates:
            weights = [getattr(bone, 'weight', 1.0) for bone in candidates]
            return random.choices(candidates, weights=weights, k=1)[0]

        # 3. T3 硬编码兜底：无匹配模板时的最终 fallback
        return ActionBone(
            bone_id="T3_FALLBACK_ACTION",
            motion_style="ANY",
            text_fragments=["{attacker}使用{weapon}展开了攻击！"],
            anim_id="anim_generic_attack",
            tier=TemplateTier.T3_FALLBACK
        )

    def _bid_reaction(self, event: RawAttackEvent, channel: Channel) -> Optional[ReactionBone]:
        """Reaction 竞标：T2 精确匹配 → T2 降级 → T3 硬编码兜底"""
        damage_material = event.damage_material
        motion_style = event.motion_style

        # 1. 基础过滤：频道 + 精确匹配 attack_result + 冷却
        t2_candidates = [
            bone for bone in self.reaction_bones
            if bone.channel == channel
            and bone.attack_result == event.attack_result  # 精确匹配，无通配
            and self._cooldowns.get(bone.bone_id, 0) <= 0
        ]

        # 2. T2 层：damage_material 匹配
        material_matches = [
            bone for bone in t2_candidates
            if bone.damage_material == damage_material
        ]
        if material_matches:
            # 2.1 优先精确匹配 motion_style
            motion_exact = [
                bone for bone in material_matches
                if bone.motion_style == motion_style
            ]
            if motion_exact:
                return self._weighted_select(motion_exact, motion_style)

            # 2.2 否则选择 ANY 或加权选择
            return self._weighted_select(material_matches, motion_style)

        # 3. T2 降级：GENERIC 材质
        generic_matches = [
            bone for bone in t2_candidates
            if bone.damage_material == "GENERIC"
        ]
        if generic_matches:
            return self._weighted_select(generic_matches, motion_style)

        # 4. T3 硬编码兜底：无匹配模板时的最终 fallback
        result_texts = {
            "HIT": ["{defender}被击中了。"],
            "CRIT": ["{defender}遭受了沉重打击！"],
            "BLOCK": ["{defender}挡住了攻击。"],
            "PARRY": ["{defender}招架了攻击。"],
            "DODGE": ["{defender}巧妙地躲开了。"],
            "MISS": ["攻击没能命中{defender}。"],
        }

        # 致死频道强制覆盖描述
        if channel == Channel.FATAL:
            fragments = ["{defender}被彻底摧毁了。"]
        else:
            fragments = result_texts.get(event.attack_result, ["{defender}受到了影响。"])

        return ReactionBone(
            bone_id=f"T3_FALLBACK_REACTION_{event.attack_result}",
            channel=channel,
            damage_material="GENERIC",
            text_fragments=fragments,
            tier=TemplateTier.T3_FALLBACK,
            attack_result=event.attack_result
        )

    def _weighted_select(self, candidates: List, motion_style: str) -> Optional:
        """加权随机选择（基于 motion_style）"""
        weights = []
        for bone in candidates:
            score = getattr(bone, 'weight', 1.0)

            # 动作风格加分
            if bone.motion_style == motion_style:
                score *= 2.5
            elif bone.motion_style != "ANY":
                score *= 0.2

            weights.append(score)

        return random.choices(candidates, weights=weights, k=1)[0]

    def tick_cooldowns(self):
        """每回合调用，递减所有冷却计数"""
        for bone_id in list(self._cooldowns.keys()):
            if self._cooldowns[bone_id] > 0:
                self._cooldowns[bone_id] -= 1
