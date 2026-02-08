"""
真实系机甲回合制策略游戏 - 战斗模拟器 MVP (Minimum Viable Product)
基于 game design document (GDD) 严格实现

技术栈:
- Python 3.10+
- 面向对象编程 (OOP)
- 数据类 (Dataclasses)
- 强类型提示 (Type Hints)

核心特性:
1. 圆桌判定系统 (One-Roll System)
2. 气力系统 (Will System)
3. 动态先手判定 (Initiative System)
4. 动态距离机制 (Dynamic Range)
5. 武器选择策略 (Weapon Selection)
6. 技能钩子系统 (Skill Hooks)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Literal, Tuple
from enum import Enum
from abc import ABC, abstractmethod
import random
import math
import sys
import io

# ============================================================================
# 环境兼容性处理 (Windows UTF-8 Fix)
# ============================================================================
if sys.platform.startswith('win'):
    # 强制标准输出使用 utf-8 编码，防止 Windows GBK 环境报错
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ============================================================================
# 配置常量 (Configuration Constants)
# ============================================================================

class Config:
    """全局游戏配置"""
    
    # 气力系统
    WILL_INITIAL = 100
    WILL_MIN = 50
    WILL_MAX = 150
    WILL_EXTENDED_MAX = 200  # 特殊技能可解锁
    
    # 回合限制
    MAX_ROUNDS = 4
    
    # 距离配置
    DISTANCE_INITIAL_MIN = 3000
    DISTANCE_INITIAL_MAX = 7000
    DISTANCE_REDUCTION_PER_ROUND = 1500
    DISTANCE_FINAL_MIN = 0
    DISTANCE_FINAL_MAX = 2000
    
    # 圆桌基础概率
    BASE_MISS_RATE = 12.0      # 基础未命中率 %
    BASE_DODGE_RATE = 22.0     # 基础躲闪率 %
    BASE_PARRY_RATE = 15.0     # 基础招架率 %
    BASE_BLOCK_RATE = 20.0     # 基础格挡率 %
    BASE_CRIT_RATE = 25.0      # 基础暴击率 %
    
    # 护甲系数 (用于减伤公式: 减伤% = 护甲 / (护甲 + K))
    ARMOR_K = 100
    
    # 暴击倍率
    CRIT_MULTIPLIER = 1.5
    
    # 气力修正公式
    WILL_MODIFIER_BASE = 100  # 气力基准值
    
    # 熟练度配置
    WEAPON_PROFICIENCY_THRESHOLD = 1000
    MECHA_PROFICIENCY_THRESHOLD = 4000


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


# ============================================================================
# 数据模型 (Data Models)
# ============================================================================

@dataclass
class Pilot:
    """驾驶员数据模型"""
    name: str
    stat_shooting: int      # 射击值 (影响射击类武器)
    stat_melee: int         # 格斗值 (影响格斗类武器)
    stat_awakening: int     # 觉醒值 (影响特殊武器和直觉回避)
    stat_defense: int       # 守备值 (影响减伤和抗暴击)
    stat_reaction: int      # 反应值 (影响躲闪/招架/格挡/先攻)
    
    # 熟练度 (简化实现)
    weapon_proficiency: int = 500   # 武器熟练度 (0-1000)
    mecha_proficiency: int = 2000   # 机体熟练度 (0-4000)
    
    # 技能钩子 (预留)
    hooks: Dict[str, float] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化默认钩子"""
        if not self.hooks:
            self.hooks = {
                'HOOK_HIT_ADD': 0.0,
                'HOOK_EVA_ADD': 0.0,
                'HOOK_DMG_MUL': 1.0,
                'HOOK_DEF_MUL': 1.0,
                'HOOK_WILL_ADD': 0,
                'HOOK_EN_COST_MUL': 1.0,
            }


