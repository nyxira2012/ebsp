"""
数值验证木桩模拟
================
用途：
1. 验证数值设计是否合理（伤害输出、防御效果等）
2. 测试技能组合的实际效果
3. 收集战斗统计数据，分析数值变动的影响

使用方法：
    python sim_challenge_boss.py              # 默认 10 轮测试
    python sim_challenge_boss.py --rounds 20 # 指定测试轮数
    python sim_challenge_boss.py --verbose   # 显示详细战斗过程
"""

import sys
import os
import io
import random
import argparse
import json
from typing import List, Dict, Any
from collections import Counter, defaultdict
from dataclasses import dataclass, field

# 确保导入路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Windows UTF-8 支持
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.models import Mecha, Pilot, Weapon, WeaponType, BattleContext, Effect, AttackResult
from src.loader import DataLoader
from src.skills import SkillRegistry, EffectManager, TraitManager
from src.combat.engine import BattleSimulator

# ============================================================================
# 1. 核心技能：死斗 (确保打爆为止)
# ============================================================================

@SkillRegistry.register_callback("cb_test_maintain")
def cb_test_maintain(val, ctx, owner):
    """只要防御方还活着，就继续战斗"""
    if ctx.defender and ctx.defender.is_alive():
        if ctx.round_number < 1000:  # 防止死循环
            return True
    return False

def get_maintain_skill():
    """创建死斗效果"""
    return Effect(
        id="skill_maintain_battle", name="无限延时",
        hook="HOOK_CHECK_MAINTAIN_BATTLE", operation="callback",
        value="cb_test_maintain", duration=-1
    )

# ============================================================================
# 2. Boss 与挑战者配置（集中修改区域）
# ============================================================================

# ==================== Boss 木桩配置 ====================
BOSS_CONFIG = {
    # === 基本信息 ===
    "name": "测试 Boss",

    # === 资源属性 ===
    "hp": 500000,           # Boss 血量（越高战斗越长）
    "en": 400,             # Boss 能量上限

    # === 防御属性 ===
    "defense": 2000,         # 护甲值（影响伤害减伤）
    "mobility": 120,         # 机动性（影响先手判定， dodge_rate = mobility * 0.1）

    # === 战斗属性（百分比）===
    "hit_rate": 20.0,        # 命中率加成
    "precision": 15.0,        # 精准值（削减敌方防御率）
    "crit_rate": 10.0,        # 暴击率加成
    "dodge_rate": None,        # 躲闪率（None 则自动计算为 mobility * 0.1）
    "parry_rate": 15.0,       # 招架率加成
    "block_rate": 15.0,        # 格挡率加成

    # === 武器配置 ===
    "weapon_power_percent": 0.01,  # 武器威力占 Boss HP 的百分比（1% = 5000 伤害）
    "weapon_en_cost": 0,           # 武器 EN 消耗

    # === 驾驶员属性 ===
    "pilot_shooting": 150,     # 射击技能
    "pilot_melee": 150,        # 格斗技能
    "pilot_reaction": 150,     # 反应速度
    "pilot_awakening": 150,     # 感应能力
    "pilot_defense": 150,      # 守备技能
}

# ==================== 挑战者配置 ====================
CHALLENGER_CONFIG = {
    # === 基本信息 ===
    "name": "Challenger Mecha",

    # === 资源属性 ===
    "hp": 10000,            # 挑战者血量
    "en": 500,              # 挑战者能量上限
    "will": 100,            # 初始气力

    # === 战斗属性（百分比）===
    "hit_rate": 50.0,        # 命中率加成
    "precision": 20.0,       # 精准值
    "crit_rate": 20.0,       # 暴击率加成
    "dodge_rate": 20.0,      # 躲闪率加成
    "parry_rate": 15.0,      # 招架率加成
    "block_rate": 15.0,      # 格挡率加成

    # === 防御属性 ===
    "defense_level": 2000,    # 护甲值
    "mobility": 150,          # 机动性
    "block_reduction": 200,   # 格挡减伤值

    # === 武器配置 ===
    "weapon_name": "上帝之雷",
    "weapon_power": 50000,    # 武器威力
    "weapon_en_cost": 0,      # 武器 EN 消耗

    # === 驾驶员属性 ===
    "pilot_shooting": 200,     # 射击技能
    "pilot_melee": 200,        # 格斗技能
    "pilot_reaction": 200,     # 反应速度
    "pilot_awakening": 200,    # 感应能力
    "pilot_defense": 200,     # 守备技能
    "weapon_proficiency": 1000, # 武器熟练度（满值）
    "mecha_proficiency": 4000,  # 机体熟练度（满值）

    # === 技能配置 ===
    "spirit_count": 2,        # 随机抽取的精神数量
    "trait_count": 3,         # 随机抽取的特性数量
}

