from enum import Enum

class VisualIntent(str, Enum):
    """
    Standard Visual Intent - Describes the physical nature of the attack
    Used to select the appropriate reaction animation and text.
    """
    # Melee
    SLASH_LIGHT = "INTENT_SLASH_LIGHT"      # Fast slash (Beam Saber, Knife)
    SLASH_HEAVY = "INTENT_SLASH_HEAVY"      # Heavy slash (Giant Sword, Axe)
    STRIKE_BLUNT = "INTENT_STRIKE_BLUNT"    # Blunt strike (Punch, Kick, Hammer)
    
    # Shooting
    BEAM_INSTANT = "INTENT_BEAM_INSTANT"    # Instant beam (Beam Rifle)
    BEAM_MASSIVE = "INTENT_BEAM_MASSIVE"    # Massive beam (Mega Particle Cannon)
    PROJECTILE_SINGLE = "INTENT_PROJECTILE_SINGLE"  # Single projectile (Bazooka, Sniper)
    PROJECTILE_RAIN = "INTENT_PROJECTILE_RAIN"      # Projectile rain (Missiles, Vulcan)
    
    # Special
    IMPACT_MASSIVE = "INTENT_IMPACT_MASSIVE"  # Massive impact (Collision)
    PSYCHO_WAVE = "INTENT_PSYCHO_WAVE"        # Psycho wave (Funnel, Mind attack)
    AOE_BURST = "INTENT_AOE_BURST"            # Area burst (Map weapon)

class PresentationTag(str, Enum):
    """
    General Presentation Tags - Used for conditional logic in templates
    """
    # Locations
    LOC_HEAD = "TAG_LOC_HEAD"
    LOC_ARM = "TAG_LOC_ARM"
    LOC_LEG = "TAG_LOC_LEG"
    LOC_BACKPACK = "TAG_LOC_BACKPACK"
    
    # Skills (Generalized)
    SKILL_NEWTYPE = "TAG_SKILL_NEWTYPE"
    SKILL_POTENTIAL = "TAG_SKILL_POTENTIAL"
    SKILL_VALOR = "TAG_SKILL_VALOR"    # Hot Blood / Valor
    SKILL_SUREHIT = "TAG_SKILL_SUREHIT" # Strike / Sure Hit
    SKILL_FLASH = "TAG_SKILL_FLASH"    # Alert / Flash
    
    # Range
    RANGE_POINT_BLANK = "TAG_RANGE_ZERO"
    RANGE_LONG = "TAG_RANGE_LONG"

class TemplateTier(str, Enum):
    """
    Template Priority Tiers (The T-Hierarchy)
    """
    T0_SCRIPTED = "T0_SCRIPTED"     # Scripted/Story events (Highest)
    T0_LETHAL = "T0_LETHAL"         # Lethal damage (special priority)
    T1_HIGHLIGHT = "T1_HIGHLIGHT"   # Skill/Character highlights
    T2_TACTICAL = "T2_TACTICAL"     # Weapon/Physics interactions
    T3_FALLBACK = "T3_FALLBACK"     # Generic fallback (Lowest)
