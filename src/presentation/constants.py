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

class MotionStyle(str, Enum):
    """
    攻击动作风格 (Action Style) - 描述驾驶员"怎么打"。
    用于驱动 ActionBone 竞标。
    """
    # Melee
    SLASH_LIGHT = "SLASH_LIGHT"      # 快速斩击 (光束军刀, 军刀)
    SLASH_HEAVY = "SLASH_HEAVY"      # 重型斩击 (大剑, 斧)
    STRIKE_BLUNT = "STRIKE_BLUNT"    # 钝器打击 (拳, 脚, 锤)

    # Shooting
    SHOOT_INSTANT = "SHOOT_INSTANT"    # 瞬间射击 (步枪)
    SHOOT_MASSIVE = "SHOOT_MASSIVE"    # 巨炮轰击 (地图炮/高能炮)
    PROJ_SINGLE = "PROJ_SINGLE"        # 单发点射 (火箭筒)
    PROJ_RAIN = "PROJ_RAIN"            # 弹幕覆盖 (导弹, 火神炮)

    # Special
    IMPACT_RAM = "IMPACT_RAM"          # 全速撞击
    PSYCHO_WAVE = "PSYCHO_WAVE"        # 精神波动
    AOE_BURST = "AOE_BURST"            # 区域爆发

class DamageMaterial(str, Enum):
    """
    伤害物理材质 (Impact Material) - 描述物理交互的"本质"。
    用于驱动 ReactionBone 竞标。
    """
    ENERGY = "ENERGY"      # 能量类 (光束, 粒子)
    KINETIC = "KINETIC"    # 动能类 (实弹, 破片)
    PHYSICAL = "PHYSICAL"  # 物理类 (金属刃, 撞击)
    GENERIC = "GENERIC"    # 通用/其他


class TemplateTier(str, Enum):
    """
    Template Priority Tiers (The T-Hierarchy)
    """
    T0_SCRIPTED = "T0_SCRIPTED"     # Scripted/Story events (Highest)
    T0_LETHAL = "T0_LETHAL"         # Lethal damage (special priority)
    T1_HIGHLIGHT = "T1_HIGHLIGHT"   # Skill/Character highlights
    T2_TACTICAL = "T2_TACTICAL"     # Weapon/Physics interactions (from YAML)
    T3_FALLBACK = "T3_FALLBACK"     # Hard-coded fallback (no template match)
