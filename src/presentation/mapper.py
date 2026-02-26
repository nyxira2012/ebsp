from typing import List, Optional
from .models import RawAttackEvent, PresentationAttackEvent
from .constants import PresentationTag, TemplateTier
from .intent_extractor import IntentExtractor
from .registry import TemplateRegistry
from .selector import TemplateSelector
from .template import PresentationTemplate

from .scripted_manager import ScriptedPresentationManager

class EventMapper:
    """
    Event Mapper - Orchestrates the conversion from RawAttackEvent to PresentationAttackEvent(s).
    """
    def __init__(self, registry: Optional[TemplateRegistry] = None):
        if registry is None:
            self.registry = TemplateRegistry()
        else:
            self.registry = registry
        self.selector = TemplateSelector(self.registry)
        self.scripted_manager = ScriptedPresentationManager()

    def map_attack(self, raw_event: RawAttackEvent) -> List[PresentationAttackEvent]:
        """
        Main entry point: Converts a raw combat event into a sequence of presentation events.
        Returns a list containing [Action, Reaction] events.
        """
        # 1. Check T0 (Scripted) first
        forced_tmpl = self.scripted_manager.get_forced_template(
            raw_event.round_number, 
            raw_event.attacker_id, 
            raw_event.defender_id
        )
        
        if forced_tmpl:
            template = forced_tmpl
        else:
            # 2. Extract Intent
            intent = IntentExtractor.extract_intent(raw_event.weapon_type, raw_event.weapon_tags)

            # 3. Select Template via Selector (T1 -> T2 -> T3)
            template = self.selector.select_template(intent, raw_event)

        if not template:
            # Should not happen if T3 fallback exists
            # Create a dummy emergency fallback
            return self._create_emergency_fallback(raw_event)

        # 4. Construct Presentation Events (Action + Reaction)
        action_event = self._create_action_event(raw_event, template)
        reaction_event = self._create_reaction_event(raw_event, template)

        return [action_event, reaction_event]

    def advance_turn(self):
        """
        Advance the state of internal components (e.g. cooldowns) at the end of a turn/round.
        """
        self.selector.tick_cooldowns()

    def _create_action_event(self, raw: RawAttackEvent, tmpl: PresentationTemplate) -> PresentationAttackEvent:
        text = tmpl.content.action_text.format(
            attacker=raw.attacker_name,
            defender=raw.defender_name,
            weapon=raw.weapon_name
        )
        
        # Dynamic Camera Logic
        cam_id = tmpl.visuals.cam_id or "cam_default"
        if cam_id == "cam_default":
            # Heuristics for better camera
            if raw.distance > 800:
                cam_id = "cam_long_shot"
            elif raw.distance < 100:
                cam_id = "cam_close_up"
            
            if raw.attack_result == "CRIT":
                cam_id = "cam_dramatic_zoom"

        return PresentationAttackEvent(
            event_type="ACTION",
            round_number=raw.round_number,
            timestamp=0.0,
            text=text,
            tier=tmpl.tier,
            anim_id=tmpl.visuals.anim_id or "default_attack",
            camera_cam=cam_id,
            vfx_ids=tmpl.visuals.vfx_ids or [],
            sfx_ids=tmpl.visuals.sfx_ids or [],
            template_id=tmpl.id,
            raw_event=raw,
            attacker_name=raw.attacker_name,
            defender_name=raw.defender_name,
            weapon_name=raw.weapon_name,
            attack_result=raw.attack_result
        )

    def _create_reaction_event(self, raw: RawAttackEvent, tmpl: PresentationTemplate) -> PresentationAttackEvent:
        text = tmpl.content.reaction_text.format(
            attacker=raw.attacker_name,
            defender=raw.defender_name,
            weapon=raw.weapon_name
        )
        
        # Dynamic Camera Logic for Reaction
        cam_id = tmpl.visuals.cam_id or "cam_default"
        if cam_id == "cam_default":
            if raw.attack_result in ["HIT", "CRIT"]:
                if raw.damage > 500: # Threshold for "big hit"
                    cam_id = "cam_shake_heavy"
                else:
                    cam_id = "cam_shake_light"
            elif raw.attack_result == "DODGE":
                cam_id = "cam_tracking_evade"
        
        return PresentationAttackEvent(
            event_type="REACTION",
            round_number=raw.round_number,
            timestamp=1.5, # Delayed start
            text=text,
            tier=tmpl.tier,
            anim_id=tmpl.visuals.anim_id or "default_anim",
            camera_cam=cam_id,
            vfx_ids=tmpl.visuals.vfx_ids or [],
            sfx_ids=tmpl.visuals.sfx_ids or [],
            damage_display=raw.damage if raw.attack_result in ["HIT", "CRIT"] else 0,
            hit_location="body", # Placeholder
            template_id=tmpl.id,
            raw_event=raw,
            attacker_name=raw.attacker_name,
            defender_name=raw.defender_name,
            weapon_name=raw.weapon_name,
            attack_result=raw.attack_result
        )

    def _create_emergency_fallback(self, raw: RawAttackEvent) -> List[PresentationAttackEvent]:
        """Last resort fallback if no template matches"""
        return [
            PresentationAttackEvent(
                event_type="ACTION",
                round_number=raw.round_number,
                text=f"{raw.attacker_name} attacks!",
                raw_event=raw
            ),
            PresentationAttackEvent(
                event_type="REACTION",
                round_number=raw.round_number,
                text=f"{raw.defender_name} takes {raw.damage} damage.",
                raw_event=raw
            )
        ]
