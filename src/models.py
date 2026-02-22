"""
数据模型定义
包含所有枚举类型、配置模型 (Pydantic) 和快照模型 (Snapshot)
"""

from enum import Enum
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from dataclasses import dataclass, field
from .config import Config

# ============================================================================
# 枚举类型 (Enums)
# ============================================================================

class WeaponType(str, Enum):
    """武器类型"""
    MELEE = "MELEE"      # < 2000m
    SHOOTING = "SHOOTING"   # 1000m - 6000m (Was "RIFLE")
    AWAKENING = "AWAKENING"  # 浮游炮等
    SPECIAL = "SPECIAL"    # 地图炮或其他
    FALLBACK = "FALLBACK"   # 保底武器
    HEAVY = "HEAVY"     # 重武器

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

    # EN 回能属性 (每回合自动回复)
    init_en_regen_rate: float = 0.0    # 百分比回能 (例如 2.0 表示 2%)
    init_en_regen_fixed: int = 0         # 固定值回能

class EquipmentConfig(BaseModel):
    """装备/部件配置表"""
    id: str
    name: str
    type: str               # WEAPON / EQUIP - 装备类型

    # 属性修正 (加法叠加)
    # key 必须匹配 MechaSnapshot 中的属性名 (e.g. "final_max_hp", "final_mobility")
    # 或者原始属性名 (e.g. "init_hp")，具体由 Factory 处理
    stat_modifiers: Dict[str, float] = {}

    # 武器特有属性 (仅当 type="WEAPON" 时有效)
    # 使用 alias 兼容 JSON 中的字段名
    weapon_power: Optional[int] = Field(default=None, alias="power")
    weapon_range_min: Optional[int] = None
    weapon_range_max: Optional[int] = None
    weapon_en_cost: Optional[int] = Field(default=None, alias="en_cost")
    weapon_type: Optional[WeaponType] = None  # 具体武器类型 (MELEE/RIFLE等)
    weapon_will_req: int = 0  # 气力需求
    weapon_tags: List[str] = Field(default=[], alias="tags")
    weapon_anim_id: str = "default_anim"

    # 用于接收嵌套的 range 对象 (from weapons.json)
    range: Optional[Dict[str, int]] = None

    # 携带技能
    passive_skills: List[str] = []

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode='before')
    @classmethod
    def extract_range_fields(cls, data: Any) -> Any:
        """从嵌套的 range 对象中提取 min/max 值到 weapon_range_min/max，并处理 weapon_type"""
        if not isinstance(data, dict):
            return data

        # 如果有 range 对象，提取 min 和 max
        if 'range' in data and isinstance(data['range'], dict):
            range_data = data['range']
            # 只在还没有 weapon_range_min/max 时才设置
            if 'min' in range_data and 'weapon_range_min' not in data:
                data['weapon_range_min'] = range_data['min']
            if 'max' in range_data and 'weapon_range_max' not in data:
                data['weapon_range_max'] = range_data['max']

        # 处理 weapon_type 中英文映射
        if 'weapon_type' in data:
            weapon_type_map = {
                "格斗": "MELEE",
                "射击": "SHOOTING",
                "觉醒": "AWAKENING",
                "特殊": "SPECIAL",
                "撞击": "FALLBACK",
                "MELEE": "MELEE",
                "RIFLE": "SHOOTING",     # Backward compatibility
                "SHOOTING": "SHOOTING",
                "AWAKENING": "AWAKENING",
                "SPECIAL": "SPECIAL",
                "FALLBACK": "FALLBACK",
                "HEAVY": "HEAVY"
            }
            if data['weapon_type'] in weapon_type_map:
                data['weapon_type'] = weapon_type_map[data['weapon_type']]

        return data

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

    # EN 回能属性 (每回合自动回复)
    final_en_regen_rate: float = 0.0   # 百分比回能 (例如 2.0 表示 2%)
    final_en_regen_fixed: int = 0        # 固定值回能
    
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
    # 辅助属性 (Helper Properties)
    # ========================================================================

    @property
    def id(self) -> str: return self.instance_id

    @property
    def name(self) -> str: return self.mecha_name

    @property
    def max_hp(self) -> int: return self.final_max_hp

    @property
    def max_en(self) -> int: return self.final_max_en

    # ========================================================================
    # 辅助方法 (Helper Methods)
    # ========================================================================

    def is_alive(self) -> bool:
        """检查机体是否存活"""
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
    """战场快照 - 单回合上下文

    命名约定:
    - mecha_a/mecha_b: 战斗中的两侧机体（位置性命名，不固定表示攻击方或防御方）
    - 具体的攻防角色由战斗流程动态决定，每回合可能互换
    """
    round_number: int
    distance: int
    terrain: Terrain = Terrain.SPACE
    mecha_a: Optional['MechaSnapshot'] = None
    mecha_b: Optional['MechaSnapshot'] = None
    weapon: Optional['WeaponSnapshot'] = None

    initiative_holder: Optional['MechaSnapshot'] = None
    initiative_reason: Optional[InitiativeReason] = None

    roll: float = 0.0
    attack_result: Optional[AttackResult] = None
    damage: int = 0

    # 当前攻击方和防御方的气力变化（由战斗流程动态决定）
    current_attacker_will_delta: int = 0
    current_defender_will_delta: int = 0

    modifiers: Dict[str, Any] = field(default_factory=dict)
    shared_state: Dict[tuple[str, str, str], Any] = field(default_factory=dict)
    hook_stack: List[str] = field(default_factory=list)
    cached_results: Dict[str, Any] = field(default_factory=dict)

    # ========================================================================
    # 辅助方法 (Helper Methods)
    # ========================================================================

    @property
    def attacker(self) -> Optional['MechaSnapshot']:
        """获取当前攻击方（兼容性属性，推荐使用 get_attacker()）"""
        return self.get_attacker()

    @property
    def defender(self) -> Optional['MechaSnapshot']:
        """获取当前防御方（兼容性属性，推荐使用 get_defender()）"""
        return self.get_defender()

    def get_attacker(self) -> Optional['MechaSnapshot']:
        """获取当前攻击方机体

        通过 weapon 的所有者判断谁是当前攻击方。
        如果无法判断，按优先级返回：initiative_holder > mecha_a > None
        """
        if self.mecha_a and self.weapon in self.mecha_a.weapons:
            return self.mecha_a
        if self.mecha_b and self.weapon in self.mecha_b.weapons:
            return self.mecha_b
        # Fallback 1: 如果 initiative_holder 设置了，使用它
        if self.initiative_holder:
            return self.initiative_holder
        # Fallback 2: 默认返回 mecha_a（兼容测试场景）
        return self.mecha_a

    def get_defender(self) -> Optional['MechaSnapshot']:
        """获取当前防御方机体

        通过 weapon 的所有者判断谁是当前防御方（即另一侧）。
        如果无法判断，返回 None。
        """
        attacker = self.get_attacker()
        if attacker is None:
            return None
        if attacker == self.mecha_a:
            return self.mecha_b
        return self.mecha_a

    def set_attacker(self, mecha: 'MechaSnapshot') -> None:
        """设置当前攻击方

        根据传入的机体是 mecha_a 还是 mecha_b，确保 weapon 属于该机体。
        """
        if mecha == self.mecha_a:
            self.initiative_holder = self.mecha_a
        elif mecha == self.mecha_b:
            self.initiative_holder = self.mecha_b
        else:
            raise ValueError("传入的机体必须是 mecha_a 或 mecha_b 之一")

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

