from dataclasses import dataclass, field
from typing import List, Optional
from .constants import TemplateTier, MotionStyle, Channel

@dataclass
class TemplateConditions:
    """
    Conditions required for a template to be selected.
    """
    motion_style: Optional[MotionStyle] = None  # 动作风格（MDDC v5.1）
    result: Optional[str] = None  # MISS, DODGE, HIT, CRIT, BLOCK, PARRY
    weapon_type: Optional[str] = None
    required_tags: List[str] = field(default_factory=list)
    skill_id: Optional[str] = None  # For T1 Highlight templates
    hp_status: Optional[str] = None  # LETHAL, CRITICAL, MODERATE, LIGHT

    def matches(self, motion_style: MotionStyle, result: str, weapon_type: str, tags: List[str], skills: List[str], hp_status: Optional[str] = None) -> bool:
        if self.motion_style and self.motion_style != motion_style:
            return False
        if self.result and self.result != result:
            return False
        if self.weapon_type and self.weapon_type != weapon_type:
            return False
        if self.required_tags:
            if not all(tag in tags for tag in self.required_tags):
                return False
        if self.skill_id:
            if self.skill_id not in skills:
                return False
        if self.hp_status and self.hp_status != hp_status:
            return False
        return True

@dataclass
class TemplateContent:
    """
    Text content for the template.
    Supports format strings: {attacker}, {defender}, {weapon}.
    """
    action_text: str  # Text displayed during Attack phase
    reaction_text: str # Text displayed during Reaction phase

@dataclass
class TemplateVisuals:
    """
    Visual resource IDs.
    """
    anim_id: Optional[str] = None
    cam_id: Optional[str] = None
    vfx_ids: List[str] = field(default_factory=list)
    sfx_ids: List[str] = field(default_factory=list)

@dataclass
class PresentationTemplate:
    """
    A single presentation template definition (旧格式 - 大一统模板).
    保留用于 T0 脚本模板和向后兼容。
    """
    id: str
    tier: TemplateTier
    conditions: TemplateConditions
    content: TemplateContent
    visuals: TemplateVisuals
    priority_score: int = 0  # For T1 bidding (100=High, 50=Med)
    cooldown: int = 0        # Rounds to wait before showing again (to avoid repetition)


# =============================================================================
# Phase 2: 新格式 - 原子化骨架 (ActionBone + ReactionBone)
# =============================================================================

@dataclass
class ActionBone:
    """
    攻击方动作骨架 - 描述"谁、用什么、怎么打"。
    MDDC v5.1: 主要由 motion_style 驱动。
    """
    bone_id: str                      # 唯一标识
    motion_style: str                 # 动作风格（如 SLASH_LIGHT, SHOOT_INSTANT）
    text_fragments: List[str]         # 用于 L3 拼装的多段文本碎片
    anim_id: str                      # 动画资源ID
    damage_material: str = "ANY"      # 可选：对材质的特定限制（ANY 表示通配）
    tier: TemplateTier = TemplateTier.T2_TACTICAL
    priority_score: int = 0           # 竞标优先级
    cooldown: int = 0                 # 冷却回合数
    weight: float = 1.0               # 竞标权重
    tags: List[str] = field(default_factory=list)  # 额外标签

@dataclass
class ReactionBone:
    """
    防御方反应骨架 - 描述"频道是什么、物理类是什么、反应如何"。
    MDDC v5.1: 主要由 damage_material 驱动，可选匹配 motion_style。
    """
    bone_id: str                      # 唯一标识
    channel: Channel                  # 只匹配对应频道 (FATAL/EVADE/IMPACT)
    damage_material: str              # 物理材质（ENERGY/KINETIC/PHYSICAL）
    text_fragments: List[str]         # 用于 L3 拼装的多段文本碎片
    motion_style: str = "ANY"         # 可选：对动作风格的特定限制（如特化"光束斩击"反应）
    vfx_ids: List[str] = field(default_factory=list)  # 视觉特效ID
    sfx_ids: List[str] = field(default_factory=list)  # 音效ID
    tier: TemplateTier = TemplateTier.T2_TACTICAL
    weight: float = 1.0               # 竞标权重
    tags: List[str] = field(default_factory=list)  # 额外标签
    attack_result: Optional[str] = None  # 攻击结果 (BLOCK, PARRY 等)，None 表示通用
