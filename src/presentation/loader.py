import yaml
import os
from typing import List, Dict, Any
from .template import PresentationTemplate, TemplateConditions, TemplateContent, TemplateVisuals
from .constants import TemplateTier, VisualIntent

class TemplateLoader:
    """
    Loads presentation templates from YAML configuration files.
    """
    
    @staticmethod
    def load_from_file(file_path: str) -> List[PresentationTemplate]:
        """Loads templates from a YAML file."""
        if not os.path.exists(file_path):
            print(f"[WARN] Template config not found: {file_path}")
            return []
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                
            if not data or 'templates' not in data:
                return []
                
            templates = []
            for item in data['templates']:
                try:
                    tmpl = TemplateLoader._parse_template(item)
                    templates.append(tmpl)
                except Exception as e:
                    print(f"[ERROR] Failed to parse template {item.get('id', 'unknown')}: {e}")
                    
            return templates
            
        except Exception as e:
            print(f"[ERROR] Failed to load template file {file_path}: {e}")
            return []

    @staticmethod
    def _parse_template(data: Dict[str, Any]) -> PresentationTemplate:
        # Parse Tier
        tier_str = data.get('tier', 'T3_FALLBACK')
        try:
            tier = TemplateTier[tier_str]
        except KeyError:
            # Try matching by value if key fails, or default
            tier = next((t for t in TemplateTier if t.value == tier_str), TemplateTier.T3_FALLBACK)

        # Parse Conditions
        cond_data = data.get('conditions', {})
        intent_str = cond_data.get('intent')
        intent = None
        if intent_str:
            try:
                intent = VisualIntent[intent_str] if intent_str in VisualIntent.__members__ else VisualIntent(intent_str)
            except ValueError:
                pass

        conditions = TemplateConditions(
            intent=intent,
            result=cond_data.get('result'),
            weapon_type=cond_data.get('weapon_type'),
            required_tags=cond_data.get('tags', []),
            skill_id=cond_data.get('skill_id'),
            hp_status=cond_data.get('hp_status')
        )

        # Parse Content
        cont_data = data.get('content', {})
        content = TemplateContent(
            action_text=cont_data.get('action_text', ""),
            reaction_text=cont_data.get('reaction_text', "")
        )

        # Parse Visuals
        vis_data = data.get('visuals', {})
        visuals = TemplateVisuals(
            anim_id=vis_data.get('anim_id'),
            cam_id=vis_data.get('cam_id'),
            vfx_ids=vis_data.get('vfx_ids', []),
            sfx_ids=vis_data.get('sfx_ids', [])
        )

        return PresentationTemplate(
            id=data['id'],
            tier=tier,
            conditions=conditions,
            content=content,
            visuals=visuals,
            priority_score=data.get('priority_score', 0),
            cooldown=data.get('cooldown', 0)
        )