@dataclass
class Weapon:
    """武器数据模型"""
    name: str
    weapon_type: WeaponType
    power: int              # 威力
    en_cost: int            # EN消耗
    range_min: int          # 最小射程 (米)
    range_max: int          # 最大射程 (米)
    hit_penalty: float = 0.0  # 命中惩罚 (例如射击类在距离外-30%)
    
    def can_use_at_distance(self, distance: int) -> bool:
        """检查武器在当前距离是否可用"""
        return self.range_min <= distance <= self.range_max
    
    def get_hit_modifier_at_distance(self, distance: int) -> float:
        """获取距离修正"""
        if not self.can_use_at_distance(distance):
            return -999.0  # 完全无法使用
        
        # 射击类武器在边缘距离有惩罚
        if self.weapon_type == WeaponType.RIFLE:
            if distance < 1000 or distance > 6000:
                return -30.0
        
        return self.hit_penalty


@dataclass
class Mecha:
    """机体数据模型"""
    name: str
    pilot: Pilot
    
    # 基础属性
    max_hp: int
    current_hp: int
    max_en: int
    current_en: int
    
    # 攻击属性
    hit_rate: float         # 命中加成 (减少未命中率)
    precision: float        # 精准值 (削减对方防御概率)
    crit_rate: float        # 暴击加成
    
    # 防御属性
    dodge_rate: float       # 躲闪基础值
    parry_rate: float       # 招架基础值
    block_rate: float       # 格挡基础值
    defense_level: int      # 装甲等级
    
    # 机体性能
    mobility: int           # 机动性 (影响先手判定)
    
    # 带默认值的字段必须放在最后
    block_value: int = 0    # 格挡固定减伤值
    
    # 武器列表
    weapons: List[Weapon] = field(default_factory=list)
    
    # 战斗状态
    current_will: int = Config.WILL_INITIAL  # 当前气力
    
    # 技能钩子 (预留)
    hooks: Dict[str, float] = field(default_factory=dict)
    
    def __post_init__(self):
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
        """检查是否存活"""
        return self.current_hp > 0
    
    def get_hp_percentage(self) -> float:
        """获取当前HP百分比"""
        return (self.current_hp / self.max_hp) * 100
    
    def can_attack(self, weapon: Weapon) -> bool:
        """检查是否有足够EN发动攻击"""
        return self.current_en >= weapon.en_cost
    
    def consume_en(self, amount: int):
        """消耗EN"""
        self.current_en = max(0, self.current_en - amount)
    
    def take_damage(self, damage: int):
        """受到伤害"""
        self.current_hp = max(0, self.current_hp - damage)
    
    def modify_will(self, delta: int):
        """修改气力"""
        self.current_will = max(Config.WILL_MIN, min(Config.WILL_MAX, self.current_will + delta))


@dataclass
class BattleContext:
    """战场快照 - 单回合上下文"""
    round_number: int
    distance: int
    attacker: Mecha
    defender: Mecha
    weapon: Weapon
    
    # 先手相关
    initiative_holder: Mecha
    initiative_reason: InitiativeReason
    
    # 判定结果
    roll: int = 0
    attack_result: Optional[AttackResult] = None
    damage: int = 0
    
    # 气力变动
    attacker_will_delta: int = 0
    defender_will_delta: int = 0


# ============================================================================
# 核心计算器 (Core Calculators)
# ============================================================================

