"""
数据模型定义
包含所有枚举类型、配置模型 (Pydantic) 和快照模型 (Snapshot)
"""

from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, ConfigDict, Field
from dataclasses import dataclass, field
from .config import Config

# ============================================================================
# 枚举类型 (Enums)
# ============================================================================

class WeaponType(str, Enum):
    """武器类型"""
    MELEE = "格斗"      # < 2000m
    SHOOTING = "射击"   # 1000m - 6000m
    AWAKENING = "觉醒"  # 浮游炮等
    SPECIAL = "特殊"    # 地图炮或其他
    FALLBACK = "撞击"   # 保底武器

class SlotType(str, Enum):
    """槽位类型"""
    FIXED = "FIXED"     # 固定槽位
    WEAPON = "WEAPON"   # 武器槽
    EQUIP = "EQUIP"     # 设备槽
    SUB_PILOT = "SUB"   # 副驾驶槽 (虚拟)

class AttackResult(str, Enum):
    """攻击判定结果"""
    MISS = "未命中"
    DODGE = "躲闪"
    PARRY = "招架"
    BLOCK = "格挡"
    CRIT = "暴击"
    HIT = "命中"

class InitiativeReason(str, Enum):
    """先手原因"""
    PERFORMANCE = "机体性能优势"
    PILOT = "驾驶员感知优势"
    ADVANTAGE = "气力优势延续"
    COUNTER = "战术反超"
    FORCED_SWITCH = "强制换手机制"

class Terrain(str, Enum):
    """地形类型"""
    SPACE = "宇宙"
    SKY = "空中"
    GROUND = "地面"
    WATER = "水下"
    FOREST = "森林" 
    BASE = "基地"   

# ============================================================================
# 源数据模型 (Source Data Definitions) - Pydantic
# ============================================================================

class MechaConfig(BaseModel):
    """机体静态配置表"""
    id: str
    name: str
    portrait_id: str
    model_asset: str = "default_model"
    
    # 基础属性 (Level 0)
    init_hp: int
    init_en: int
    init_armor: int
    init_mobility: int
    
    # 判定属性 (硬件修正)
    init_hit: float         # 命中率修正
    init_precision: float   # 精准值
    init_crit: float        # 暴击率
    
    # 防御倾向
    init_dodge: float       # 机体回避
    init_parry: float       # 机体招架
    init_block: float       # 机体格挡
    init_block_red: int     # 机体格挡减伤
    
    # 槽位与武器
    slots: List[str] = []         # ["WEAPON", "EQUIP", "WEAPON"...]
    fixed_weapons: List[str] = [] # 内置武器 ID 列表

class EquipmentConfig(BaseModel):
    """装备/部件配置表"""
    id: str
    name: str
    type: str               # WEAPON / EQUIP
    
    # 属性修正 (加法叠加)
    # key 必须匹配 MechaSnapshot 中的属性名 (e.g. "final_max_hp", "final_mobility")
    # 或者原始属性名 (e.g. "init_hp")，具体由 Factory 处理
    stat_modifiers: Dict[str, float] = {}
    
    # 武器特有属性 (仅当 type="WEAPON" 时有效)
    weapon_power: Optional[int] = None
    weapon_range_min: Optional[int] = None
    weapon_range_max: Optional[int] = None
    weapon_en_cost: Optional[int] = None
    weapon_type: Optional[WeaponType] = None 
    weapon_will_req: int = 0  # 气力需求
    weapon_tags: List[str] = []
    weapon_anim_id: str = "default_anim" 
    
    # 携带技能
    passive_skills: List[str] = []

class PilotConfig(BaseModel):
    """驾驶员配置表"""
    id: str
    name: str
    portrait_id: str

    # 核心五维
    stat_shooting: int      # 射击 (修正射击威力)
    stat_melee: int         # 格斗 (修正格斗威力)
    stat_awakening: int     # 觉醒 (修正觉醒威力 & 直觉)
    stat_defense: int       # 守备 (修正防御)
    stat_reaction: int      # 反应 (修正回避/先手)

    stat_tech: int = 0      # 技量 (预留，不参与计算)

    # 熟练度
    weapon_proficiency: int = 500     # 武器熟练度 (影响命中惩罚)
    mecha_proficiency: int = 2000     # 机体熟练度 (影响防御率)

    innate_skills: List[str] = []

# ============================================================================
# 快照模型 (Runtime Snapshots) - Pydantic
# ============================================================================

