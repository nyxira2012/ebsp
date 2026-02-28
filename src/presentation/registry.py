from typing import List, Dict, Optional
import os
from .template import PresentationTemplate, TemplateConditions, TemplateContent, TemplateVisuals
from .constants import TemplateTier, VisualIntent
from .loader import TemplateLoader

class TemplateRegistry:
    """
    Registry for managing and retrieving Presentation Templates.
    Loads from YAML/JSON files.
    """
    def __init__(self, config_path: Optional[str] = None):
        self._templates: Dict[str, PresentationTemplate] = {}
        
        # Load defaults first (fallback)
        self._initialize_defaults()
        
        # Load from config if provided
        if config_path:
            self.load_from_config(config_path)

    def load_from_config(self, config_path: str):
        """Loads and registers templates from a configuration file."""
        loaded_templates = TemplateLoader.load_from_file(config_path)
        for tmpl in loaded_templates:
            self.register(tmpl)

    def register(self, template: PresentationTemplate):
        self._templates[template.id] = template

    def get_templates_by_tier(self, tier: TemplateTier) -> List[PresentationTemplate]:
        return [t for t in self._templates.values() if t.tier == tier]

    def _initialize_defaults(self):
        """
        Initialize minimal hardcoded default templates (T3 Fallback)
        to ensure system works even if config fails.
        """
        # T3: Generic Fallback
        self.register(PresentationTemplate(
            id="t3_fallback_generic_default",
            tier=TemplateTier.T3_FALLBACK,
            conditions=TemplateConditions(), # Matches everything
            content=TemplateContent(
                action_text="{attacker} attacks {defender} with {weapon}!",
                reaction_text="{defender} receives the attack."
            ),
            visuals=TemplateVisuals()
        ))
