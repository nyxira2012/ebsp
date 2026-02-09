"""
数据模型定义
包含所有枚举类型和数据类 (Dataclasses)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from .config import Config

# ============================================================================
# 枚举类型 (Enums)
# ============================================================================

class WeaponType(Enum):
    """武器类型"""
    MELEE = "格斗"      # < 2000m
    RIFLE = "射击"      # 1000m - 6000m
    HEAVY = "狙击"      # > 3000m
    FALLBACK = "撞击"   # 保底武器


class AttackResult(Enum):
    """攻击判定结果"""
    MISS = "未命中"
    DODGE = "躲闪"
    PARRY = "招架"
    BLOCK = "格挡"
    CRIT = "暴击"
    HIT = "命中"


class InitiativeReason(Enum):
    """先手原因"""
    PERFORMANCE = "机体性能优势"
    PILOT = "驾驶员感知优势"
    ADVANTAGE = "气力优势延续"
    COUNTER = "战术反超"
    FORCED_SWITCH = "强制换手机制"


class Terrain(Enum):
    """地形类型"""
    SPACE = "宇宙"
    SKY = "空中"
    GROUND = "地面"
    WATER = "水下"
    FOREST = "森林" # 覆盖率高，防御/回避修正
    BASE = "基地"   # 回复HP/EN，防御修正



# ============================================================================
# 数据模型 (Data Models)
# ============================================================================

@dataclass
class Modifier:
    """属性修正值"""
    stat_name: str              # 属性名称 (e.g., "hit_rate", "defense_level")
    value: float                # 修正值 (加算)
    source: str                 # 来源 (e.g., "SKILL_FOCUS", "ITEM_BOOSTER")
    duration: int = 1           # 持续回合数 (-1 表示无限)


@dataclass
class Effect:
    """状态效果 (Buff/Debuff/Trait Effect)
    
    完整的效果数据模型，支持：
    - 钩子点挂载（hook）
    - 多种操作类型（add/mul/override/callback）
    - 概率触发（trigger_chance）
    - 条件检查（conditions）
    - 副作用（side_effects）
    - 次数限制（charges）
    - 优先级控制（priority + sub_priority）
    """
    id: str                     # 效果ID (e.g., "spirit_valor", "trait_bunshin")
    name: str                   # 显示名称
    hook: str                   # 挂载的钩子点名称 (e.g., "HOOK_PRE_DAMAGE_MULT")
    operation: str              # 操作类型: "add"(加法) / "mul"(乘法) / "override"(覆盖) / "callback"(回调)
    value: float | str          # 数值或回调函数名 (float for add/mul/override, str for callback)
    
    # 优先级控制
    priority: int = 50          # 主优先级 (0-100): 0=被动, 21-50=Buff, 51-80=倍率, 81-99=条件, 100=绝对
    sub_priority: int = 500     # 子优先级 (0-1000): 同 priority 下的排序，默认 500
    
    # 触发控制
    trigger_chance: float = 1.0 # 触发概率 (0.0-1.0): 1.0=必定触发, 0.5=50%概率
    target: str = "self"        # 作用目标: "self"=自己, "enemy"=对方, "both"=双方
    
    # 生命周期
    duration: int = 1           # 持续回合数: -1=永久, 0=已失效, >0=剩余回合
    charges: int = -1           # 生效次数 (-1=无限, >0=有限次数): -1=无限, 0=已用完, >0=剩余次数
    
    # 条件与副作用
    conditions: list[dict[str, Any]] = field(default_factory=list)  # 触发条件列表
    side_effects: list[dict[str, Any]] = field(default_factory=list)  # 副作用列表
    
    # 兼容性字段
    payload: dict[str, Any] = field(default_factory=dict)  # 额外数据（向后兼容）


@dataclass
class Condition:
    """效果触发条件
    
    用于检查 Effect 是否应该触发。
    支持多种条件类型：HP阈值、气力阈值、武器属性、对方状态等。
    """
    type: str                   # 条件类型 (e.g., "hp_threshold", "will_threshold", "weapon_tag")
    val: Any                    # 条件值（根据类型不同而不同）
    op: str = ">"               # 比较操作符: ">", "<", "==", ">=", "<=", "!="
    
    # 可选字段
    target: str = "self"        # 检查目标: "self"=自己, "enemy"=对方
    ref_hook: str | None = None # 跨钩子引用: 引用其他钩子点的计算结果


@dataclass
class SideEffect:
    """效果副作用
    
    Effect 触发后产生的副作用，用于消耗资源、修改状态等。
    例如：消耗EN、回复气力、累积计数器等。
    """
    type: str                   # 副作用类型 (e.g., "consume_en", "modify_will", "modify_stat")
    val: float                  # 副作用数值
    target: str = "self"        # 作用目标: "self"=自己, "enemy"=对方, "both"=双方
    
    # 可选字段（用于特定副作用类型）
    stat: str | None = None     # 对于 "modify_stat" 类型，指定要修改的属性名


@dataclass
class Pilot:
    """驾驶员数据模型"""
    id: str                     # 唯一标识符
    name: str                   # 名称
    stat_shooting: int          # 射击值 (影响射击类武器)
    stat_melee: int             # 格斗值 (影响格斗类武器)
    stat_awakening: int         # 觉醒值 (影响特殊武器和直觉回避)
    stat_defense: int           # 守备值 (影响减伤和抗暴击)
    stat_reaction: int          # 反应值 (影响躲闪/招架/格挡/先攻)
    
    # 熟练度 (可选，默认值)
    weapon_proficiency: int = 500   # 武器熟练度 (0-1000)
    mecha_proficiency: int = 2000   # 机体熟练度 (0-4000)
    
    # 动态状态
    effects: list[Effect] = field(default_factory=list)
    stat_modifiers: dict[str, float] = field(default_factory=dict)

    # 技能钩子 (保留用于兼容，建议迁移到 Effect 系统)
    hooks: dict[str, float] = field(default_factory=dict)
    
    def get_effective_stat(self, stat_name: str) -> float:
        """获取包含修正值的属性值"""
        base_value = getattr(self, stat_name, 0)
        modifier = self.stat_modifiers.get(stat_name, 0.0)
        return base_value + modifier

    def __post_init__(self) -> None:
        """初始化默认钩子"""
        if not self.hooks:
            self.hooks = {
                'HOOK_HIT_ADD': 0.0,
                'HOOK_EVA_ADD': 0.0,
                'HOOK_DMG_MUL': 1.0,
                'HOOK_DEF_MUL': 1.0,
                'HOOK_WILL_ADD': 0.0,
                'HOOK_EN_COST_MUL': 1.0,
            }


@dataclass
class Weapon:
    """武器数据模型"""
    id: str                     # 唯一标识符
    name: str                   # 名称
    weapon_type: WeaponType     # 武器类型
    power: int                  # 威力
    en_cost: int                # EN消耗
    range_min: int              # 最小射程 (米)
    range_max: int              # 最大射程 (米)
    hit_penalty: float = 0.0    # 命中惩罚 (例如射击类在距离外-30%)
    
    def can_use_at_distance(self, distance: int) -> bool:
        """检查武器在当前距离是否可用。

        Args:
            distance: 当前交战距离 (米)

        Returns:
            bool: 距离在武器射程范围内返回 True,否则返回 False
        """
        return self.range_min <= distance <= self.range_max
    
    def get_hit_modifier_at_distance(self, distance: int) -> float:
        """获取当前距离下的命中修正值。

        计算逻辑:
        - 距离不在射程内: 返回 -999.0 (完全无法使用)
        - 射击类武器(RIFLE)在边缘距离(<1000m 或 >6000m): 返回配置的惩罚值
        - 其他情况: 返回武器的默认命中修正

        Args:
            distance: 当前交战距离 (米)

        Returns:
            float: 命中修正百分比 (例如 -30.0 表示 -30%, -999.0 表示不可用)
        """
        if not self.can_use_at_distance(distance):
            return -999.0  # 完全无法使用

        # 射击类武器在边缘距离有惩罚
        if self.weapon_type == WeaponType.RIFLE:
            if distance < 1000 or distance > 6000:
                return Config.RIFLE_RANGE_PENALTY

        return self.hit_penalty


@dataclass
class Mecha:
    """机体数据模型"""
    id: str                     # 唯一标识符
    name: str                   # 名称
    pilot: Pilot                # 驾驶员对象
    
    # 基础属性
    max_hp: int
    current_hp: int
    max_en: int
    current_en: int
    
    # 攻击属性
    hit_rate: float             # 命中加成 (减少未命中率)
    precision: float            # 精准值 (削减对方防御概率)
    crit_rate: float            # 暴击加成
    
    # 防御属性
    dodge_rate: float           # 躲闪基础值
    parry_rate: float           # 招架基础值
    block_rate: float           # 格挡基础值
    defense_level: int          # 装甲等级
    
    # 机体性能
    mobility: int               # 机动性 (影响先手判定)
    
    # 带默认值的字段必须放在最后
    block_value: int = 0        # 格挡固定减伤值
    
    # 武器列表
    weapons: list[Weapon] = field(default_factory=list)
    
    # 战斗状态
    current_will: int = Config.WILL_INITIAL  # 当前气力
    
    # 机体特性 (trait ID 列表)
    traits: list[str] = field(default_factory=list)

    # 动态状态
    effects: list[Effect] = field(default_factory=list)
    stat_modifiers: dict[str, float] = field(default_factory=dict)
    
    # 技能钩子 (保留用于兼容)
    hooks: dict[str, bool | float] = field(default_factory=dict)
    
    def get_effective_stat(self, stat_name: str) -> float:
        """获取包含修正值的属性值"""
        base_value = getattr(self, stat_name, 0)
        modifier = self.stat_modifiers.get(stat_name, 0.0)
        return base_value + modifier

    def __post_init__(self) -> None:
        """初始化"""
        if not self.hooks:
            self.hooks = {
                'HOOK_FORCE_INITIATIVE': False,
                'HOOK_IGNORE_ARMOR': False,
                'HOOK_GUARANTEE_PARRY': False,
                'HOOK_IGNORE_RANGE_PENALTY': False,
                'HOOK_SUPPRESS_ESCAPE': False,
                'HOOK_DEATH_RESIST': False,
            }
    
    def is_alive(self) -> bool:
        """检查机体是否存活。

        Returns:
            bool: 当前 HP 大于 0 返回 True,否则返回 False
        """
        return self.current_hp > 0
    
    def get_hp_percentage(self) -> float:
        """获取当前 HP 的百分比。

        Returns:
            float: HP 百分比 (0.0 - 100.0)
        """
        return (self.current_hp / self.max_hp) * 100
    
    def can_attack(self, weapon: Weapon) -> bool:
        """检查机体是否有足够 EN 发动攻击。

        Args:
            weapon: 要使用的武器对象

        Returns:
            bool: 当前 EN 大于等于武器消耗返回 True,否则返回 False
        """
        return self.current_en >= weapon.en_cost
    
    def consume_en(self, amount: int) -> None:
        """消耗指定数量的 EN。

        EN 最低降至 0,不会出现负值。

        Args:
            amount: 要消耗的 EN 数量
        """
        self.current_en = max(0, self.current_en - amount)
    
    def take_damage(self, damage: int) -> None:
        """受到伤害,扣除对应 HP。

        HP 最低降至 0,不会出现负值。

        Args:
            damage: 受到的伤害数值
        """
        self.current_hp = max(0, self.current_hp - damage)
    
    def modify_will(self, delta: int) -> None:
        """修改气力值。

        气力会被限制在配置的最小值和最大值之间。

        Args:
            delta: 气力变化量 (正数为增加,负数为减少)
        """
        self.current_will = max(Config.WILL_MIN, min(Config.WILL_MAX, self.current_will + delta))


@dataclass
class BattleContext:
    """战场快照 - 单回合上下文
    
    包含完整的战斗状态和上下文信息，支持：
    - 基础战斗信息（回合数、距离、地形）
    - 双方机体和武器
    - 判定结果和伤害
    - 共享状态和缓存（用于跨钩子通信）
    - 递归防护（防止钩子死锁）
    """
    round_number: int
    distance: int
    terrain: Terrain = Terrain.SPACE
    attacker: Mecha | None = None
    defender: Mecha | None = None
    weapon: Weapon | None = None
    
    # 先手相关
    initiative_holder: Mecha | None = None
    initiative_reason: InitiativeReason | None = None
    
    # 判定结果
    roll: int = 0
    attack_result: AttackResult | None = None
    damage: int = 0
    
    # 气力变动
    attacker_will_delta: int = 0
    defender_will_delta: int = 0

    # 扩展上下文（向后兼容）
    modifiers: dict[str, Any] = field(default_factory=dict) # 临时的战斗修正
    event_flags: set[str] = field(default_factory=set)      # 战斗事件标记 (e.g. "COUNTER_TRIGGERED")
    
    # ========== 新增字段（技能系统支持） ==========
    
    # 共享状态字典 - 用于跨 Effect 通信和状态共享
    # 例如：学习电脑累积层数、连续攻击计数等
    # 格式: {(effect_id, state_key, lifecycle): value}
    shared_state: dict[tuple[str, str, str], Any] = field(default_factory=dict)
    
    # 钩子栈 - 防止递归死锁
    # 记录当前正在处理的钩子点调用链，防止循环引用
    hook_stack: list[str] = field(default_factory=list)
    
    # 缓存结果字典 - 用于跨钩子引用
    # 存储每个钩子点的计算结果，供后续钩子点查询
    # 格式: {hook_name: calculated_value}
    cached_results: dict[str, Any] = field(default_factory=dict)