class CombatCalculator:
    """战斗计算核心"""
    
    @staticmethod
    def calculate_proficiency_miss_penalty(proficiency: int) -> float:
        """
        计算武器熟练度导致的未命中惩罚
        公式: 当前未命中率 = 12% + (18% * (1 - (Min(次数, 1000)/1000)^1.5))
        """
        clamped = min(proficiency, Config.WEAPON_PROFICIENCY_THRESHOLD)
        ratio = (clamped / Config.WEAPON_PROFICIENCY_THRESHOLD) ** 1.5
        penalty = 18.0 * (1 - ratio)
        return Config.BASE_MISS_RATE + penalty
    
    @staticmethod
    def calculate_proficiency_defense_ratio(proficiency: int, base_rate: float) -> float:
        """
        计算机体熟练度对躲闪/招架的影响
        公式: 当前比率 = 基础比率 * (log(Min(次数, 4000) + 1) / log(4000 + 1))
        """
        clamped = min(proficiency, Config.MECHA_PROFICIENCY_THRESHOLD)
        ratio = math.log(clamped + 1) / math.log(Config.MECHA_PROFICIENCY_THRESHOLD + 1)
        return base_rate * ratio
    
    @staticmethod
    def calculate_will_damage_modifier(will: int) -> float:
        """气力对伤害的修正: 伤害修正系数 = 气力 / 100"""
        return will / Config.WILL_MODIFIER_BASE
    
    @staticmethod
    def calculate_will_defense_modifier(will: int) -> float:
        """气力对防御的修正: 有效装甲值 = 基础装甲 * (气力 / 100)"""
        return will / Config.WILL_MODIFIER_BASE
    
    @staticmethod
    def calculate_will_stability_bonus(will: int) -> float:
        """
        气力对命中/躲闪的微调
        公式: 命中/躲闪附加率 = (气力 - 100) * 0.2%
        """
        return (will - Config.WILL_MODIFIER_BASE) * 0.002
    
    @staticmethod
    def calculate_armor_mitigation(armor: int, will_modifier: float) -> float:
        """
        护甲减伤计算 (非线性)
        公式: 减伤% = (护甲 * 气力修正) / (护甲 * 气力修正 + K)
        """
        effective_armor = armor * will_modifier
        return effective_armor / (effective_armor + Config.ARMOR_K)
    
    @staticmethod
    def calculate_precision_reduction(precision: float) -> float:
        """
        精准削减防御概率的比例
        简化公式: 削减比 = precision / 100
        例如: 精准30 -> 削减30%防御概率
        """
        return min(precision / 100.0, 0.8)  # 最多削减80%


