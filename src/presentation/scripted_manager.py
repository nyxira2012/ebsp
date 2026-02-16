from typing import Dict, List, Optional
from .models import PresentationAttackEvent, RawAttackEvent
from .template import PresentationTemplate

class ScriptedPresentationManager:
    """
    T0 Scripted Manager - Manages forced presentation templates for specific scenarios.
    Allows external scripts to inject high-priority templates that bypass logic.
    """
    def __init__(self):
        # Maps (round_number, attacker_id, defender_id) -> PresentationTemplate
        self._forced_templates: Dict[tuple, PresentationTemplate] = {}

    def inject_template(self, round_number: int, attacker_id: str, defender_id: str, template: PresentationTemplate):
        """Force a specific template for a specific battle moment."""
        key = (round_number, attacker_id, defender_id)
        self._forced_templates[key] = template

    def get_forced_template(self, round_number: int, attacker_id: str, defender_id: str) -> Optional[PresentationTemplate]:
        """Check if there is a forced template for this moment."""
        return self._forced_templates.get((round_number, attacker_id, defender_id))

    def clear(self):
        self._forced_templates.clear()
