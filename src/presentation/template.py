from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .constants import TemplateTier, VisualIntent

@dataclass
class TemplateConditions:
    """
    Conditions required for a template to be selected.
    """
    intent: Optional[VisualIntent] = None
    result: Optional[str] = None  # MISS, DODGE, HIT, CRIT, BLOCK, PARRY
    weapon_type: Optional[str] = None
    required_tags: List[str] = field(default_factory=list)
    skill_id: Optional[str] = None  # For T1 Highlight templates
    hp_status: Optional[str] = None  # LETHAL, CRITICAL, MODERATE, LIGHT

    def matches(self, intent: VisualIntent, result: str, weapon_type: str, tags: List[str], skills: List[str], hp_status: Optional[str] = None) -> bool:
        if self.intent and self.intent != intent:
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
    A single presentation template definition.
    """
    id: str
    tier: TemplateTier
    conditions: TemplateConditions
    content: TemplateContent
    visuals: TemplateVisuals
    priority_score: int = 0  # For T1 bidding (100=High, 50=Med)
    cooldown: int = 0        # Rounds to wait before showing again (to avoid repetition)
