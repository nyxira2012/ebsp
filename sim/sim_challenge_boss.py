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
from src.skills import SkillRegistry, EffectManager, TraitManager
from src.combat.engine import BattleSimulator
from src.loader import DataLoader
from src.factory import MechaFactory

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
    "defense": 1000,         # 护甲值（影响伤害减伤）
    "mobility": 120,         # 机动性（影响先手判定， dodge_rate = mobility * 0.1）

    # === 战斗属性（百分比）===
    "hit_rate": 20.0,        # 命中率加成
    "precision": 15.0,        # 精准值（削减敌方防御率）
    "crit_rate": 10.0,        # 暴击率加成
    "dodge_rate": None,        # 躲闪率（None 则自动计算为 mobility * 0.1）
    "parry_rate": 15.0,       # 招架率加成
    "block_rate": 15.0,        # 格挡率加成

    # === 武器配置 ===
    "weapon_power_percent": 0.0008,  # 武器威力占 Boss HP 的百分比
    "weapon_en_cost": 1,           # 武器 EN 消耗

    # === 驾驶员属性 ===
    "pilot_shooting": 150,     # 射击技能
    "pilot_melee": 150,        # 格斗技能
    "pilot_reaction": 150,     # 反应速度
    "pilot_awakening": 150,     # 感应能力
    "pilot_defense": 150,      # 守备技能

    # === 熟练度 ===
    "weapon_proficiency": 1000,  # 武器熟练度（满值）
    "mecha_proficiency": 4000,   # 机体熟练度（满值）
}