class AttackTableResolver:
    """圆桌判定系统 (核心难点)"""
    
    @staticmethod
    def resolve_attack(ctx: BattleContext) -> Tuple[AttackResult, int]:
        """
        单一随机数判定
        返回: (判定结果, 最终伤害)
        
        优先级顺序:
        1. Miss (未命中)
        2. Dodge (躲闪)
        3. Parry (招架)
        4. Block (格挡)
        5. Crit (暴击)
        6. Hit (普通命中)
        """
        attacker = ctx.attacker
        defender = ctx.defender
        weapon = ctx.weapon
        
        # 生成 0-100 随机数
        roll = random.randint(0, 100)
        ctx.roll = roll
        
        # === 1. 计算未命中区间 ===
        miss_rate = CombatCalculator.calculate_proficiency_miss_penalty(
            attacker.pilot.weapon_proficiency
        )
        # 命中加成减少未命中率
        miss_rate = max(0, miss_rate - attacker.hit_rate)
        
        # === 2. 计算防御概率 (受精准削减) ===
        precision_reduction = CombatCalculator.calculate_precision_reduction(attacker.precision)
        
        # 躲闪率 (受机体熟练度影响)
        dodge_base = CombatCalculator.calculate_proficiency_defense_ratio(
            defender.pilot.mecha_proficiency,
            Config.BASE_DODGE_RATE
        )
        dodge_rate = dodge_base * (1 - precision_reduction)
        dodge_rate = max(0, dodge_rate)
        
        # 招架率 (受机体熟练度影响)
        parry_base = CombatCalculator.calculate_proficiency_defense_ratio(
            defender.pilot.mecha_proficiency,
            Config.BASE_PARRY_RATE
        )
        parry_rate = parry_base * (1 - precision_reduction)
        parry_rate = max(0, min(50, parry_rate))  # 最高50%
        
        # 格挡率
        block_rate = defender.block_rate * (1 - precision_reduction)
        block_rate = max(0, min(80, block_rate))  # 最高80%
        
        # === 3. 暴击率 ===
        crit_rate = min(100, attacker.crit_rate)
        
        # === 4. 构建圆桌 (优先级排列) ===
        current_threshold = 0.0
        
        # Miss
        current_threshold += miss_rate
        if roll <= current_threshold:
            return AttackTableResolver._resolve_miss(ctx)
        
        # Dodge
        current_threshold += dodge_rate
        if roll <= current_threshold:
            return AttackTableResolver._resolve_dodge(ctx)
        
        # Parry
        current_threshold += parry_rate
        if roll <= current_threshold:
            return AttackTableResolver._resolve_parry(ctx)
        
        # Block
        current_threshold += block_rate
        if roll <= current_threshold:
            return AttackTableResolver._resolve_block(ctx)
        
        # 剩余空间分配给 Crit 和 Hit
        remaining = 100 - current_threshold
        
        # Crit 占用剩余空间的一部分
        crit_threshold = current_threshold + (remaining * crit_rate / 100)
        if roll <= crit_threshold:
            return AttackTableResolver._resolve_crit(ctx)
        
        # Hit 占据剩余全部
        return AttackTableResolver._resolve_hit(ctx)
    
    @staticmethod
    def _calculate_base_damage(ctx: BattleContext) -> int:
        """计算基础伤害"""
        attacker = ctx.attacker
        weapon = ctx.weapon
        
        # 武器威力 + 机体性能修正 (简化: 使用驾驶员对应属性)
        if weapon.weapon_type == WeaponType.MELEE:
            stat_bonus = attacker.pilot.stat_melee
        elif weapon.weapon_type in [WeaponType.RIFLE, WeaponType.HEAVY]:
            stat_bonus = attacker.pilot.stat_shooting
        else:  # FALLBACK
            stat_bonus = 0
        
        base_damage = weapon.power + (stat_bonus * 2)  # 简化公式
        
        # 气力修正
        will_modifier = CombatCalculator.calculate_will_damage_modifier(attacker.current_will)
        base_damage = int(base_damage * will_modifier)
        
        # 技能钩子: 伤害乘数
        damage_multiplier = attacker.pilot.hooks.get('HOOK_DMG_MUL', 1.0)
        base_damage = int(base_damage * damage_multiplier)
        
        return base_damage
    
    @staticmethod
    def _apply_armor_mitigation(damage: int, ctx: BattleContext) -> int:
        """应用护甲减伤"""
        defender = ctx.defender
        
        # 气力对防御的修正
        will_def_modifier = CombatCalculator.calculate_will_defense_modifier(defender.current_will)
        
        # 护甲减伤
        mitigation_ratio = CombatCalculator.calculate_armor_mitigation(
            defender.defense_level,
            will_def_modifier
        )
        
        # 技能钩子: 防御乘数
        defense_multiplier = defender.pilot.hooks.get('HOOK_DEF_MUL', 1.0)
        mitigation_ratio *= defense_multiplier
        
        # 应用减伤
        final_damage = int(damage * (1 - mitigation_ratio))
        return max(0, final_damage)
    
    @staticmethod
    def _resolve_miss(ctx: BattleContext) -> Tuple[AttackResult, int]:
        """未命中处理"""
        return (AttackResult.MISS, 0)
    
    @staticmethod
    def _resolve_dodge(ctx: BattleContext) -> Tuple[AttackResult, int]:
        """躲闪处理"""
        # 气力变动: 防御方 +5
        ctx.defender_will_delta = 5
        return (AttackResult.DODGE, 0)
    
    @staticmethod
    def _resolve_parry(ctx: BattleContext) -> Tuple[AttackResult, int]:
        """招架处理"""
        # 气力变动: 防御方 +15
        ctx.defender_will_delta = 15
        return (AttackResult.PARRY, 0)
    
    @staticmethod
    def _resolve_block(ctx: BattleContext) -> Tuple[AttackResult, int]:
        """格挡处理"""
        # 气力变动: 防御方 +5
        ctx.defender_will_delta = 5
        
        # 计算伤害并减去格挡值
        base_damage = AttackTableResolver._calculate_base_damage(ctx)
        damage_after_armor = AttackTableResolver._apply_armor_mitigation(base_damage, ctx)
        final_damage = max(0, damage_after_armor - ctx.defender.block_value)
        
        return (AttackResult.BLOCK, final_damage)
    
    @staticmethod
    def _resolve_hit(ctx: BattleContext) -> Tuple[AttackResult, int]:
        """普通命中处理"""
        # 气力变动: 攻击方 +2, 防御方 +1
        ctx.attacker_will_delta = 2
        ctx.defender_will_delta = 1
        
        base_damage = AttackTableResolver._calculate_base_damage(ctx)
        final_damage = AttackTableResolver._apply_armor_mitigation(base_damage, ctx)
        
        return (AttackResult.HIT, final_damage)
    
    @staticmethod
    def _resolve_crit(ctx: BattleContext) -> Tuple[AttackResult, int]:
        """暴击处理"""
        # 气力变动: 攻击方 +5
        ctx.attacker_will_delta = 5
        
        base_damage = AttackTableResolver._calculate_base_damage(ctx)
        # 暴击倍率
        crit_damage = int(base_damage * Config.CRIT_MULTIPLIER)
        final_damage = AttackTableResolver._apply_armor_mitigation(crit_damage, ctx)
        
        return (AttackResult.CRIT, final_damage)


