from enum import Enum

class Channel(str, Enum):
    """
    演出频道 - 基于结局前置路由 (Outcome-First Routing)
    这是 L1 绝对律令层的核心输出，决定后续所有层的检索范围。
    """
    FATAL = "FATAL"       # 致死
    EVADE = "EVADE"       # 闪避/招架/未命中
    IMPACT = "IMPACT"     # 命中/格挡/暴击
    SPECIAL = "SPECIAL"   # 支援/反击

class VisualIntent(str, Enum):
    """
    Standard Visual Intent - Describes the physical nature of the attack
    Used to select the appropriate reaction animation and text.
    """
    # Melee
    SLASH_LIGHT = "SLASH_LIGHT"      # Fast slash (Beam Saber, Knife)
    SLASH_HEAVY = "SLASH_HEAVY"      # Heavy slash (Giant Sword, Axe)
    STRIKE_BLUNT = "STRIKE_BLUNT"    # Blunt strike (Punch, Kick, Hammer)

    # Shooting
    BEAM_INSTANT = "BEAM_INSTANT"    # Instant beam (Beam Rifle)
    BEAM_MASSIVE = "BEAM_MASSIVE"    # Massive beam (Mega Particle Cannon)
    PROJECTILE_SINGLE = "PROJECTILE_SINGLE"  # Single projectile (Bazooka, Sniper)
    PROJECTILE_RAIN = "PROJECTILE_RAIN"      # Projectile rain (Missiles, Vulcan)

    # Special
    IMPACT_MASSIVE = "IMPACT_MASSIVE"  # Massive impact (Collision)
    PSYCHO_WAVE = "PSYCHO_WAVE"        # Psycho wave (Funnel, Mind attack)
    AOE_BURST = "AOE_BURST"            # Area burst (Map weapon)

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