class WeaponSnapshot(BaseModel):
    """武器运行时快照"""
    uid: str                    # 运行时唯一ID
    definition_id: str          # 原始配置ID
    name: str
    type: WeaponType
    
    final_power: int            # 加成后的实战威力
    range_min: int
    range_max: int
    en_cost: int                # 统一使用 EN 消耗
    will_req: int               # 气力需求
    anim_id: str                # 战斗动画 ID
    
    # 额外补正 (通常来自武器自身特性)
    hit_mod: float = 0.0
    crit_mod: float = 0.0
    
    tags: List[str] = []

    def can_use_at_distance(self, distance: int) -> bool:
        return self.range_min <= distance <= self.range_max
        
    @property
    def weapon_type(self) -> WeaponType: return self.type
    
    @property
    def power(self) -> int: return self.final_power

    @property
    def id(self) -> str: return self.definition_id

    def get_hit_modifier_at_distance(self, distance: int) -> float:
        """获取指定距离下的命中补正，超出射程返回 -999"""
        if self.can_use_at_distance(distance):
            return 0.0
        return -999.0

class MechaSnapshot(BaseModel):
    """机体运行时快照"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    instance_id: str = "default_id"
    mecha_name: str = "DefaultMecha"
    
    # 资源管理
    main_portrait: str = "default_portrait"
    sub_portrait: Optional[str] = None
    model_asset: str = "default_asset"
    
    # 核心状态
    final_max_hp: int = 1000
    current_hp: int = 1000
    final_max_en: int = 100
    current_en: int = 100
    current_will: int = 100
    
    # 战斗属性
    final_armor: int = 1000
    final_mobility: int = 100
    
    # 判定倾向 (0-100)
    final_hit: float = 0.0
    final_precision: float = 0.0
    final_crit: float = 0.0
    
    final_dodge: float = 0.0
    final_parry: float = 0.0
    final_block: float = 0.0
    block_reduction: int = 0
    
    # 容器
    weapons: List[WeaponSnapshot] = []
    skills: List[str] = []

    # 驾驶员属性备份 (用于伤害计算和防御公式)
    # keys: shooting, melee, awakening, defense, reaction, weapon_proficiency, mecha_proficiency
    pilot_stats_backup: Dict[str, int] = {}

    # 战斗中的动态状态 (不序列化到纯JSON配置，但运行时需要)
    effects: List[Any] = Field(default_factory=list, exclude=True) # 运行时 Effect 对象列表
    
    # ========================================================================
    # 兼容性层 (Compatibility Layer for Legacy Tests/Code)
    # ========================================================================
    
    @property
    def id(self) -> str: return self.instance_id
    
    @property
    def name(self) -> str: return self.mecha_name

    def is_alive(self) -> bool:
        """检查机体是否存活"""
        return self.current_hp > 0

    @property
    def max_hp(self) -> int: return self.final_max_hp
    @max_hp.setter
    def max_hp(self, value: int): self.final_max_hp = value
    
    @property
    def max_en(self) -> int: return self.final_max_en
    @max_en.setter
    def max_en(self, value: int): self.final_max_en = value
    
    @property
    def hit_rate(self) -> float: return self.final_hit
    @hit_rate.setter
    def hit_rate(self, value: float): self.final_hit = value
    
    @property
    def precision(self) -> float: return self.final_precision
    @precision.setter
    def precision(self, value: float): self.final_precision = value

    @property
    def crit_rate(self) -> float: return self.final_crit
    @crit_rate.setter
    def crit_rate(self, value: float): self.final_crit = value

    @property
    def dodge_rate(self) -> float: return self.final_dodge
    @dodge_rate.setter
    def dodge_rate(self, value: float): self.final_dodge = value

    @property
    def parry_rate(self) -> float: return self.final_parry
    @parry_rate.setter
    def parry_rate(self, value: float): self.final_parry = value

    @property
    def block_rate(self) -> float: return self.final_block
    @block_rate.setter
    def block_rate(self, value: float): self.final_block = value
    
    @property
    def block_value(self) -> int: return self.block_reduction
    @block_value.setter
    def block_value(self, value: int): self.block_reduction = value

    @property
    def traits(self) -> List[str]: return self.skills
    @traits.setter
    def traits(self, value: List[str]): self.skills = value
    
    @property
    def defense_level(self) -> int: return self.final_armor
    @defense_level.setter
    def defense_level(self, value: int): self.final_armor = value
    
    @property
    def mobility(self) -> int: return self.final_mobility
    
    @property
    def pilot(self):
        """Mock pilot object for legacy access like mecha.pilot.stat_shooting"""
        stats_backup = self.pilot_stats_backup
        class MockPilot:
            def __init__(self, stats):
                self.stat_shooting = stats.get('stat_shooting', 0)
                self.stat_melee = stats.get('stat_melee', 0)
                self.stat_awakening = stats.get('stat_awakening', 0)
                self.stat_defense = stats.get('stat_defense', 0)
                self.stat_reaction = stats.get('stat_reaction', 0)
                self.weapon_proficiency = stats.get('weapon_proficiency', 500)
                self.mecha_proficiency = stats.get('mecha_proficiency', 2000)
                self._stats = stats
            
            def get_effective_stat(self, stat_name: str) -> int:
                return self._stats.get(stat_name, 0)
        return MockPilot(stats_backup)

    def is_alive(self) -> bool:
        return self.current_hp > 0
    
    def get_hp_percentage(self) -> float:
        return (self.current_hp / self.final_max_hp) * 100 if self.final_max_hp > 0 else 0
    
    def can_attack(self, weapon: WeaponSnapshot) -> bool:
        return self.current_en >= weapon.en_cost
    
    def consume_en(self, amount: int) -> None:
        self.current_en = max(0, self.current_en - amount)
    
    def take_damage(self, damage: int) -> None:
        self.current_hp = max(0, self.current_hp - damage)
    
    def modify_will(self, delta: int) -> None:
        from .config import Config
        self.current_will = max(Config.WILL_MIN, min(Config.WILL_MAX, self.current_will + delta))
        
    def get_pilot_stat(self, stat_name: str) -> int:
        return self.pilot_stats_backup.get(stat_name, 0)
    
    def get_effective_armor(self, will: int) -> int:
        """核心公式: (装甲 + 守备*1.5) * 气力%"""
        defense_val = self.pilot_stats_backup.get("stat_defense", 0)
        base_mitigation = self.final_armor + (defense_val * 1.5)
        return int(base_mitigation * (will / 100.0))

# ============================================================================
# 类名别名 (Backward Compatibility Aliases)
# ============================================================================
Mecha = MechaSnapshot
Pilot = PilotConfig
Weapon = WeaponSnapshot


# ============================================================================
# 技能系统模型 (Skill System Support)
# ============================================================================

# 注意：为了兼容现有设计文档，暂时保留 dataclass 定义用于内部计算逻辑，
# 或者后续重构为 Pydantic。目前 BattleContext 仍作为运行时上下文及其复杂。

@dataclass
class Modifier:
    """属性修正值 (Legacy/Helper)"""
    stat_name: str
    value: float
    source: str
    duration: int = 1

@dataclass
class BattleContext:
    """战场快照 - 单回合上下文"""
    round_number: int
    distance: int
    terrain: Terrain = Terrain.SPACE
    attacker: Optional['MechaSnapshot'] = None
    defender: Optional['MechaSnapshot'] = None
    weapon: Optional['WeaponSnapshot'] = None
    
    initiative_holder: Optional['MechaSnapshot'] = None
    initiative_reason: Optional[InitiativeReason] = None
    
    roll: int = 0
    attack_result: Optional[AttackResult] = None
    damage: int = 0
    
    attacker_will_delta: int = 0
    defender_will_delta: int = 0
    
    modifiers: Dict[str, Any] = field(default_factory=dict)
    shared_state: Dict[tuple[str, str, str], Any] = field(default_factory=dict)
    hook_stack: List[str] = field(default_factory=list)
    cached_results: Dict[str, Any] = field(default_factory=dict)

# 保留 Effect 相关的 Dataclasses 供技能系统使用
@dataclass
class Condition:
    type: str
    params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SideEffect:
    type: str
    params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Effect:
    id: str
    name: str
    source_id: str = ""  # 效果来源标识（技能ID/装备ID/机体ID），用于调试追踪
    hook: str = ""
    operation: str = "add"
    value: float | str = 0
    priority: int = 50
    sub_priority: int = 500
    trigger_chance: float = 1.0
    target: str = "self"
    duration: int = 1
    charges: int = -1
    consume_charges: bool = False  # 是否在触发时自动消耗次数
    conditions: List[Condition] = field(default_factory=list)
    side_effects: List[SideEffect] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)