# ============================================================================
# 3. 统计数据结构
# ============================================================================

@dataclass
class RoundStatistics:
    """单回合统计数据"""
    round_number: int
    distance: int
    first_mover: str
    initiative_reason: str

    # 先手攻击统计
    first_weapon: str
    first_result: AttackResult
    first_damage: int
    first_roll: float
    first_en_cost: int
    first_will_delta: int

    # 后手攻击统计
    second_weapon: str = ""
    second_result: AttackResult = None
    second_damage: int = 0
    second_roll: float = 0.0
    second_en_cost: int = 0
    second_will_delta: int = 0

    # 回合结束状态
    attacker_hp: int = 0
    attacker_en: int = 0
    attacker_will: int = 0
    defender_hp: int = 0
    defender_en: int = 0
    defender_will: int = 0

@dataclass
class BattleStatistics:
    """单场战斗统计数据"""
    battle_id: int
    rounds: int = 0
    winner: str = ""
    end_reason: str = ""

    # 伤害统计
    total_damage_dealt: int = 0
    total_damage_taken: int = 0
    max_single_damage: int = 0
    min_single_damage: int = float('inf')

    # 判定结果统计
    attack_results: Counter = field(default_factory=Counter)

    # 回合统计
    round_stats: List[RoundStatistics] = field(default_factory=list)

    # 技能触发统计
    skills_triggered: Counter = field(default_factory=Counter)

    # 资源消耗
    total_en_consumed: int = 0

    # 气力变化
    will_changes: List[tuple] = field(default_factory=list)

    def finalize(self):
        """计算最终统计数据"""
        if self.min_single_damage == float('inf'):
            self.min_single_damage = 0

# ============================================================================
# 4. 木桩测试器
# ============================================================================