class InitiativeCalculator:
    """先手判定系统"""
    
    def __init__(self):
        self.consecutive_wins = {
            'A': 0,  # A方连先次数
            'B': 0   # B方连先次数
        }
        self.last_winner = None
    
    def calculate_initiative(
        self,
        mecha_a: Mecha,
        mecha_b: Mecha,
        round_number: int
    ) -> Tuple[Mecha, Mecha, InitiativeReason]:
        """
        计算先手方和后手方
        返回: (先手方, 后手方, 先手原因)
        """
        
        # === 第一层: 绝对优先权 ===
        
        # 检查强制换手机制
        if self.consecutive_wins['A'] >= 2:
            self._update_winner('B')
            return (mecha_b, mecha_a, InitiativeReason.FORCED_SWITCH)
        
        if self.consecutive_wins['B'] >= 2:
            self._update_winner('A')
            return (mecha_a, mecha_b, InitiativeReason.FORCED_SWITCH)
        
        # 检查技能: 强制先攻
        if mecha_a.hooks.get('HOOK_FORCE_INITIATIVE', False):
            self._update_winner('A')
            return (mecha_a, mecha_b, InitiativeReason.PERFORMANCE)
        
        if mecha_b.hooks.get('HOOK_FORCE_INITIATIVE', False):
            self._update_winner('B')
            return (mecha_b, mecha_a, InitiativeReason.PERFORMANCE)
        
        # === 第二层: 综合优势判定 ===
        
        score_a = self._calculate_initiative_score(mecha_a)
        score_b = self._calculate_initiative_score(mecha_b)
        
        # 判断理由
        if score_a > score_b:
            winner = mecha_a
            reason = self._determine_reason(mecha_a, mecha_b)
            self._update_winner('A')
            return (winner, mecha_b, reason)
        elif score_b > score_a:
            winner = mecha_b
            reason = self._determine_reason(mecha_b, mecha_a)
            self._update_winner('B')
            return (winner, mecha_a, reason)
        else:
            # 平局: 上回合后手方获得先手
            if self.last_winner == 'A':
                self._update_winner('B')
                return (mecha_b, mecha_a, InitiativeReason.COUNTER)
            else:
                self._update_winner('A')
                return (mecha_a, mecha_b, InitiativeReason.COUNTER)
    
    def _calculate_initiative_score(self, mecha: Mecha) -> float:
        """
        计算先手判定值
        公式: 基底 = (机体性能 * 权重A) + (驾驶员感知 * 权重B) + 当前气力修正
        """
        # 基底
        base_score = (mecha.mobility * 0.6) + (mecha.pilot.stat_reaction * 0.4)
        
        # 气力修正
        will_bonus = mecha.current_will * 0.3
        
        # 随机事件 (小幅度)
        random_event = random.uniform(-10, 10)
        
        return base_score + will_bonus + random_event
    
    def _determine_reason(self, winner: Mecha, loser: Mecha) -> InitiativeReason:
        """判断先手原因"""
        # 简化逻辑
        mobility_diff = abs(winner.mobility - loser.mobility)
        reaction_diff = abs(winner.pilot.stat_reaction - loser.pilot.stat_reaction)
        will_diff = abs(winner.current_will - loser.current_will)
        
        if mobility_diff > 20:
            return InitiativeReason.PERFORMANCE
        elif reaction_diff > 15:
            return InitiativeReason.PILOT
        elif will_diff > 20:
            return InitiativeReason.ADVANTAGE
        else:
            return InitiativeReason.PERFORMANCE
    
    def _update_winner(self, winner_id: str):
        """更新连胜记录"""
        if self.last_winner == winner_id:
            self.consecutive_wins[winner_id] += 1
        else:
            # 换手了,重置所有计数
            self.consecutive_wins = {'A': 0, 'B': 0}
            self.consecutive_wins[winner_id] = 1
        
        self.last_winner = winner_id


