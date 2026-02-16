from typing import List, Optional
import json
from .models import PresentationAttackEvent, PresentationRoundEvent, TemplateTier

class TextRenderer:
    """
    Renders presentation events as human-readable text for the console.
    """
    
    # ANSI Color Codes
    COLORS = {
        "ACTION": "\033[93m",      # Yellow
        "REACTION": "\033[94m",    # Blue
        "T1": "\033[95m",          # Magenta (High-light)
        "DAMAGE": "\033[91m",      # Red
        "RESET": "\033[0m"
    }

    @staticmethod
    def render_attack(events: List[PresentationAttackEvent], use_color: bool = True) -> str:
        """Renders a list of events (typically Action + Reaction)"""
        output = []
        for e in events:
            color = TextRenderer.COLORS["ACTION"] if e.event_type == "ACTION" else TextRenderer.COLORS["REACTION"]
            tier_prefix = f"[{e.tier.value}] " if e.tier != TemplateTier.T3_FALLBACK else ""
            
            reset = TextRenderer.COLORS["RESET"]
            
            line = f"{color if use_color else ''}{e.event_type}{reset if use_color else ''}: {tier_prefix}{e.text}"
            
            # Special damage display for reactions
            if e.event_type == "REACTION" and e.damage_display > 0:
                dmg_color = TextRenderer.COLORS["DAMAGE"]
                line += f" ({dmg_color if use_color else ''}Damage: {e.damage_display}{reset if use_color else ''})"
            
            output.append(line)
        return "\n".join(output)

    @staticmethod
    def render_round(round_event: PresentationRoundEvent, use_color: bool = True) -> str:
        """Renders a full round event."""
        output = []
        output.append(f"=== ROUND {round_event.round_number} PRESENTATION ===")

        if round_event.context_events:
            output.append("--- Context ---")
            for ctx in round_event.context_events:
                output.append(f"{ctx.text}")

        for idx, seq in enumerate(round_event.attack_sequences, 1):
            output.append(f"--- Attack Sequence {idx} ---")
            output.append(TextRenderer.render_attack(seq.events, use_color))

        if round_event.summary_events:
            output.append("--- Summary ---")
            for summary in round_event.summary_events:
                output.append(f"{summary.text}")

        return "\n".join(output)

class JSONRenderer:
    """
    Renders presentation events as JSON for frontend integration.
    """
    @staticmethod
    def render_attack(events: List[PresentationAttackEvent]) -> str:
        data = []
        for e in events:
            data.append({
                "type": e.event_type,
                "text": e.text,
                "anim_id": e.anim_id,
                "vfx": e.vfx_ids,
                "sfx": e.sfx_ids,
                "damage": e.damage_display,
                "tier": e.tier.value
            })
        return json.dumps(data, indent=2, ensure_ascii=False)

    @staticmethod
    def render_timeline(timeline: List[PresentationRoundEvent]) -> dict:
        """Render a complete battle timeline to JSON-serializable dict."""
        rounds = []
        for round_event in timeline:
            round_data = {
                "round_number": round_event.round_number,
                "context_events": [
                    {
                        "type": e.event_type,
                        "text": e.text,
                        "anim_id": e.anim_id,
                        "vfx": e.vfx_ids,
                        "sfx": e.sfx_ids,
                        "tier": e.tier.value
                    } for e in round_event.context_events
                ],
                "attack_sequences": [
                    {
                        "attacker_id": seq.attacker_id,
                        "defender_id": seq.defender_id,
                        "events": [
                            {
                                "type": e.event_type,
                                "text": e.text,
                                "anim_id": e.anim_id,
                                "vfx": e.vfx_ids,
                                "sfx": e.sfx_ids,
                                "damage": e.damage_display,
                                "tier": e.tier.value
                            } for e in seq.events
                        ]
                    } for seq in round_event.attack_sequences
                ],
                "summary_events": [
                    {
                        "type": e.event_type,
                        "text": e.text,
                        "anim_id": e.anim_id,
                        "vfx": e.vfx_ids,
                        "sfx": e.sfx_ids,
                        "tier": e.tier.value
                    } for e in round_event.summary_events
                ]
            }
            rounds.append(round_data)
        return {"rounds": rounds}