class DummyBossSimulator(BattleSimulator):
    """增强版战斗模拟器，带统计功能"""

    def __init__(self, mecha_a: Mecha, mecha_b: Mecha, battle_id: int = 0, verbose: bool = False):
        super().__init__(mecha_a, mecha_b)
        self.battle_id = battle_id
        self.verbose = verbose
        self.stats = BattleStatistics(battle_id=battle_id)

        # 保存攻击方和防御方的引用
        self.attacker = mecha_a
        self.defender = mecha_b

    def run_battle_with_stats(self) -> BattleStatistics:
        """运行战斗并收集统计数据"""
        if self.verbose:
            print("=" * 80)
            print(f"战斗开始: {self.mecha_a.name} vs {self.mecha_b.name}")
            print("=" * 80)

        max_rounds = SkillRegistry.process_hook(
            "HOOK_MAX_ROUNDS", 4,
            BattleContext(round_number=0, distance=0, attacker=self.mecha_a, defender=self.mecha_b)
        )

        while True:
            # 状态检查
            if not self.mecha_a.is_alive() or not self.mecha_b.is_alive():
                break

            # 回合上限检查
            if self.round_number >= max_rounds:
                ctx = BattleContext(
                    round_number=self.round_number, distance=0,
                    attacker=self.mecha_a, defender=self.mecha_b
                )
                should_maintain = SkillRegistry.process_hook("HOOK_CHECK_MAINTAIN_BATTLE", False, ctx)
                if not should_maintain:
                    break

            self.round_number += 1
            round_stat = self._execute_round_with_stats()
            self.stats.round_stats.append(round_stat)

            if self.verbose:
                print()

        # 战斗结束钩子
        final_ctx = BattleContext(
            round_number=self.round_number, distance=0,
            attacker=self.mecha_a, defender=self.mecha_b
        )
        SkillRegistry.process_hook("HOOK_ON_BATTLE_END", None, final_ctx)

        # 结算
        self._finalize_stats()
        return self.stats

    def _execute_round_with_stats(self) -> RoundStatistics:
        """执行回合并收集统计"""
        round_stat = RoundStatistics(
            round_number=self.round_number,
            distance=0,
            first_mover="",
            initiative_reason="",
            first_weapon="",
            first_result=None,
            first_damage=0,
            first_roll=0.0,
            first_en_cost=0,
            first_will_delta=0
        )

        if self.verbose:
            print(f"{'=' * 80}")
            print(f"ROUND {self.round_number}")
            print(f"{'=' * 80}")

        # 1. 生成距离
        distance = self._generate_distance()
        round_stat.distance = distance

        if self.verbose:
            print(f"📍 交战距离: {distance}m")

        # 2. 先手判定
        first_mover, second_mover, reason = self.initiative_calc.calculate_initiative(
            self.mecha_a, self.mecha_b, self.round_number
        )
        round_stat.first_mover = first_mover.name
        round_stat.initiative_reason = reason.value

        if self.verbose:
            print(f"⚔️  先手方: {first_mover.name} ({reason.value})")
            print()

        # 3. 先攻方攻击
        self._execute_attack_with_stats(first_mover, second_mover, distance, round_stat, is_first=True)

        if not second_mover.is_alive():
            return round_stat

        if self.verbose:
            print()

        # 4. 后攻方反击
        self._execute_attack_with_stats(second_mover, first_mover, distance, round_stat, is_first=False)

        # 5. 回合结束处理
        self.mecha_a.modify_will(1)
        self.mecha_b.modify_will(1)

        ctx = BattleContext(
            round_number=self.round_number, distance=distance,
            attacker=self.mecha_a, defender=self.mecha_b
        )
        SkillRegistry.process_hook("HOOK_ON_TURN_END", None, ctx)

        EffectManager.tick_effects(self.mecha_a)
        EffectManager.tick_effects(self.mecha_b)

        # 记录回合结束状态
        round_stat.attacker_hp = self.mecha_a.current_hp
        round_stat.attacker_en = self.mecha_a.current_en
        round_stat.attacker_will = self.mecha_a.current_will
        round_stat.defender_hp = self.mecha_b.current_hp
        round_stat.defender_en = self.mecha_b.current_en
        round_stat.defender_will = self.mecha_b.current_will

        if self.verbose:
            print()
            print(f"📊 {self.mecha_a.name}: HP={self.mecha_a.current_hp}/{self.mecha_a.max_hp} | "
                  f"EN={self.mecha_a.current_en}/{self.mecha_a.max_en} | "
                  f"气力={self.mecha_a.current_will}")
            print(f"📊 {self.mecha_b.name}: HP={self.mecha_b.current_hp}/{self.mecha_b.max_hp} | "
                  f"EN={self.mecha_b.current_en}/{self.mecha_b.max_en} | "
                  f"气力={self.mecha_b.current_will}")

        return round_stat

    def _execute_attack_with_stats(
        self,
        attacker: Mecha,
        defender: Mecha,
        distance: int,
        round_stat: RoundStatistics,
        is_first: bool
    ):
        """执行攻击并收集统计"""
        # 选择武器
        from src.combat.engine import WeaponSelector
        weapon = WeaponSelector.select_best_weapon(attacker, distance)

        if self.verbose:
            print(f"{'[先攻]' if is_first else '[反击]'} {attacker.name} 使用 【{weapon.name}】"
                  f" (威力:{weapon.power}, EN消耗:{weapon.en_cost})")

        # 创建上下文
        ctx = BattleContext(
            round_number=self.round_number,
            distance=distance,
            attacker=attacker,
            defender=defender,
            weapon=weapon
        )

        # EN消耗计算
        weapon_cost = float(weapon.en_cost)
        weapon_cost = SkillRegistry.process_hook("HOOK_PRE_EN_COST_MULT", weapon_cost, ctx)

        if attacker.current_en < int(weapon_cost):
            if self.verbose:
                print(f"   ❌ EN不足! 无法攻击")
            return

        attacker.consume_en(int(weapon_cost))

        # 圆桌判定
        from src.combat.resolver import AttackTableResolver
        result, damage = AttackTableResolver.resolve_attack(ctx)

        # 应用伤害
        if damage > 0:
            defender.take_damage(damage)

        # 应用气力变化
        attacker_will_delta = ctx.attacker_will_delta
        defender_will_delta = ctx.defender_will_delta
        if attacker_will_delta != 0:
            attacker.modify_will(attacker_will_delta)
        if defender_will_delta != 0:
            defender.modify_will(defender_will_delta)

        # 记录统计数据
        if is_first:
            round_stat.first_weapon = weapon.name
            round_stat.first_result = result
            round_stat.first_damage = damage
            round_stat.first_roll = ctx.roll
            round_stat.first_en_cost = int(weapon_cost)
            round_stat.first_will_delta = attacker_will_delta
        else:
            round_stat.second_weapon = weapon.name
            round_stat.second_result = result
            round_stat.second_damage = damage
            round_stat.second_roll = ctx.roll
            round_stat.second_en_cost = int(weapon_cost)
            round_stat.second_will_delta = attacker_will_delta

        # 更新统计
        self.stats.attack_results[result.name] += 1
        self.stats.total_en_consumed += int(weapon_cost)

        if attacker == self.attacker:
            self.stats.total_damage_dealt += damage
            self.stats.will_changes.append((self.round_number, self.mecha_a.current_will))
        else:
            self.stats.total_damage_taken += damage

        if damage > 0:
            self.stats.max_single_damage = max(self.stats.max_single_damage, damage)
            self.stats.min_single_damage = min(self.stats.min_single_damage, damage)

        # 技能钩子
        if damage > 0:
            SkillRegistry.process_hook("HOOK_ON_DAMAGE_DEALT", damage, ctx)
        if not defender.is_alive():
            SkillRegistry.process_hook("HOOK_ON_KILL", None, ctx)
        SkillRegistry.process_hook("HOOK_ON_ATTACK_END", None, ctx)

        if self.verbose:
            result_emoji = {
                AttackResult.MISS: "❌",
                AttackResult.DODGE: "💨",
                AttackResult.PARRY: "⚔️",
                AttackResult.BLOCK: "🛡️",
                AttackResult.HIT: "💥",
                AttackResult.CRIT: "💥✨"
            }
            print(f"   {result_emoji.get(result, '❓')} {result.value}! "
                  f"Roll点: {ctx.roll:.1f} | 伤害: {damage} | "
                  f"气力变化: ⚡{attacker.name}({attacker_will_delta:+d}) "
                  f"⚡{defender.name}({defender_will_delta:+d})")

    def _finalize_stats(self):
        """结算战斗统计"""
        self.stats.rounds = self.round_number

        if not self.mecha_a.is_alive():
            self.stats.winner = self.mecha_b.name
            self.stats.end_reason = "击破"
        elif not self.mecha_b.is_alive():
            self.stats.winner = self.mecha_a.name
            self.stats.end_reason = "击破"
        else:
            hp_a = self.mecha_a.get_hp_percentage()
            hp_b = self.mecha_b.get_hp_percentage()
            if hp_a > hp_b:
                self.stats.winner = self.mecha_a.name
                self.stats.end_reason = "判定胜"
            elif hp_b > hp_a:
                self.stats.winner = self.mecha_b.name
                self.stats.end_reason = "判定胜"
            else:
                self.stats.winner = "平局"
                self.stats.end_reason = "平局"

        self.stats.finalize()


