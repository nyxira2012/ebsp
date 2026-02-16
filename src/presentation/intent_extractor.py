from typing import List, Optional
from ..models import WeaponType
from .constants import VisualIntent

class IntentExtractor:
    """
    Logic for extracting the VisualIntent from weapon data and tags.
    """

    @staticmethod
    def extract_intent(weapon_type: str, tags: List[str]) -> VisualIntent:
        """
        Determines the VisualIntent based on WeaponType and Tags.

        Rules:
        1. Check tags for specific overrides.
        2. Fallback to default intent for the WeaponType.
        3. Global fallback.
        """
        # Normalize tags
        tags = [t.lower() for t in tags] if tags else []

        # 1. SPECIAL/AWAKENING specific checks
        if "psycho" in tags or "funnel" in tags:
            return VisualIntent.PSYCHO_WAVE
        if "map" in tags or "aoe" in tags:
            return VisualIntent.AOE_BURST

        # 2. WeaponType specific logic
        # Handle both enum values (e.g., "RIFLE") and common strings (e.g., "SHOOTING")
        weapon_type_upper = weapon_type.upper() if weapon_type else ""

        if weapon_type_upper in ["MELEE", WeaponType.MELEE.value]:
            if any(t in tags for t in ["heavy", "axe", "greatsword"]):
                return VisualIntent.SLASH_HEAVY
            if any(t in tags for t in ["blunt", "hammer", "punch", "kick"]):
                return VisualIntent.STRIKE_BLUNT
            return VisualIntent.SLASH_LIGHT

        elif weapon_type_upper in ["SHOOTING", "RIFLE", WeaponType.SHOOTING.value]:
            if "beam" in tags:
                if "massive" in tags or "mega" in tags:
                    return VisualIntent.BEAM_MASSIVE
                return VisualIntent.BEAM_INSTANT

            # Projectiles
            if any(t in tags for t in ["missile", "gatling", "vulcan", "rapid"]):
                return VisualIntent.PROJECTILE_RAIN
            return VisualIntent.PROJECTILE_SINGLE

        elif weapon_type_upper in ["HEAVY", WeaponType.HEAVY.value]:
            if "beam" in tags:
                return VisualIntent.BEAM_MASSIVE
            return VisualIntent.IMPACT_MASSIVE

        elif weapon_type_upper in ["AWAKENING", WeaponType.AWAKENING.value]:
            return VisualIntent.PSYCHO_WAVE

        elif weapon_type_upper in ["SPECIAL", WeaponType.SPECIAL.value]:
            return VisualIntent.AOE_BURST

        elif weapon_type_upper in ["FALLBACK", WeaponType.FALLBACK.value]:
            return VisualIntent.IMPACT_MASSIVE

        # Default Fallback
        return VisualIntent.STRIKE_BLUNT