class WeaponSelector:
    """武器选择策略 (AI)"""
    
    @staticmethod
    def select_best_weapon(mecha: Mecha, distance: int) -> Weapon:
        """
        选择当前距离下期望伤害最高的武器
        若无可用武器,返回保底武器 (撞击)
        """
        available_weapons = []
        
        for weapon in mecha.weapons:
            # 检查EN是否足够
            if not mecha.can_attack(weapon):
                continue
            
            # 检查距离是否适用
            if not weapon.can_use_at_distance(distance):
                continue
            
            # 计算期望伤害 (简化: 威力 * 距离修正)
            hit_mod = weapon.get_hit_modifier_at_distance(distance)
            if hit_mod <= -999:
                continue
            
            expected_damage = weapon.power * (1 + hit_mod / 100)
            available_weapons.append((weapon, expected_damage))
        
        # 如果有可用武器,选择期望伤害最高的
        if available_weapons:
            available_weapons.sort(key=lambda x: x[1], reverse=True)
            return available_weapons[0][0]
        
        # 否则返回保底武器
        return WeaponSelector._create_fallback_weapon()
    
    @staticmethod
    def _create_fallback_weapon() -> Weapon:
        """创建保底撞击武器"""
        return Weapon(
            name="撞击",
            weapon_type=WeaponType.FALLBACK,
            power=50,  # 低威力
            en_cost=0,  # 0消耗
            range_min=0,
            range_max=10000
        )


# ============================================================================
# 战斗循环 (Game Loop)
# ============================================================================