# ============================================================================
# 轻量级技能系统模型 (Lightweight Skill System Models)
# ============================================================================

@dataclass(frozen=True)
class TriggerEvent:
    """技能触发事件（结构化数据，用于前端演出、统计分析）"""
    skill_id: str              # 技能ID
    owner: Any                 # 触发者 (Mecha 对象)
    hook_name: str             # 触发的钩子
    effect_text: str           # 描述文本
    old_value: Any            # 触发前的值
    new_value: Any            # 触发后的值
    probability: float | None = None  # 概率技能的触发概率
    triggered: bool = True    # 是否实际触发（False 表示概率失败）

@dataclass
class BuffState:
    """轻量级技能状态（用于 UI 图标显示、持续时间管理）"""
    skill_id: str               # 技能ID
    duration: int = -1          # 剩余回合数 (-1 = 永久)
    charges: int = -1            # 剩余次数 (-1 = 无限)

    def is_expired(self) -> bool:
        """检查是否过期

        规则：
        - duration == 0 或 charges == 0 时过期
        - duration == -1 或 charges == -1 表示永久/无限
        """
        return self.duration == 0 or self.charges == 0

    def tick(self) -> None:
        """回合结束时调用"""
        if self.duration > 0:
            self.duration -= 1
        if self.charges > 0:
            self.charges -= 1