class BossChallenger:
    """Boss 木桩测试器"""

    def __init__(self, verbose: bool = False):
        self.loader = DataLoader()
        self.loader.load_all()

        self.verbose = verbose

        # 加载所有技能 ID
        with open("data/skills.json", "r", encoding="utf-8") as f:
            self.all_skill_ids = list(json.load(f).keys())

        self.spirits = [s for s in self.all_skill_ids if s.startswith("spirit_")]
        self.traits = [t for t in self.all_skill_ids if t.startswith("trait_")]

    def create_boss(self) -> Mecha:
        """创建 Boss 木桩（使用 BOSS_CONFIG 配置）"""
        # 创建驾驶员
        pilot = Pilot(
            id="boss_pilot", name="Boss Pilot", portrait_id="boss_portrait",
            stat_shooting=BOSS_CONFIG['pilot_shooting'],
            stat_melee=BOSS_CONFIG['pilot_melee'],
            stat_reaction=BOSS_CONFIG['pilot_reaction'],
            stat_awakening=BOSS_CONFIG['pilot_awakening'],
            stat_defense=BOSS_CONFIG['pilot_defense']
        )

        # 计算躲闪率（如果配置为 None，则自动计算为 mobility * 0.1）
        dodge_rate = BOSS_CONFIG['dodge_rate']
        if dodge_rate is None:
            dodge_rate = BOSS_CONFIG['mobility'] * 0.1

        # 创建机体
        boss = Mecha(
            id="boss", name=BOSS_CONFIG['name'],
            pilot=pilot,
            max_hp=BOSS_CONFIG['hp'],
            current_hp=BOSS_CONFIG['hp'],
            max_en=BOSS_CONFIG['en'],
            current_en=BOSS_CONFIG['en'],
            hit_rate=BOSS_CONFIG['hit_rate'],
            precision=BOSS_CONFIG['precision'],
            crit_rate=BOSS_CONFIG['crit_rate'],
            dodge_rate=dodge_rate,
            parry_rate=BOSS_CONFIG['parry_rate'],
            block_rate=BOSS_CONFIG['block_rate'],
            defense_level=BOSS_CONFIG['defense'],
            mobility=BOSS_CONFIG['mobility']
        )

        # Boss 武器
        boss.weapons = [
            Weapon(
                uid="boss_weapon_uid", definition_id="boss_weapon", name="Boss Attack",
                type=WeaponType.SPECIAL,
                final_power=int(BOSS_CONFIG['hp'] * BOSS_CONFIG['weapon_power_percent']),
                en_cost=BOSS_CONFIG['weapon_en_cost'],
                range_min=0, range_max=10000,
                will_req=0, anim_id="boss_anim"
            )
        ]

        return boss

    def create_challenger(self) -> Mecha:
        """创建挑战者机体（使用 CHALLENGER_CONFIG 配置）"""
        # 创建驾驶员
        pilot = Pilot(
            id="challenger_pilot", name="Challenger", portrait_id="challenger_portrait",
            stat_shooting=CHALLENGER_CONFIG['pilot_shooting'],
            stat_melee=CHALLENGER_CONFIG['pilot_melee'],
            stat_reaction=CHALLENGER_CONFIG['pilot_reaction'],
            stat_awakening=CHALLENGER_CONFIG['pilot_awakening'],
            stat_defense=CHALLENGER_CONFIG['pilot_defense'],
            weapon_proficiency=CHALLENGER_CONFIG['weapon_proficiency'],
            mecha_proficiency=CHALLENGER_CONFIG['mecha_proficiency']
        )

        # 创建武器
        god_weapon = Weapon(
            uid="w_god_uid", definition_id="w_god", name=CHALLENGER_CONFIG['weapon_name'],
            type=WeaponType.SPECIAL,
            final_power=CHALLENGER_CONFIG['weapon_power'],
            en_cost=CHALLENGER_CONFIG['weapon_en_cost'],
            range_min=0, range_max=10000,
            will_req=0, anim_id="god_anim"
        )

        # 创建机体
        attacker = Mecha(
            instance_id="challenger", mecha_name=CHALLENGER_CONFIG['name'],
            main_portrait="challenger_portrait", model_asset="challenger_model",

            final_max_hp=CHALLENGER_CONFIG['hp'], current_hp=CHALLENGER_CONFIG['hp'],
            final_max_en=CHALLENGER_CONFIG['en'], current_en=CHALLENGER_CONFIG['en'],
            current_will=CHALLENGER_CONFIG['will'],

            final_armor=CHALLENGER_CONFIG['defense_level'], final_mobility=CHALLENGER_CONFIG['mobility'],

            final_hit=CHALLENGER_CONFIG['hit_rate'],
            final_precision=CHALLENGER_CONFIG['precision'],
            final_crit=CHALLENGER_CONFIG['crit_rate'],
            final_dodge=CHALLENGER_CONFIG['dodge_rate'],
            final_parry=CHALLENGER_CONFIG['parry_rate'],
            final_block=CHALLENGER_CONFIG['block_rate'],
            block_reduction=CHALLENGER_CONFIG['block_reduction'],

            weapons=[god_weapon],
            pilot_stats_backup={
                'stat_shooting': CHALLENGER_CONFIG['pilot_shooting'],
                'stat_melee': CHALLENGER_CONFIG['pilot_melee'],
                'stat_awakening': CHALLENGER_CONFIG['pilot_awakening'],
                'stat_defense': CHALLENGER_CONFIG['pilot_defense'],
                'stat_reaction': CHALLENGER_CONFIG['pilot_reaction'],
                'weapon_proficiency': CHALLENGER_CONFIG['weapon_proficiency'],
                'mecha_proficiency': CHALLENGER_CONFIG['mecha_proficiency']
            },
            skills=[], effects=[]
        )

        return attacker

    def apply_random_skills(self, mecha: Mecha):
        """应用随机技能组合（使用 CHALLENGER_CONFIG 配置）"""
        spirit_count = CHALLENGER_CONFIG['spirit_count']
        trait_count = CHALLENGER_CONFIG['trait_count']

        selected_spirits = random.sample(self.spirits, min(spirit_count, len(self.spirits)))
        selected_traits = random.sample(self.traits, min(trait_count, len(self.traits)))

        if self.verbose:
            print(f"\n随机抽取的精神 ({len(selected_spirits)}):")
            for s in selected_spirits:
                print(f"  - {s}")
            print(f"\n随机抽取的特性 ({len(selected_traits)}):")
            for t in selected_traits:
                print(f"  - {t}")

        # 应用精神和特性
        for s_id in selected_spirits:
            EffectManager.add_effect(mecha, s_id, duration=100)
        mecha.traits = selected_traits
        TraitManager.apply_traits(mecha)

        return selected_spirits + selected_traits

    def run_challenge(self, round_idx: int) -> BattleStatistics:
        """执行一轮测试"""
        if self.verbose:
            print("\n" + "="*70)
            print(f"【第 {round_idx} 轮测试】")
            print("="*70)
            print(f"\nBoss HP: {BOSS_CONFIG['hp']:,}")
            print(f"Boss 防御: {BOSS_CONFIG['defense']}")
            print(f"Boss 机动: {BOSS_CONFIG['mobility']}")
            print(f"Boss EN: {BOSS_CONFIG['en']}")

        # 初始化
        attacker = self.create_challenger()
        boss = self.create_boss()

        # 应用随机技能
        skills_applied = self.apply_random_skills(attacker)

        # 强制注入死斗技能
        attacker.effects.append(get_maintain_skill())

        if self.verbose:
            print(f"\n--- 战斗开始: {attacker.name} vs {boss.name} ---")
            print(f"挑战者 HP: {attacker.current_hp:,} | Boss HP: {boss.current_hp:,}")

        # 执行战斗并收集统计
        sim = DummyBossSimulator(attacker, boss, battle_id=round_idx, verbose=self.verbose)
        stats = sim.run_battle_with_stats()

        # 记录应用的技能
        for skill_id in skills_applied:
            stats.skills_triggered[skill_id] += 1

        if self.verbose:
            print(f"\n{'─'*70}")
            print(f"【测试结束】")
            print(f"{'─'*70}")
            print(f"最终回合数: {stats.rounds}")
            print(f"获胜方: {stats.winner} ({stats.end_reason})")
            print(f"挑战者剩余 HP: {attacker.current_hp:,} ({attacker.get_hp_percentage():.1f}%)")
            print(f"Boss 剩余 HP: {boss.current_hp:,} ({boss.get_hp_percentage():.1f}%)")

        return stats