# ==================== 挑战者配置 ====================
CHALLENGER_CONFIG = {
    # === 引用data中的配置 ===
    "mecha_id": "mech_rx78",     # 机体配置ID
    "pilot_id": "pilot_amuro",   # 驾驶员配置ID

    # === 可选：覆盖武器列表（为空则使用机体的fixed_weapons）===
    "weapon_ids": [],  # 留空使用机体自带武器，或指定如 ["wpn_beam_rifle", "wpn_beam_saber"]

    # === 可选：安装设备列表（最多3个设备槽）===
    # 示例：安装增压器、乔巴姆装甲、磁气覆膜
    "equip_ids": ["e_booster", "e_chobham_armor", "e_magnetron_coating"],

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
    second_result: AttackResult | None = None
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
    min_single_damage: float = float('inf')
    damage_distribution: List[int] = field(default_factory=list)  # 挑战者所有伤害值

    # 判定结果统计（分开统计）
    attack_results: Counter = field(default_factory=Counter)  # 总计
    challenger_attack_results: Counter = field(default_factory=Counter)  # 挑战者
    boss_attack_results: Counter = field(default_factory=Counter)  # Boss

    # 回合统计
    round_stats: List[RoundStatistics] = field(default_factory=list)

    # 技能统计（新设计）
    skills_applied: List[str] = field(default_factory=list)  # 本场应用的技能列表
    skill_trigger_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)  # {skill_id: {attempts, success}}
    total_battles_count: int = 0  # 总场数，用于计算应用率

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

    def run_battle_with_stats(self) -> BattleStatistics:
        """运行战斗并收集统计数据"""
        if self.verbose:
            print("=" * 80)
            print(f"战斗开始: {self.mecha_a.name} vs {self.mecha_b.name}")
            print("=" * 80)

        max_rounds = SkillRegistry.process_hook(
            "HOOK_MAX_ROUNDS", 4,
            BattleContext(round_number=0, distance=0, mecha_a=self.mecha_a, mecha_b=self.mecha_b)
        )

        while True:
            # 状态检查
            if not self.mecha_a.is_alive() or not self.mecha_b.is_alive():
                break

            # 回合上限检查
            if self.round_number >= max_rounds:
                ctx = BattleContext(
                    round_number=self.round_number, distance=0,
                    mecha_a=self.mecha_a, mecha_b=self.mecha_b
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
            mecha_a=self.mecha_a, mecha_b=self.mecha_b
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
            first_result=AttackResult.MISS,  # 默认值，稍后会被覆盖
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
            mecha_a=self.mecha_a, mecha_b=self.mecha_b
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
            print(f"📊 {self.mecha_a.name}: HP={self.mecha_a.current_hp}/{self.mecha_a.final_max_hp} | "
                  f"EN={self.mecha_a.current_en}/{self.mecha_a.final_max_en} | "
                  f"气力={self.mecha_a.current_will}")
            print(f"📊 {self.mecha_b.name}: HP={self.mecha_b.current_hp}/{self.mecha_b.final_max_hp} | "
                  f"EN={self.mecha_b.current_en}/{self.mecha_b.final_max_en} | "
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
            mecha_a=attacker,
            mecha_b=defender,
            weapon=weapon
        )

        # EN消耗计算
        weapon_cost = float(weapon.en_cost)
        weapon_cost = SkillRegistry.process_hook("HOOK_PRE_EN_COST_MULT", weapon_cost, ctx)

        final_en_cost = int(weapon_cost)
        if attacker.current_en < final_en_cost:
            if self.verbose:
                print(f"   ❌ EN不足! 无法攻击")
            return

        attacker.consume_en(final_en_cost)

        # 圆桌判定
        from src.combat.resolver import AttackTableResolver
        result, damage = AttackTableResolver.resolve_attack(ctx)

        # 应用伤害
        if damage > 0:
            defender.take_damage(damage)

        # 应用气力变化
        attacker_will_delta = ctx.current_attacker_will_delta
        defender_will_delta = ctx.current_defender_will_delta
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

        # 根据攻击者角色分别统计判定结果
        # 判断是挑战者还是Boss（通过比较instance_id或引用）
        is_challenger = (attacker == self.mecha_a)
        is_boss = (attacker == self.mecha_b)

        if is_challenger:
            self.stats.challenger_attack_results[result.name] += 1
            # 记录挑战者的伤害值（用于伤害分布统计）
            self.stats.damage_distribution.append(damage)
        elif is_boss:
            self.stats.boss_attack_results[result.name] += 1

        if attacker == self.mecha_a:
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
        self.verbose = verbose
        # 从上级目录加载数据（sim目录的父目录）
        import os
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        self.loader = DataLoader(data_dir=data_dir)
        self.loader.load_all()

        # 加载所有技能数据
        skills_path = os.path.join(data_dir, "skills.json")
        with open(skills_path, "r", encoding="utf-8") as f:
            self.all_skills_data = json.load(f)

        self.all_skill_ids = list(self.all_skills_data.keys())
        self.spirits = [s for s in self.all_skill_ids if s.startswith("spirit_")]
        self.traits = [t for t in self.all_skill_ids if t.startswith("trait_")]

        # 缓存挑战者名称（用于统计）
        self.challenger_name = None

    def get_skill_name(self, skill_id: str) -> str:
        """获取技能的中文名称"""
        if skill_id in self.all_skills_data:
            return self.all_skills_data[skill_id].get("name", skill_id)
        return skill_id

    def get_skill_info(self, skill_id: str) -> dict:
        """获取技能的详细信息（包括描述、概率等）"""
        if skill_id in self.all_skills_data:
            effects_list = self.all_skills_data[skill_id]
            if isinstance(effects_list, list) and len(effects_list) > 0:
                effect = effects_list[0]
                return {
                    'name': effect.get("name", skill_id),
                    'description': effect.get("description", ""),
                    'operation': effect.get("operation", ""),
                    'value': effect.get("value", ""),
                    'hook': effect.get("hook", "")
                }
        return {
            'name': skill_id,
            'description': "",
            'operation': "",
            'value': "",
            'hook': ""
        }

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
            instance_id="boss", mecha_name=BOSS_CONFIG['name'],
            final_max_hp=BOSS_CONFIG['hp'],
            current_hp=BOSS_CONFIG['hp'],
            final_max_en=BOSS_CONFIG['en'],
            current_en=BOSS_CONFIG['en'],
            final_hit=BOSS_CONFIG['hit_rate'],
            final_precision=BOSS_CONFIG['precision'],
            final_crit=BOSS_CONFIG['crit_rate'],
            final_dodge=dodge_rate,
            final_parry=BOSS_CONFIG['parry_rate'],
            final_block=BOSS_CONFIG['block_rate'],
            final_armor=BOSS_CONFIG['defense'],
            final_mobility=BOSS_CONFIG['mobility'],
            pilot_stats_backup={
                'stat_shooting': BOSS_CONFIG['pilot_shooting'],
                'stat_melee': BOSS_CONFIG['pilot_melee'],
                'stat_awakening': BOSS_CONFIG['pilot_awakening'],
                'stat_defense': BOSS_CONFIG['pilot_defense'],
                'stat_reaction': BOSS_CONFIG['pilot_reaction'],
                'weapon_proficiency': BOSS_CONFIG['weapon_proficiency'],
                'mecha_proficiency': BOSS_CONFIG['mecha_proficiency'],
            }
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
        """创建挑战者机体（使用data中的配置）"""
        # 使用MechaFactory从配置创建机体
        mecha_config = self.loader.get_mecha_config(CHALLENGER_CONFIG['mecha_id'])
        pilot_config = self.loader.get_pilot_config(CHALLENGER_CONFIG['pilot_id'])

        # 加载设备配置
        equip_configs = []
        if CHALLENGER_CONFIG['equip_ids']:
            for equip_id in CHALLENGER_CONFIG['equip_ids']:
                if equip_id in self.loader.equipments:
                    equip_configs.append(self.loader.equipments[equip_id])
                else:
                    print(f"[警告] 设备 {equip_id} 不存在于配置中，已跳过")

        challenger = MechaFactory.create_mecha_snapshot(
            mecha_config,
            pilot_conf=pilot_config,
            equipments=equip_configs if equip_configs else None,
            weapon_configs=self.loader.equipments
        )

        # 缓存挑战者名称
        self.challenger_name = challenger.name

        # 如果配置了自定义武器列表，替换机体武器
        if CHALLENGER_CONFIG['weapon_ids']:
            new_weapons = []
            for weapon_id in CHALLENGER_CONFIG['weapon_ids']:
                weapon_config = self.loader.get_equipment_config(weapon_id)
                weapon_snapshot = MechaFactory.create_weapon_snapshot(weapon_config)
                new_weapons.append(weapon_snapshot)
            challenger.weapons = new_weapons

        return challenger

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
        mecha.skills = selected_traits
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

        # 清空EventManager统计（避免累积多场战斗的数据）
        from src.skill_system.event_manager import EventManager
        EventManager.clear_statistics()

        # 执行战斗并收集统计（不抑制输出，让技能触发日志显示）
        sim = DummyBossSimulator(attacker, boss, battle_id=round_idx, verbose=self.verbose)
        stats = sim.run_battle_with_stats()

        # 记录本场应用的技能列表
        stats.skills_applied = skills_applied

        # 从EventManager获取技能触发统计
        all_skill_stats = EventManager.get_statistics()

        # 打印调试信息（仅在verbose模式下）
        if self.verbose and all_skill_stats:
            print(f"\n[DEBUG] 技能触发统计 (本场战斗):")
            for skill_id, trigger_data in all_skill_stats.items():
                attempts = trigger_data.get("attempts", 0)
                success = trigger_data.get("success", 0)
                skill_name = self.get_skill_name(skill_id)
                print(f"  {skill_name}({skill_id}): 尝试 {attempts} 次, 成功 {success} 次")

        stats.skill_trigger_stats = all_skill_stats

        if self.verbose:
            print(f"\n{'─'*70}")
            print(f"【测试结束】")
            print(f"{'─'*70}")
            print(f"最终回合数: {stats.rounds}")
            print(f"获胜方: {stats.winner} ({stats.end_reason})")
            print(f"挑战者剩余 HP: {attacker.current_hp:,} ({attacker.get_hp_percentage():.1f}%)")
            print(f"Boss 剩余 HP: {boss.current_hp:,} ({boss.get_hp_percentage():.1f}%)")
        else:
            # 非verbose模式下显示简短进度
            print(f"  第 {round_idx} 轮完成: {stats.rounds} 回合, 获胜者: {stats.winner}")

        return stats


# ============================================================================
# 5. 统计分析
# ============================================================================

def print_statistics(all_stats: List[BattleStatistics], challenger: Mecha | None = None, challenger_obj: Any = None):
    """打印统计分析结果

    Args:
        all_stats: 所有战斗的统计数据
        challenger: 挑战者机体对象（用于获取HP和武器威力）
        challenger_obj: BossChallenger对象（用于获取技能信息）
    """

    print("\n" + "="*80)
    print("【统计分析报告】")
    print("="*80)

    # 推断挑战者名称（从第一场统计的winner中获取）
    challenger_name = None
    if all_stats and all_stats[0].winner and all_stats[0].winner != BOSS_CONFIG['name']:
        challenger_name = all_stats[0].winner

    # 基础统计
    total_battles = len(all_stats)
    wins = sum(1 for s in all_stats if s.winner == challenger_name)
    losses = sum(1 for s in all_stats if s.winner == BOSS_CONFIG['name'])

    avg_rounds = sum(s.rounds for s in all_stats) / total_battles
    min_rounds = min(s.rounds for s in all_stats)
    max_rounds = max(s.rounds for s in all_stats)

    print(f"\n【基础数据】")
    print(f"测试次数: {total_battles}")
    print(f"胜利次数: {wins} ({wins/total_battles*100:.1f}%)")
    print(f"失败次数: {losses} ({losses/total_battles*100:.1f}%)")
    print(f"平均回合数: {avg_rounds:.1f} (最短: {min_rounds}, 最长: {max_rounds})")

    # 回合数分布统计
    from collections import defaultdict as dd
    round_ranges = dd(int)
    for s in all_stats:
        if s.rounds <= 20:
            round_ranges["1-20回"] += 1
        elif s.rounds <= 40:
            round_ranges["21-40回"] += 1
        elif s.rounds <= 60:
            round_ranges["41-60回"] += 1
        elif s.rounds <= 80:
            round_ranges["61-80回"] += 1
        else:
            round_ranges["81+回"] += 1

    print(f"\n回合数分布:")
    for range_name, count in sorted(round_ranges.items()):
        percentage = count / total_battles * 100
        print(f"  {range_name}: {count} 场 ({percentage:.1f}%)")

    # 生存统计（仅统计胜利的战斗）
    if wins > 0:
        win_stats = [s for s in all_stats if s.winner == challenger_name]
        # 从最后一回合的统计中获取HP
        final_hp_list = []
        for s in win_stats:
            if s.round_stats:
                final_hp_list.append(s.round_stats[-1].attacker_hp)

        if final_hp_list:
            avg_hp_remaining = sum(final_hp_list) / len(final_hp_list)
            challenger_max_hp = challenger.final_max_hp if challenger else 5000
            avg_hp_percentage = (avg_hp_remaining / challenger_max_hp) * 100
            print(f"\n胜利时生存情况:")
            print(f"  平均剩余HP: {avg_hp_remaining:,.0f} ({avg_hp_percentage:.1f}%)")
            print(f"  最惨胜HP: {min(final_hp_list):,.0f}")
            print(f"  最好胜HP: {max(final_hp_list):,.0f}")

    # 判定结果分布（分别统计）- 提前计算用于伤害效率分析
    total_attacks = sum(sum(s.attack_results.values()) for s in all_stats)

    # 挑战者判定结果
    challenger_attacks = sum(sum(s.challenger_attack_results.values()) for s in all_stats)
    challenger_results = Counter()
    for s in all_stats:
        challenger_results.update(s.challenger_attack_results)

    # Boss判定结果
    boss_attacks = sum(sum(s.boss_attack_results.values()) for s in all_stats)
    boss_results = Counter()
    for s in all_stats:
        boss_results.update(s.boss_attack_results)

    # 伤害统计
    avg_damage_dealt = sum(s.total_damage_dealt for s in all_stats) / total_battles
    max_damage_dealt = max(s.total_damage_dealt for s in all_stats)
    min_damage_dealt = min(s.total_damage_dealt for s in all_stats)

    avg_max_single = sum(s.max_single_damage for s in all_stats) / total_battles
    avg_min_single = sum(s.min_single_damage for s in all_stats) / total_battles

    # 提前计算 avg_dpr，供后续使用
    avg_rounds = sum(s.rounds for s in all_stats) / total_battles
    avg_dpr = avg_damage_dealt / avg_rounds if avg_rounds > 0 else 0

    print(f"\n【伤害统计】")
    print(f"场均总输出: {avg_damage_dealt:,.0f} (最高: {max_damage_dealt:,}, 最低: {min_damage_dealt:,})")
    print(f"场均最大单次伤害: {avg_max_single:,.0f}")
    print(f"场均最小单次伤害: {avg_min_single:,.0f}")

    # 挑战者伤害分布统计
    all_damages = []
    for s in all_stats:
        all_damages.extend(s.damage_distribution)

    if all_damages:
        all_damages.sort()
        total_hits_count = len(all_damages)

        print(f"\n【挑战者伤害分布】(总计 {total_hits_count} 次命中)")

        # 分区间统计
        max_damage = max(all_damages) if all_damages else 0
        min_damage = min(all_damages) if all_damages else 0
        avg_damage = sum(all_damages) / total_hits_count if total_hits_count > 0 else 0

        print(f"  伤害范围: {min_damage:,.0f} - {max_damage:,.0f}")
        print(f"  平均伤害: {avg_damage:,.1f}")

        # 计算分位数
        if total_hits_count >= 4:
            p25 = all_damages[int(total_hits_count * 0.25)]
            p50 = all_damages[int(total_hits_count * 0.50)]  # 中位数
            p75 = all_damages[int(total_hits_count * 0.75)]
            print(f"  分位数: P25={p25:,.0f}, P50={p50:,.0f}, P75={p75:,.0f}")

        # 分区间统计
        damage_ranges = {
            "0-1000": 0,
            "1000-2000": 0,
            "2000-3000": 0,
            "3000-4000": 0,
            "4000-5000": 0,
            "5000-6000": 0,
            "6000-7000": 0,
            "7000-8000": 0,
            "8000+": 0
        }

        for dmg in all_damages:
            if dmg < 1000:
                damage_ranges["0-1000"] += 1
            elif dmg < 2000:
                damage_ranges["1000-2000"] += 1
            elif dmg < 3000:
                damage_ranges["2000-3000"] += 1
            elif dmg < 4000:
                damage_ranges["3000-4000"] += 1
            elif dmg < 5000:
                damage_ranges["4000-5000"] += 1
            elif dmg < 6000:
                damage_ranges["5000-6000"] += 1
            elif dmg < 7000:
                damage_ranges["6000-7000"] += 1
            elif dmg < 8000:
                damage_ranges["7000-8000"] += 1
            else:
                damage_ranges["8000+"] += 1

        print(f"\n  伤害区间分布:")
        # 总是显示所有区间，即使次数为0，便于验证数据一致性
        for range_name in ["0-1000", "1000-2000", "2000-3000", "3000-4000",
                           "4000-5000", "5000-6000", "6000-7000", "7000-8000", "8000+"]:
            count = damage_ranges.get(range_name, 0)
            percentage = count / total_hits_count * 100
            bar_length = int(percentage / 2)  # 每2%一个字符
            bar = "█" * bar_length
            print(f"    {range_name:<10} {count:>4} 次 ({percentage:>5.1f}%) {bar}")

    # ========================================================================
    # 挑战者攻击情况分析
    # ========================================================================
    print("\n" + "="*80)
    print("【挑战者攻击情况分析】")
    print("="*80)

    # 伤害统计
    avg_damage_dealt = sum(s.total_damage_dealt for s in all_stats) / total_battles
    max_damage_dealt = max(s.total_damage_dealt for s in all_stats)
    min_damage_dealt = min(s.total_damage_dealt for s in all_stats)

    avg_max_single = sum(s.max_single_damage for s in all_stats) / total_battles
    avg_min_single = sum(s.min_single_damage for s in all_stats) / total_battles

    # 提前计算 avg_dpr，供后续使用
    avg_dpr = avg_damage_dealt / avg_rounds if avg_rounds > 0 else 0

    print(f"\n【伤害输出】")
    print(f"场均总输出: {avg_damage_dealt:,.0f} (最高: {max_damage_dealt:,}, 最低: {min_damage_dealt:,})")
    print(f"场均最大单次伤害: {avg_max_single:,.0f}")
    print(f"场均最小单次伤害: {avg_min_single:,.0f}")

    # 挑战者伤害分布统计
    all_damages = []
    for s in all_stats:
        all_damages.extend(s.damage_distribution)

    if all_damages:
        all_damages.sort()
        total_hits_count = len(all_damages)

        print(f"\n【伤害分布】(总计 {total_hits_count} 次命中)")

        # 分区间统计
        max_damage = max(all_damages) if all_damages else 0
        min_damage = min(all_damages) if all_damages else 0
        avg_damage = sum(all_damages) / total_hits_count if total_hits_count > 0 else 0

        print(f"  伤害范围: {min_damage:,.0f} - {max_damage:,.0f}")
        print(f"  平均伤害: {avg_damage:,.1f}")

        # 计算分位数
        if total_hits_count >= 4:
            p25 = all_damages[int(total_hits_count * 0.25)]
            p50 = all_damages[int(total_hits_count * 0.50)]  # 中位数
            p75 = all_damages[int(total_hits_count * 0.75)]
            print(f"  分位数: P25={p25:,.0f}, P50={p50:,.0f}, P75={p75:,.0f}")

        # 分区间统计
        damage_ranges = {
            "0-1000": 0,
            "1000-2000": 0,
            "2000-3000": 0,
            "3000-4000": 0,
            "4000-5000": 0,
            "5000-6000": 0,
            "6000-7000": 0,
            "7000-8000": 0,
            "8000+": 0
        }

        for dmg in all_damages:
            if dmg < 1000:
                damage_ranges["0-1000"] += 1
            elif dmg < 2000:
                damage_ranges["1000-2000"] += 1
            elif dmg < 3000:
                damage_ranges["2000-3000"] += 1
            elif dmg < 4000:
                damage_ranges["3000-4000"] += 1
            elif dmg < 5000:
                damage_ranges["4000-5000"] += 1
            elif dmg < 6000:
                damage_ranges["5000-6000"] += 1
            elif dmg < 7000:
                damage_ranges["6000-7000"] += 1
            elif dmg < 8000:
                damage_ranges["7000-8000"] += 1
            else:
                damage_ranges["8000+"] += 1

        print(f"\n  伤害区间分布:")
        # 总是显示所有区间，即使次数为0，便于验证数据一致性
        for range_name in ["0-1000", "1000-2000", "2000-3000", "3000-4000",
                           "4000-5000", "5000-6000", "6000-7000", "7000-8000", "8000+"]:
            count = damage_ranges.get(range_name, 0)
            percentage = count / total_hits_count * 100
            bar_length = int(percentage / 2)  # 每2%一个字符
            bar = "█" * bar_length
            print(f"    {range_name:<10} {count:>4} 次 ({percentage:>5.1f}%) {bar}")

    # 伤害效率分析
    if challenger_attacks > 0:
        avg_damage_per_attack = avg_damage_dealt / challenger_attacks
        crit_count = challenger_results.get("CRIT", 0)
        hit_count = challenger_results.get("HIT", 0)
        total_hits = crit_count + hit_count

        if total_hits > 0:
            avg_damage_on_hit = avg_damage_dealt / total_hits
            print(f"\n【伤害效率】")
            print(f"  平均每次攻击伤害: {avg_damage_per_attack:,.1f}")
            print(f"  平均每次命中伤害: {avg_damage_on_hit:,.1f}")
            print(f"  命中率: {total_hits/challenger_attacks*100:.2f}%")
            print(f"  暴击率: {crit_count/challenger_attacks*100:.2f}%")

    # 挑战者攻击判定结果（挑战者打出去的攻击被Boss如何防御）
    result_descriptions = {
        "MISS": "未命中",
        "DODGE": "闪避",
        "PARRY": "招架",
        "BLOCK": "格挡",
        "CRIT": "暴击",
        "HIT": "普通命中"
    }

    if challenger_name:
        print(f"\n【攻击判定】({challenger_name} vs Boss, 总计 {challenger_attacks} 次攻击)")
    else:
        print(f"\n【攻击判定】(挑战者 vs Boss, 总计 {challenger_attacks} 次攻击)")
    print(f"  {'判定类型':<10} | {'次数':<8} | {'百分比':<8} | {'说明'}")
    print(f"  {'-'*60}")

    for result_name in ["MISS", "DODGE", "PARRY", "BLOCK", "CRIT", "HIT"]:
        count = challenger_results.get(result_name, 0)
        percentage = count / challenger_attacks * 100 if challenger_attacks > 0 else 0
        description = result_descriptions.get(result_name, "")
        # 对于防御类判定，说明这是被Boss如何防御
        if result_name in ["DODGE", "PARRY", "BLOCK"]:
            description = f"被Boss{description}"
        print(f"  {result_name:<10} | {count:<8} | {percentage:>6.2f}% | {description}")

    # 输出节奏分析
    if avg_rounds > 0:
        print(f"\n【输出节奏】")
        print(f"  平均每回合输出(DPR): {avg_dpr:,.1f}")
        # 估算TTK（Time To Kill，回合数）
        if avg_dpr > 0:
            ttk_boss = BOSS_CONFIG['hp'] / avg_dpr
            print(f"  估算击杀Boss需: {ttk_boss:.1f} 回合")

    # ========================================================================
    # 挑战者防御情况分析
    # ========================================================================
    print("\n" + "="*80)
    print("【挑战者防御情况分析】")
    print("="*80)

    # Boss攻击判定结果（Boss打出去的攻击被挑战者如何防御）
    if boss_attacks > 0:
        print(f"\n【防御判定】(Boss vs 挑战者, 总计 {boss_attacks} 次攻击)")
        print(f"  {'判定类型':<10} | {'次数':<8} | {'百分比':<8} | {'说明'}")
        print(f"  {'-'*60}")

        for result_name in ["MISS", "DODGE", "PARRY", "BLOCK", "CRIT", "HIT"]:
            count = boss_results.get(result_name, 0)
            percentage = count / boss_attacks * 100 if boss_attacks > 0 else 0
            description = result_descriptions.get(result_name, "")
            # 对于防御类判定，说明这是被挑战者如何防御
            if result_name in ["DODGE", "PARRY", "BLOCK"]:
                description = f"挑战者{description}"
            print(f"  {result_name:<10} | {count:<8} | {percentage:>6.2f}% | {description}")

        # 挑战者防御效率分析
        challenger_dodges = boss_results.get("DODGE", 0)
        challenger_parries = boss_results.get("PARRY", 0)
        challenger_blocks = boss_results.get("BLOCK", 0)
        challenger_misses = boss_results.get("MISS", 0)

        total_defenses = challenger_dodges + challenger_parries + challenger_blocks + challenger_misses
        defense_rate = total_defenses / boss_attacks * 100

        print(f"\n【防御效率】")
        print(f"  综合防御率: {defense_rate:.2f}%")
        print(f"  闪避贡献: {challenger_dodges/boss_attacks*100:.2f}%")
        print(f"  招架贡献: {challenger_parries/boss_attacks*100:.2f}%")
        print(f"  格挡贡献: {challenger_blocks/boss_attacks*100:.2f}%")
        print(f"  未命中贡献: {challenger_misses/boss_attacks*100:.2f}%")

    # 生存统计
    if wins > 0:
        win_stats = [s for s in all_stats if s.winner == challenger_name]
        # 从最后一回合的统计中获取HP
        final_hp_list = []
        for s in win_stats:
            if s.round_stats:
                final_hp_list.append(s.round_stats[-1].attacker_hp)

        if final_hp_list:
            avg_hp_remaining = sum(final_hp_list) / len(final_hp_list)
            challenger_max_hp = challenger.final_max_hp if challenger else 5000
            avg_hp_percentage = (avg_hp_remaining / challenger_max_hp) * 100
            print(f"\n【生存情况】(胜利时)")
            print(f"  平均剩余HP: {avg_hp_remaining:,.0f} ({avg_hp_percentage:.1f}%)")
            print(f"  最惨胜HP: {min(final_hp_list):,.0f}")
            print(f"  最好胜HP: {max(final_hp_list):,.0f}")

    # 受到的伤害统计
    avg_damage_taken = sum(s.total_damage_taken for s in all_stats) / total_battles
    max_damage_taken = max(s.total_damage_taken for s in all_stats)
    min_damage_taken = min(s.total_damage_taken for s in all_stats)

    print(f"\n【承受伤害】")
    print(f"场均承受伤害: {avg_damage_taken:,.0f} (最高: {max_damage_taken:,}, 最低: {min_damage_taken:,})")
    if avg_rounds > 0:
        avg_damage_per_round = avg_damage_taken / avg_rounds
        print(f"平均每回合承受: {avg_damage_per_round:,.1f}")

    # EN消耗统计
    avg_en_consumed = sum(s.total_en_consumed for s in all_stats) / total_battles
    avg_en_per_round = avg_en_consumed / avg_rounds if avg_rounds > 0 else 0

    print(f"\n【资源消耗】")
    print(f"  场均EN消耗: {avg_en_consumed:,.1f}")
    print(f"  平均每回合EN消耗: {avg_en_per_round:.1f}")

    # 技能触发统计（新逻辑）
    from collections import defaultdict as dd

    # 1. 统计每个技能的出现次数和触发情况
    skill_appearance_count = Counter()  # 每个技能在多少场中出现
    skill_trigger_stats = defaultdict(lambda: {"attempts": 0, "success": 0})  # 每个技能的总触发统计

    for s in all_stats:
        # 记录本场应用的技能
        for skill_id in s.skills_applied:
            skill_appearance_count[skill_id] += 1

        # 记录本场技能的触发统计
        for skill_id, trigger_data in s.skill_trigger_stats.items():
            skill_trigger_stats[skill_id]["attempts"] += trigger_data.get("attempts", 0)
            skill_trigger_stats[skill_id]["success"] += trigger_data.get("success", 0)

    if skill_appearance_count:
        # 加载技能名称映射
        try:
            import os
            data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
            skills_path = os.path.join(data_dir, "skills.json")
            with open(skills_path, "r", encoding="utf-8") as f:
                skills_data = json.load(f)

            def get_skill_name(skill_id: str) -> str:
                """获取技能的中文名称"""
                if skill_id in skills_data:
                    effects_list = skills_data[skill_id]
                    if isinstance(effects_list, list) and len(effects_list) > 0:
                        return effects_list[0].get("name", skill_id)
                return skill_id

            def get_skill_chance(skill_id: str) -> float | None:
                """获取技能的触发概率"""
                if skill_id in skills_data:
                    effects_list = skills_data[skill_id]
                    if isinstance(effects_list, list) and len(effects_list) > 0:
                        effect = effects_list[0]
                        trigger_chance = effect.get("trigger_chance", 1.0)
                        if trigger_chance < 1.0:
                            return trigger_chance
                return None

            # 按技能类型分类统计
            spirit_skills = []
            trait_skills = []
            never_triggered_skills = []  # 从未触发的技能

            for skill_id, appearance_count in skill_appearance_count.items():
                appearance_rate = (appearance_count / total_battles) * 100

                # 获取触发统计
                trigger_data = skill_trigger_stats[skill_id]
                attempts = trigger_data["attempts"]
                success = trigger_data["success"]
                actual_trigger_rate = (success / attempts * 100) if attempts > 0 else 0

                # 获取理论触发概率和技能hook
                theory_chance = get_skill_chance(skill_id)
                skill_hook = ""
                if challenger_obj:
                    skill_info_full = challenger_obj.get_skill_info(skill_id)
                    skill_hook = skill_info_full.get('hook', '')

                skill_name = get_skill_name(skill_id)
                skill_info = {
                    'id': skill_id,
                    'name': skill_name,
                    'appearance_count': appearance_count,
                    'appearance_rate': appearance_rate,
                    'attempts': attempts,
                    'success': success,
                    'actual_trigger_rate': actual_trigger_rate,
                    'theory_trigger_rate': theory_chance * 100 if theory_chance else None,
                    'hook': skill_hook
                }

                if skill_id.startswith("spirit_"):
                    spirit_skills.append(skill_info)
                elif skill_id.startswith("trait_"):
                    trait_skills.append(skill_info)

                # 记录从未触发的技能（attempts == 0）
                if attempts == 0:
                    never_triggered_skills.append(skill_info)

            # 按出现率和触发次数排序
            spirit_skills.sort(key=lambda x: (-x['appearance_rate'], -x['success']))
            trait_skills.sort(key=lambda x: (-x['appearance_rate'], -x['success']))

            print(f"\n【技能统计】(共 {len(skill_appearance_count)} 个不同技能，总场数: {total_battles})")
            print(f"  说明：出现率 = 技能被随机抽取并应用的场次比例")
            print(f"        实际触发率 = 技能在战斗中的实际触发次数 / 触发机会次数")
            print(f"        理论触发率 = 技能配置中定义的触发概率（仅概率型技能显示）")

            # 精神指令统计
            if spirit_skills:
                print(f"\n  【精神指令】(共 {len(spirit_skills)} 个)")
                print(f"  {'技能名称':<12} | {'出现场次':<8} | {'出现率':<8} | {'尝试/成功':<12} | {'实际触发率':<10} | {'理论触发率'}")
                print(f"  {'-'*90}")

                for skill in spirit_skills[:15]:  # 显示前15个
                    theory_rate = f"{skill['theory_trigger_rate']:.1f}%" if skill['theory_trigger_rate'] is not None else "-"
                    attempts_success = f"{skill['attempts']}/{skill['success']}"
                    print(f"  {skill['name']:<12} | {skill['appearance_count']:<8} | {skill['appearance_rate']:>6.1f}% | {attempts_success:<12} | {skill['actual_trigger_rate']:>8.1f}% | {theory_rate:>12}")

            # 机体特性统计
            if trait_skills:
                print(f"\n  【机体特性】(共 {len(trait_skills)} 个)")
                print(f"  {'技能名称':<12} | {'出现场次':<8} | {'出现率':<8} | {'尝试/成功':<12} | {'实际触发率':<10} | {'理论触发率'}")
                print(f"  {'-'*90}")

                for skill in trait_skills[:15]:  # 显示前15个
                    theory_rate = f"{skill['theory_trigger_rate']:.1f}%" if skill['theory_trigger_rate'] is not None else "-"
                    attempts_success = f"{skill['attempts']}/{skill['success']}"
                    print(f"  {skill['name']:<12} | {skill['appearance_count']:<8} | {skill['appearance_rate']:>6.1f}% | {attempts_success:<12} | {skill['actual_trigger_rate']:>8.1f}% | {theory_rate:>12}")

            # 概率型技能触发率对比分析
            print(f"\n  【概率型技能触发率分析】")
            prob_skills = [s for s in spirit_skills + trait_skills if s['theory_trigger_rate'] is not None]
            if prob_skills:
                print(f"  共 {len(prob_skills)} 个概率型技能")
                print(f"  {'技能名称':<12} | {'理论':<8} | {'实际':<8} | {'偏差'}")
                print(f"  {'-'*50}")

                for skill in prob_skills:
                    theory = skill['theory_trigger_rate']
                    actual = skill['actual_trigger_rate']
                    diff = actual - theory
                    diff_str = f"{diff:+.1f}%"
                    print(f"  {skill['name']:<12} | {theory:>6.1f}% | {actual:>6.1f}% | {diff_str:>8}")
            else:
                print(f"  本轮测试中未出现概率型技能")

            # 从未触发技能分析（调试信息）
            if never_triggered_skills:
                print(f"\n  【从未触发技能调试】(共 {len(never_triggered_skills)} 个)")
                print(f"  说明：这些技能被应用了，但在所有场次中都没有触发")
                print(f"  {'技能名称':<15} | {'出现场次':<10} | {'Hook':<25} | {'可能原因'}")
                print(f"  {'-'*80}")

                hook_reasons = {
                    "HOOK_ON_KILL": "需要击杀敌人（Boss血量过高，可能从未击杀）",
                    "HOOK_ON_DAMAGE_DEALT": "需要造成伤害（可能未命中或被闪避）",
                    "HOOK_ON_TURN_END": "回合结束触发（应该触发，需检查逻辑）",
                    "HOOK_PRE_DAMAGE_MULT": "伤害计算前触发（应该触发，需检查逻辑）",
                    "HOOK_INITIATIVE_SCORE": "先手判定时触发（可能先手率低）",
                }

                for skill in never_triggered_skills[:10]:  # 只显示前10个
                    hook = skill['hook']
                    reason = hook_reasons.get(hook, f"未知Hook: {hook}")
                    print(f"  {skill['name']:<15} | {skill['appearance_count']:<10} | {hook:<25} | {reason}")

                if len(never_triggered_skills) > 10:
                    print(f"  ... 还有 {len(never_triggered_skills) - 10} 个未显示")

        except FileNotFoundError:
            # 如果文件不存在，使用原始ID
            import os
            print(f"\n【技能应用情况】(共 {len(skill_appearance_count)} 个不同技能)")
            for skill_id, appearance_count in skill_appearance_count.most_common(10):
                appearance_rate = (appearance_count / total_battles) * 100
                trigger_data = skill_trigger_stats[skill_id]
                attempts = trigger_data["attempts"]
                success = trigger_data["success"]
                actual_trigger_rate = (success / attempts * 100) if attempts > 0 else 0
                print(f"  {skill_id}: 出现 {appearance_count} 次 ({appearance_rate:.1f}%) | 触发 {success}/{attempts} ({actual_trigger_rate:.1f}%)")

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
    print(f"  HP: {BOSS_CONFIG['hp']:,} (快照值)")
    print(f"  EN: {BOSS_CONFIG['en']:,} (快照值)")
    print(f"  护甲: {BOSS_CONFIG['defense']:,} (快照值)")
    print(f"  机动: {BOSS_CONFIG['mobility']} (快照值)")
    print(f"  命中/精准/暴击: {BOSS_CONFIG['hit_rate']}% / {BOSS_CONFIG['precision']}% / {BOSS_CONFIG['crit_rate']}% (快照值)")
    dodge_rate = BOSS_CONFIG['dodge_rate'] if BOSS_CONFIG['dodge_rate'] is not None else BOSS_CONFIG['mobility'] * 0.1
    print(f"  躲闪/招架/格挡: {dodge_rate}% / {BOSS_CONFIG['parry_rate']}% / {BOSS_CONFIG['block_rate']}% (快照值)")

    # 获取挑战者配置信息
    mecha_config = challenger.loader.get_mecha_config(CHALLENGER_CONFIG['mecha_id'])

    print(f"\n【挑战者配置】({mecha_config.name})")
    print(f"  机体ID: {CHALLENGER_CONFIG['mecha_id']}")
    print(f"  驾驶员ID: {CHALLENGER_CONFIG['pilot_id']}")
    print(f"  固定武器: {', '.join(mecha_config.fixed_weapons)}")
    print(f"  随机技能: {CHALLENGER_CONFIG['spirit_count']} 精神 + {CHALLENGER_CONFIG['trait_count']} 特性")

    # 显示设备配置
    if CHALLENGER_CONFIG['equip_ids']:
        equip_names = []
        for equip_id in CHALLENGER_CONFIG['equip_ids']:
            if equip_id in challenger.loader.equipments:
                equip_names.append(challenger.loader.equipments[equip_id].name)
        print(f"  安装设备: {', '.join(equip_names)}")

    # 创建一个实例来查看实际属性（包括设备加成）
    test_mecha = challenger.create_challenger()

    # 计算修正值的辅助函数
    def format_with_mod(final_val: int | float, base_val: int | float, is_float: bool = False) -> str:
        """格式化显示：快照值(修正值)"""
        modifier = final_val - base_val
        sign = "+" if modifier > 0 else "" if modifier == 0 else ""
        if is_float:
            return f"{final_val} ({sign}{modifier:.1f})"
        return f"{final_val:,} ({sign}{modifier:,})"

    print(f"\n【挑战者快照属性】(含设备和驾驶员加成)")
    print(f"  HP: {format_with_mod(test_mecha.final_max_hp, mecha_config.init_hp)} (基础: {mecha_config.init_hp:,})")
    print(f"  EN: {format_with_mod(test_mecha.final_max_en, mecha_config.init_en)} (基础: {mecha_config.init_en:,})")
    print(f"  护甲: {format_with_mod(test_mecha.final_armor, mecha_config.init_armor)} (基础: {mecha_config.init_armor:,})")
    print(f"  机动: {format_with_mod(test_mecha.final_mobility, mecha_config.init_mobility)} (基础: {mecha_config.init_mobility:,})")
    print(f"  命中: {format_with_mod(test_mecha.final_hit, mecha_config.init_hit, is_float=True)}% (基础: {mecha_config.init_hit}%)")
    print(f"  精准: {format_with_mod(test_mecha.final_precision, mecha_config.init_precision, is_float=True)}% (基础: {mecha_config.init_precision}%)")
    print(f"  暴击: {format_with_mod(test_mecha.final_crit, mecha_config.init_crit, is_float=True)}% (基础: {mecha_config.init_crit}%)")
    print(f"  躲闪: {format_with_mod(test_mecha.final_dodge, mecha_config.init_dodge, is_float=True)}% (基础: {mecha_config.init_dodge}%)")
    print(f"  招架: {format_with_mod(test_mecha.final_parry, mecha_config.init_parry, is_float=True)}% (基础: {mecha_config.init_parry}%)")
    print(f"  格挡: {format_with_mod(test_mecha.final_block, mecha_config.init_block, is_float=True)}% (基础: {mecha_config.init_block}%)")

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

    # 打印统计分析（创建一个用于显示数据的challenger实例）
    challenger_mecha = challenger.create_challenger()
    print_statistics(all_stats, challenger_mecha, challenger)


if __name__ == "__main__":
    main()