class BattleSimulator:
    """战斗模拟器主控"""
    
    def __init__(self, mecha_a: Mecha, mecha_b: Mecha):
        self.mecha_a = mecha_a
        self.mecha_b = mecha_b
        self.initiative_calc = InitiativeCalculator()
        self.round_number = 0
        self.battle_log = []
    
    def run_battle(self):
        """运行完整战斗"""
        print("=" * 80)
        print(f"战斗开始: {self.mecha_a.name} vs {self.mecha_b.name}")
        print("=" * 80)
        print()
        
        while self.round_number < Config.MAX_ROUNDS:
            self.round_number += 1
            
            # 检查战斗是否结束
            if not self.mecha_a.is_alive() or not self.mecha_b.is_alive():
                break
            
            # 执行回合
            self._execute_round()
            
            print()
        
        # 战斗结算
        self._conclude_battle()
    
    def _execute_round(self):
        """执行单个回合"""
        print(f"{'=' * 80}")
        print(f"ROUND {self.round_number}")
        print(f"{'=' * 80}")
        
        # 1. 生成距离
        distance = self._generate_distance()
        print(f"📍 交战距离: {distance}m")
        
        # 2. 先手判定
        first_mover, second_mover, reason = self.initiative_calc.calculate_initiative(
            self.mecha_a,
            self.mecha_b,
            self.round_number
        )
        print(f"⚔️  先手方: {first_mover.name} ({reason.value})")
        print()
        
        # 3. 先攻方攻击
        self._execute_attack(first_mover, second_mover, distance, is_first=True)
        
        # 检查后攻方是否存活
        if not second_mover.is_alive():
            print(f"💀 {second_mover.name} 被击破!")
            return
        
        print()
        
        # 4. 后攻方反击
        self._execute_attack(second_mover, first_mover, distance, is_first=False)
        
        # 检查先攻方是否存活
        if not first_mover.is_alive():
            print(f"💀 {first_mover.name} 被击破!")
            return
        
        # 5. 回合结束 - 气力基础增长
        self.mecha_a.modify_will(1)
        self.mecha_b.modify_will(1)
        
        print()
        print(f"📊 {self.mecha_a.name}: HP={self.mecha_a.current_hp}/{self.mecha_a.max_hp} | "
              f"EN={self.mecha_a.current_en}/{self.mecha_a.max_en} | "
              f"气力={self.mecha_a.current_will}")
        print(f"📊 {self.mecha_b.name}: HP={self.mecha_b.current_hp}/{self.mecha_b.max_hp} | "
              f"EN={self.mecha_b.current_en}/{self.mecha_b.max_en} | "
              f"气力={self.mecha_b.current_will}")
    
    def _generate_distance(self) -> int:
        """
        生成当前回合距离
        距离范围随回合数逐渐缩进
        """
        # 计算当前回合的距离范围
        rounds_elapsed = self.round_number - 1
        reduction = Config.DISTANCE_REDUCTION_PER_ROUND * rounds_elapsed
        
        range_min = max(Config.DISTANCE_FINAL_MIN, Config.DISTANCE_INITIAL_MIN - reduction)
        range_max = max(Config.DISTANCE_FINAL_MAX, Config.DISTANCE_INITIAL_MAX - reduction)
        
        # 在范围内随机
        return random.randint(range_min, range_max)
    
    def _execute_attack(
        self,
        attacker: Mecha,
        defender: Mecha,
        distance: int,
        is_first: bool
    ):
        """执行单次攻击"""
        # 1. 选择武器
        weapon = WeaponSelector.select_best_weapon(attacker, distance)
        
        print(f"{'[先攻]' if is_first else '[反击]'} {attacker.name} 使用 【{weapon.name}】"
              f" (威力:{weapon.power}, EN消耗:{weapon.en_cost})")
        
        # 2. 检查EN
        if not attacker.can_attack(weapon):
            print(f"   ❌ EN不足! 无法攻击 (当前EN: {attacker.current_en})")
            # TODO: 实现战术脱离逻辑
            return
        
        # 3. 消耗EN
        attacker.consume_en(weapon.en_cost)
        
        # 4. 创建战场上下文
        ctx = BattleContext(
            round_number=self.round_number,
            distance=distance,
            attacker=attacker,
            defender=defender,
            weapon=weapon,
            initiative_holder=attacker if is_first else defender,
            initiative_reason=InitiativeReason.PERFORMANCE  # 占位
        )
        
        # 5. 圆桌判定
        result, damage = AttackTableResolver.resolve_attack(ctx)
        
        # 6. 应用伤害
        if damage > 0:
            defender.take_damage(damage)
        
        # 7. 应用气力变化
        if ctx.attacker_will_delta != 0:
            attacker.modify_will(ctx.attacker_will_delta)
        if ctx.defender_will_delta != 0:
            defender.modify_will(ctx.defender_will_delta)
        
        # 8. 输出结果
        result_emoji = {
            AttackResult.MISS: "❌",
            AttackResult.DODGE: "💨",
            AttackResult.PARRY: "⚔️",
            AttackResult.BLOCK: "🛡️",
            AttackResult.HIT: "💥",
            AttackResult.CRIT: "💥✨"
        }
        
        print(f"   {result_emoji.get(result, '❓')} {result.value}! "
              f"Roll点: {ctx.roll} | 伤害: {damage} | "
              f"气力变化: ⚡{attacker.name}({ctx.attacker_will_delta:+d}) "
              f"⚡{defender.name}({ctx.defender_will_delta:+d})")
    
    def _conclude_battle(self):
        """战斗结算"""
        print()
        print("=" * 80)
        print("战斗结束")
        print("=" * 80)
        
        # 判断胜负
        if not self.mecha_a.is_alive():
            print(f"🏆 胜者: {self.mecha_b.name} (击破)")
        elif not self.mecha_b.is_alive():
            print(f"🏆 胜者: {self.mecha_a.name} (击破)")
        else:
            # 判定胜
            hp_a = self.mecha_a.get_hp_percentage()
            hp_b = self.mecha_b.get_hp_percentage()
            
            print(f"回合数达到上限! 进入判定...")
            print(f"{self.mecha_a.name} HP: {hp_a:.1f}%")
            print(f"{self.mecha_b.name} HP: {hp_b:.1f}%")
            
            if hp_a > hp_b:
                print(f"🏆 胜者: {self.mecha_a.name} (判定胜)")
            elif hp_b > hp_a:
                print(f"🏆 胜者: {self.mecha_b.name} (判定胜)")
            else:
                print(f"🤝 平局!")