# ============================================================================
# 5. 统计分析
# ============================================================================

def print_statistics(all_stats: List[BattleStatistics]):
    """打印统计分析结果"""

    print("\n" + "="*80)
    print("【统计分析报告】")
    print("="*80)

    # 基础统计
    total_battles = len(all_stats)
    wins = sum(1 for s in all_stats if s.winner == "Challenger Mecha")
    losses = sum(1 for s in all_stats if s.winner == BOSS_CONFIG['name'])

    avg_rounds = sum(s.rounds for s in all_stats) / total_battles
    min_rounds = min(s.rounds for s in all_stats)
    max_rounds = max(s.rounds for s in all_stats)

    print(f"\n【基础数据】")
    print(f"测试次数: {total_battles}")
    print(f"胜利次数: {wins} ({wins/total_battles*100:.1f}%)")
    print(f"失败次数: {losses} ({losses/total_battles*100:.1f}%)")
    print(f"平均回合数: {avg_rounds:.1f} (最短: {min_rounds}, 最长: {max_rounds})")

    # 伤害统计
    avg_damage_dealt = sum(s.total_damage_dealt for s in all_stats) / total_battles
    max_damage_dealt = max(s.total_damage_dealt for s in all_stats)
    min_damage_dealt = min(s.total_damage_dealt for s in all_stats)

    avg_max_single = sum(s.max_single_damage for s in all_stats) / total_battles
    avg_min_single = sum(s.min_single_damage for s in all_stats) / total_battles

    print(f"\n【伤害统计】")
    print(f"场均总输出: {avg_damage_dealt:,.0f} (最高: {max_damage_dealt:,}, 最低: {min_damage_dealt:,})")
    print(f"场均最大单次伤害: {avg_max_single:,.0f}")
    print(f"场均最小单次伤害: {avg_min_single:,.0f}")

    # 判定结果分布
    total_attacks = sum(sum(s.attack_results.values()) for s in all_stats)
    all_results = Counter()
    for s in all_stats:
        all_results.update(s.attack_results)

    print(f"\n【判定结果分布】(总计 {total_attacks} 次攻击)")
    print(f"{'判定类型':<12} | {'次数':<8} | {'百分比':<8} | {'说明'}")
    print(f"{'-'*70}")

    result_descriptions = {
        "MISS": "未命中",
        "DODGE": "闪避",
        "PARRY": "招架",
        "BLOCK": "格挡",
        "CRIT": "暴击",
        "HIT": "普通命中"
    }

    for result_name in ["MISS", "DODGE", "PARRY", "BLOCK", "CRIT", "HIT"]:
        count = all_results.get(result_name, 0)
        percentage = count / total_attacks * 100 if total_attacks > 0 else 0
        description = result_descriptions.get(result_name, "")
        print(f"{result_name:<12} | {count:<8} | {percentage:>6.2f}% | {description}")

    # EN消耗统计
    avg_en_consumed = sum(s.total_en_consumed for s in all_stats) / total_battles
    avg_en_per_round = avg_en_consumed / avg_rounds if avg_rounds > 0 else 0

    print(f"\n【资源消耗】")
    print(f"场均EN消耗: {avg_en_consumed:,.1f}")
    print(f"平均每回合EN消耗: {avg_en_per_round:.1f}")

    # 技能触发统计（如果有）
    all_skills = Counter()
    for s in all_stats:
        all_skills.update(s.skills_triggered)

    if all_skills:
        print(f"\n【技能应用情况】(共 {len(all_skills)} 个不同技能)")
        top_skills = all_skills.most_common(10)
        for skill_id, count in top_skills:
            print(f"  {skill_id}: {count} 次")

    print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(
        description="数值验证木桩模拟",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python sim_challenge_boss.py              # 运行 10 轮测试（默认）
  python sim_challenge_boss.py --rounds 20 # 运行 20 轮测试
  python sim_challenge_boss.py --verbose   # 显示详细战斗过程
        """
    )

    parser.add_argument(
        "--rounds", "-r",
        type=int,
        default=10,
        help="测试轮数 (默认: 10)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细战斗过程"
    )

    args = parser.parse_args()

    challenger = BossChallenger(verbose=args.verbose)

    # 打印配置信息
    print("\n" + "="*80)
    print("【木桩测试配置】")
    print("="*80)

    print(f"\n【Boss 配置】({BOSS_CONFIG['name']})")
    print(f"  HP: {BOSS_CONFIG['hp']:,}")
    print(f"  EN: {BOSS_CONFIG['en']}")
    print(f"  护甲: {BOSS_CONFIG['defense']}")
    print(f"  机动: {BOSS_CONFIG['mobility']}")
    print(f"  命中/精准/暴击: {BOSS_CONFIG['hit_rate']}% / {BOSS_CONFIG['precision']}% / {BOSS_CONFIG['crit_rate']}%")
    dodge_rate = BOSS_CONFIG['dodge_rate'] if BOSS_CONFIG['dodge_rate'] is not None else BOSS_CONFIG['mobility'] * 0.1
    print(f"  躲闪/招架/格挡: {dodge_rate}% / {BOSS_CONFIG['parry_rate']}% / {BOSS_CONFIG['block_rate']}%")

    print(f"\n【挑战者配置】({CHALLENGER_CONFIG['name']})")
    print(f"  HP: {CHALLENGER_CONFIG['hp']:,}")
    print(f"  EN: {CHALLENGER_CONFIG['en']}")
    print(f"  初始气力: {CHALLENGER_CONFIG['will']}")
    print(f"  护甲/机动: {CHALLENGER_CONFIG['defense_level']} / {CHALLENGER_CONFIG['mobility']}")
    print(f"  命中/精准/暴击: {CHALLENGER_CONFIG['hit_rate']}% / {CHALLENGER_CONFIG['precision']}% / {CHALLENGER_CONFIG['crit_rate']}%")
    print(f"  躲闪/招架/格挡: {CHALLENGER_CONFIG['dodge_rate']}% / {CHALLENGER_CONFIG['parry_rate']}% / {CHALLENGER_CONFIG['block_rate']}%")
    print(f"  武器: {CHALLENGER_CONFIG['weapon_name']} (威力: {CHALLENGER_CONFIG['weapon_power']:,})")
    print(f"  随机技能: {CHALLENGER_CONFIG['spirit_count']} 精神 + {CHALLENGER_CONFIG['trait_count']} 特性")

    print(f"\n【测试设置】")
    print(f"  测试轮数: {args.rounds}")
    print(f"  详细输出: {'是' if args.verbose else '否'}")

    # 运行测试
    all_stats: List[BattleStatistics] = []
    for i in range(1, args.rounds + 1):
        stats = challenger.run_challenge(i)
        all_stats.append(stats)

        # 回合间暂停（仅在交互模式且非详细输出时）
        if not args.verbose and i < args.rounds and sys.stdin.isatty():
            try:
                input(f"\n第 {i}/{args.rounds} 轮完成，按 Enter 继续...")
            except (EOFError, KeyboardInterrupt):
                pass

    # 打印统计分析
    print_statistics(all_stats)


if __name__ == "__main__":
    main()
