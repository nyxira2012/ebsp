from typing import List, Optional
import random
from .models import RawAttackEvent, PresentationAttackEvent
from .template import PresentationTemplate
from .registry import TemplateRegistry
from .constants import TemplateTier, VisualIntent

class TemplateSelector:
    """
    Selects the best PresentationTemplate based on the RawAttackEvent and VisualIntent.
    Implements the T-Hierarchy and Bidding system.
    """
    def __init__(self, registry: TemplateRegistry):
        self.registry = registry
        # Bug Fix #1: Use (template_id, entity_id) as keys to scope cooldowns per entity
        self._cooldowns: dict[tuple[str, str], int] = {} 
        self._demotion_weights: dict[tuple[str, str], int] = {} 

    def select_template(self,
                        intent: VisualIntent,
                        raw_event: RawAttackEvent,
                        hp_status: Optional[str] = None) -> Optional[PresentationTemplate]:
        """
        Main selection logic.
        """
        # 1. Gather candidates from T1/T2/T3 only
        candidates = self._gather_candidates(intent, raw_event, hp_status)

        # 2. Hierarchy Check (T1 -> T2 -> T3)
        winner = None
        if candidates[TemplateTier.T1_HIGHLIGHT]:
            winner = self._pick_t1(candidates[TemplateTier.T1_HIGHLIGHT], raw_event)
        elif candidates[TemplateTier.T2_TACTICAL]:
            winner = self._pick_t2(candidates[TemplateTier.T2_TACTICAL])
        elif candidates[TemplateTier.T3_FALLBACK]:
            winner = self._pick_t3(candidates[TemplateTier.T3_FALLBACK])

        if winner:
            self._record_usage(winner, raw_event)

        return winner

    def _get_target_id(self, tmpl: PresentationTemplate, event: RawAttackEvent) -> str:
        """
        Determines the entity responsible for this presentation template.
        - Dodge/Parry/Block templates are scoped to the Defender.
        - All other templates (usually attacks) are scoped to the Attacker.
        """
        if tmpl.conditions.result in ("DODGE", "PARRY", "BLOCK"):
            return event.defender_id
        return event.attacker_id

    def _gather_candidates(self, intent: VisualIntent, event: RawAttackEvent, hp_status: Optional[str] = None) -> dict[TemplateTier, List[PresentationTemplate]]:
        HANDLED_TIERS = (TemplateTier.T1_HIGHLIGHT, TemplateTier.T2_TACTICAL, TemplateTier.T3_FALLBACK)
        candidates = {tier: [] for tier in TemplateTier}

        for tier in HANDLED_TIERS:
            tier_templates = self.registry.get_templates_by_tier(tier)
            for tmpl in tier_templates:
                # Scoped Cooldown Check
                target_id = self._get_target_id(tmpl, event)
                if self._cooldowns.get((tmpl.id, target_id), 0) > 0:
                    continue

                if tmpl.conditions.matches(
                    intent=intent,
                    result=event.attack_result,
                    weapon_type=event.weapon_type,
                    tags=event.weapon_tags,
                    skills=event.triggered_skills,
                    hp_status=hp_status
                ):
                    candidates[tier].append(tmpl)
        return candidates

    def _pick_t1(self, candidates: List[PresentationTemplate], event: RawAttackEvent) -> PresentationTemplate:
        # Sort by effective_score = base_score - demotion_penalty
        
        def calculate_effective_score(tmpl: PresentationTemplate) -> int:
            target_id = self._get_target_id(tmpl, event)
            penalty = self._demotion_weights.get((tmpl.id, target_id), 0)
            return tmpl.priority_score - penalty

        candidates.sort(key=calculate_effective_score, reverse=True)
        
        best = candidates[0]
        best_score = calculate_effective_score(best)
        
        ties = [c for c in candidates if calculate_effective_score(c) == best_score]
        return random.choice(ties)

    def _pick_t2(self, candidates: List[PresentationTemplate]) -> PresentationTemplate:
        return random.choice(candidates)

    def _pick_t3(self, candidates: List[PresentationTemplate]) -> PresentationTemplate:
        return random.choice(candidates)

    def _record_usage(self, template: PresentationTemplate, event: RawAttackEvent):
        """Record usage of a template to apply cooldowns and demotions."""
        target_id = self._get_target_id(template, event)
        key = (template.id, target_id)

        # 1. Apply Cooldown if specified
        if template.cooldown > 0:
            self._cooldowns[key] = template.cooldown
        else:
            # Default minimal cooldown to avoid back-to-back repetition for same entity
            self._cooldowns[key] = 1

        # 2. Apply Demotion Weights (primarily for T1 bidding, but safe for all)
        current_penalty = self._demotion_weights.get(key, 0)
        self._demotion_weights[key] = min(90, current_penalty + 30)

    def tick_cooldowns(self):
        """Decrease cooldowns and recover weights for all entries"""
        # 1. Cooldowns
        for key in list(self._cooldowns.keys()):
            self._cooldowns[key] -= 1
            if self._cooldowns[key] <= 0:
                del self._cooldowns[key]
                
        # 2. Demotion Recovery
        for key in list(self._demotion_weights.keys()):
            self._demotion_weights[key] = max(0, self._demotion_weights[key] - 15)
            if self._demotion_weights[key] <= 0:
                del self._demotion_weights[key]

