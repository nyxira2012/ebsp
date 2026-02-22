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
        self._cooldowns: dict[str, int] = {} # template_id -> rounds remaining
        self._demotion_weights: dict[str, int] = {} # template_id -> transient score penalty

    def select_template(self,
                        intent: VisualIntent,
                        raw_event: RawAttackEvent) -> Optional[PresentationTemplate]:
        """
        Main selection logic.
        Note: T0 (Scripted) is handled exclusively by ScriptedPresentationManager
        in EventMapper before this selector is called. This method only handles T1->T2->T3.
        """
        # 1. Gather candidates from T1/T2/T3 only (T0 is handled upstream)
        candidates = self._gather_candidates(intent, raw_event)

        # 2. Hierarchy Check (T1 -> T2 -> T3)
        # T0 is intentionally skipped here; it is handled by ScriptedPresentationManager.

        # T1: Highlight (Weighted Bidding)
        if candidates[TemplateTier.T1_HIGHLIGHT]:
            return self._pick_t1(candidates[TemplateTier.T1_HIGHLIGHT])

        # T2: Tactical (First Match/Random)
        if candidates[TemplateTier.T2_TACTICAL]:
            return self._pick_t2(candidates[TemplateTier.T2_TACTICAL])

        # T3: Fallback
        if candidates[TemplateTier.T3_FALLBACK]:
            return self._pick_t3(candidates[TemplateTier.T3_FALLBACK])

        return None

    def _gather_candidates(self, intent: VisualIntent, event: RawAttackEvent) -> dict[TemplateTier, List[PresentationTemplate]]:
        # Bug Fix #4: Skip T0_SCRIPTED tier here.
        # T0 is exclusively managed by ScriptedPresentationManager in EventMapper.
        # Allowing T0 templates through the registry would create two competing T0 systems
        # with undefined priority between them.
        HANDLED_TIERS = (TemplateTier.T1_HIGHLIGHT, TemplateTier.T2_TACTICAL, TemplateTier.T3_FALLBACK)

        candidates = {tier: [] for tier in TemplateTier}

        for tier in HANDLED_TIERS:
            tier_templates = self.registry.get_templates_by_tier(tier)
            for tmpl in tier_templates:
                # Check cooldown
                if self._cooldowns.get(tmpl.id, 0) > 0:
                    continue

                if tmpl.conditions.matches(
                    intent=intent,
                    result=event.attack_result,
                    weapon_type=event.weapon_type,
                    tags=event.weapon_tags,
                    skills=event.triggered_skills
                ):
                    candidates[tier].append(tmpl)
        return candidates

    def _pick_t0(self, candidates: List[PresentationTemplate]) -> PresentationTemplate:
        # T0 is usually unique, return the first one
        return candidates[0]

    def _pick_t1(self, candidates: List[PresentationTemplate]) -> PresentationTemplate:
        # Sort by (effective_score) descending
        # effective_score = base_score - demotion_penalty
        
        def calculate_effective_score(tmpl: PresentationTemplate) -> int:
            penalty = self._demotion_weights.get(tmpl.id, 0)
            return tmpl.priority_score - penalty

        # Sort based on calculated effective score
        candidates.sort(key=calculate_effective_score, reverse=True)
        
        best = candidates[0]
        best_score = calculate_effective_score(best)
        
        # Check for ties
        ties = [c for c in candidates if calculate_effective_score(c) == best_score]
        winner = random.choice(ties)
        
        # Apply demotion logic
        # -30 score penalty for next round, accumulating
        self._demotion_weights[winner.id] = self._demotion_weights.get(winner.id, 0) + 30
        
        # Also apply 2 round hard cooldown as per original design default
        # or we rely purely on weighting? The doc mentions "下回合其权重临时 -30"
        # Let's keep cooldown separate if defined in template
        if winner.cooldown > 0:
            self._cooldowns[winner.id] = winner.cooldown
        
        return winner

    def _pick_t2(self, candidates: List[PresentationTemplate]) -> PresentationTemplate:
        # Random for variety
        return random.choice(candidates)

    def _pick_t3(self, candidates: List[PresentationTemplate]) -> PresentationTemplate:
        # Random for variety
        return random.choice(candidates)

    def tick_cooldowns(self):
        """Call this at end of round to decrease cooldowns and recover weights"""
        # 1. Cooldowns
        for tid in list(self._cooldowns.keys()):
            self._cooldowns[tid] -= 1
            if self._cooldowns[tid] <= 0:
                del self._cooldowns[tid]
                
        # 2. Demotion Recovery
        # Decay penalty by 15 per round
        for tid in list(self._demotion_weights.keys()):
            self._demotion_weights[tid] = max(0, self._demotion_weights[tid] - 15)
            if self._demotion_weights[tid] <= 0:
                del self._demotion_weights[tid]