# ============================================================================
# Mock 数据 (Demo)
# ============================================================================

def create_demo_battle():
    """创建演示战斗"""
    
    # === 驾驶员 A: 阿姆罗·雷 ===
    pilot_amuro = Pilot(
        name="阿姆罗·雷",
        stat_shooting=85,
        stat_melee=70,
        stat_awakening=90,
        stat_defense=65,
        stat_reaction=88,
        weapon_proficiency=800,   # 高熟练度
        mecha_proficiency=3500    # 高熟练度
    )
    
    # 武器: 光束步枪
    beam_rifle = Weapon(
        name="光束步枪",
        weapon_type=WeaponType.RIFLE,
        power=800,
        en_cost=20,
        range_min=1000,
        range_max=6000
    )
    
    # 武器: 光束军刀
    beam_saber = Weapon(
        name="光束军刀",
        weapon_type=WeaponType.MELEE,
        power=1200,
        en_cost=15,
        range_min=0,
        range_max=2000
    )
    
    # 机体 A: RX-78-2 高达
    gundam = Mecha(
        name="RX-78-2 高达",
        pilot=pilot_amuro,
        max_hp=5000,
        current_hp=5000,
        max_en=200,
        current_en=200,
        hit_rate=15.0,
        precision=30.0,
        crit_rate=25.0,
        dodge_rate=22.0,
        parry_rate=15.0,
        block_rate=25.0,
        defense_level=120,
        block_value=100,
        mobility=85,
        weapons=[beam_rifle, beam_saber]
    )
    
    # === 驾驶员 B: 夏亚·阿兹纳布尔 ===
    pilot_char = Pilot(
        name="夏亚·阿兹纳布尔",
        stat_shooting=90,
        stat_melee=80,
        stat_awakening=85,
        stat_defense=70,
        stat_reaction=92,
        weapon_proficiency=900,
        mecha_proficiency=3800
    )
    
    # 武器: 120mm机炮
    machine_gun = Weapon(
        name="120mm机炮",
        weapon_type=WeaponType.RIFLE,
        power=700,
        en_cost=18,
        range_min=1000,
        range_max=6000
    )
    
    # 武器: 热能斧
    heat_axe = Weapon(
        name="热能斧",
        weapon_type=WeaponType.MELEE,
        power=1100,
        en_cost=20,
        range_min=0,
        range_max=2000
    )
    
    # 武器: 光束火箭炮
    bazooka = Weapon(
        name="光束火箭炮",
        weapon_type=WeaponType.HEAVY,
        power=1400,
        en_cost=35,
        range_min=3000,
        range_max=8000
    )
    
    # 机体 B: MS-06S 扎古II
    zaku = Mecha(
        name="MS-06S 扎古II (指挥官机)",
        pilot=pilot_char,
        max_hp=5500,
        current_hp=5500,
        max_en=180,
        current_en=180,
        hit_rate=18.0,
        precision=28.0,
        crit_rate=30.0,
        dodge_rate=20.0,
        parry_rate=12.0,
        block_rate=28.0,
        defense_level=150,
        block_value=120,
        mobility=90,
        weapons=[machine_gun, heat_axe, bazooka]
    )
    
    return gundam, zaku


# ============================================================================
# 主入口 (Main Entry)
# ============================================================================

if __name__ == "__main__":
    # 创建演示战斗
    mecha_a, mecha_b = create_demo_battle()
    
    # 运行模拟
    simulator = BattleSimulator(mecha_a, mecha_b)
    simulator.run_battle()
    
    print()
    print("=" * 80)
    print("战斗模拟器运行完毕")
    print("=" * 80)
