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

重构说明：
- 移除 _execute_attack_with_stats() 重写方法
- 使用父类标准 _execute_attack() 流程
- 集成 StatisticsCollector 作为事件监听器
- 完整支持演出系统和事件驱动架构
"""

import sys
import os
import io
import random
import argparse
import json
from typing import List, Any
from collections import Counter, defaultdict

# 确保导入路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

# Windows UTF-8 支持
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.models import Mecha, Pilot, Weapon, WeaponType, BattleContext, Effect
from src.skills import SkillRegistry, EffectManager, TraitManager
from src.combat.engine import BattleSimulator
from src.combat.statistics_collector import StatisticsCollector, BattleStatistics
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

BOSS_CONFIG = {
    "name": "测试 Boss",
    "hp": 500000,
    "en": 400,
    "defense": 1000,
    "mobility": 120,
    "hit_rate": 20.0,
    "precision": 15.0,
    "crit_rate": 10.0,
    "dodge_rate": None,
    "parry_rate": 15.0,
    "block_rate": 15.0,
    "weapon_power_percent": 0.001,
    "weapon_en_cost": 1,
    "pilot_shooting": 150,
    "pilot_melee": 150,
    "pilot_reaction": 150,
    "pilot_awakening": 150,
    "pilot_defense": 150,
    "weapon_proficiency": 1000,
    "mecha_proficiency": 4000,
}

CHALLENGER_CONFIG = {
    "mecha_id": "mech_rx78",
    "pilot_id": "pilot_amuro",
    "weapon_ids": ["wpn_beam_saber"],
    "equip_ids": ["e_booster", "e_chobham_armor", "e_magnetron_coating"],
    "spirit_count": 2,
    "trait_count": 3,
}

# ============================================================================
# 3. 木桩测试器
# ============================================================================
# 4. 木桩测试器
# ============================================================================

class DummyBossSimulator(BattleSimulator):
    """增强版战斗模拟器，集成统计收集功能。

    该类继承自BattleSimulator，增加了对战斗过程的统计收集功能，
    用于分析战斗数据、收集统计数据，并支持详细的结果分析。

    重构说明：
    - 使用父类标准 _execute_attack() 流程
    - 集成 StatisticsCollector 作为事件监听器
    - 删除 _execute_attack_with_stats() 重写方法
    - 完整支持演出系统和事件驱动架构

    Attributes:
        battle_id (int): 战斗ID，用于区分不同的战斗实例
    重载说明：
    - 继承自 BattleSimulator，利用其自带的 verbose/quiet 控制和渲染能力
    - 仅配置 StatisticsCollector 及其事件钩子，逻辑完全复用父类
    """

    def __init__(self, mecha_a: Mecha, mecha_b: Mecha, battle_id: int = 0, verbose: bool = False, quiet: bool = False):
        """初始化精简版战斗模拟器。

        Args:
            mecha_a: A方机体实例
            mecha_b: B方机体实例
            battle_id: 战斗唯一标识符
            verbose: 是否输出详细战斗日志
            quiet: 是否静默运行
        """
        # 调用父类构造函数，启用演出系统并配置日志级别
        super().__init__(
            mecha_a, mecha_b,
            enable_presentation=not quiet,
            verbose=verbose,
            quiet=quiet
        )

        self.battle_id = battle_id

        # 创建统计收集器
        self.collector = StatisticsCollector(
            battle_id=battle_id,
            mecha_a_id=mecha_a.id,
            mecha_b_id=mecha_b.id,
            enable_detailed_records=False
        )

        # 注册核心引擎钩子
        self.register_attack_event_listener(self.collector.on_attack_event)
        self.register_round_start_listener(self._on_round_start_hook)
        self.register_round_end_listener(self._on_round_end_hook)

    def run_battle_with_stats(self) -> BattleStatistics:
        """执行战斗并返回结算统计对象。"""
        # 直接使用父类的标准战斗流程
        self.run_battle()
        return self._finalize_stats()

    def _on_round_start_hook(self, round_num, distance, first_mover, second_mover, reason):
        """同步统计收集器的回合上下文。"""
        self.collector.set_round_context(
            round_number=round_num,
            distance=distance,
            first_mover=first_mover.name,
            initiative_reason=reason.value
        )

    def _on_round_end_hook(self, round_num, distance):
        """回合结束时收集状态快照。"""
        # 记录全场状态
        self.collector.on_round_end(
            mecha_a_hp=self.mecha_a.current_hp,
            mecha_a_en=self.mecha_a.current_en,
            mecha_a_will=self.mecha_a.current_will,
            mecha_b_hp=self.mecha_b.current_hp,
            mecha_b_en=self.mecha_b.current_en,
            mecha_b_will=self.mecha_b.current_will
        )
        self.collector.on_will_changed(round_num, self.mecha_a.current_will)

        # 估算本回合回复（简化模拟：基于 mecha 属性）
        # 注：真正的精确逻辑在 on_en_regened 中，由于 engine._execute_round 没暴露 regen 数值
        # 我们可以通过订阅 on_en_regened 的回调（如果需要绝对精确）
        # 但这里主要用于统计显示，我们在父类 _apply_en_regeneration 中加个通知即可（可选）
        # 目前简单通过状态差值计算
        pass

    def _finalize_stats(self) -> BattleStatistics:
        """结算战斗统计"""
        # 从父类状态中提取胜方
        winner = "平局"
        end_reason = "平局"

        if not self.mecha_a.is_alive():
            winner = self.mecha_b.name
            end_reason = "击破"
        elif not self.mecha_b.is_alive():
            winner = self.mecha_a.name
            end_reason = "击破"
        else:
            hp_a = self.mecha_a.get_hp_percentage()
            hp_b = self.mecha_b.get_hp_percentage()
            if hp_a > hp_b:
                winner = self.mecha_a.name
                end_reason = "判定胜"
            elif hp_b > hp_a:
                winner = self.mecha_b.name
                end_reason = "判定胜"

        # 使用统计收集器生成最终统计
        return self.collector.finalize_battle(
            rounds=self.round_number,
            winner=winner,
            end_reason=end_reason
        )


class BossChallenger:
    """Boss木桩测试器。

    该类用于创建和管理Boss木桩测试，可以模拟挑战者与高防御力的Boss机体的战斗，
    并收集相关的战斗统计数据用于分析。
    """

    def __init__(self, verbose: bool = False):
        """初始化Boss木桩测试器。

        该构造函数加载必要的数据文件和技能配置，为后续的Boss挑战测试做准备。

        Args:
            verbose (bool): 是否输出详细信息，默认为False
        """
        self.verbose = verbose
        import os
        # 获取项目根目录（scripts/sim 的上两级）
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        data_dir = os.path.join(project_root, 'data')
        self.loader = DataLoader(data_dir=data_dir)
        self.loader.load_all()

        skills_path = os.path.join(data_dir, "skills.json")
        with open(skills_path, "r", encoding="utf-8") as f:
            self.all_skills_data = json.load(f)

        self.all_skill_ids = list(self.all_skills_data.keys())
        self.spirits = [s for s in self.all_skill_ids if s.startswith("spirit_")]
        self.traits = [t for t in self.all_skill_ids if t.startswith("trait_")]
        self.challenger_name = None

    def get_skill_name(self, skill_id: str) -> str:
        """根据技能ID获取技能名称。

        通过技能的唯一标识符查找对应的技能名称，如果找不到则返回技能ID本身。

        Args:
            skill_id (str): 技能的唯一标识符

        Returns:
            str: 技能名称，如果找不到则返回技能ID本身
        """
        if skill_id in self.all_skills_data:
            effects_list = self.all_skills_data[skill_id]
            if isinstance(effects_list, list) and len(effects_list) > 0:
                return effects_list[0].get("name", skill_id)
        return skill_id

    def get_skill_info(self, skill_id: str) -> dict:
        """根据技能ID获取技能详细信息。

        通过技能的唯一标识符查找技能的详细信息，包括名称、描述、操作类型等。
        如果找不到对应技能，则返回包含基本名称信息的字典。

        Args:
            skill_id (str): 技能的唯一标识符

        Returns:
            dict: 包含技能详细信息的字典，包括名称、描述、操作类型、值和钩子类型
        """
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
        return {'name': skill_id, 'description': "", 'operation': "", 'value': "", 'hook': ""}

    def create_boss(self) -> Mecha:
        """创建Boss木桩机体实例。

        该方法根据预设的BOSS_CONFIG配置创建一个高防御力的Boss机体，
        用于测试挑战者的输出能力和各种技能组合的效果。

        Returns:
            Mecha: 配置完成的Boss机体实例
        """
        pilot = Pilot(
            id="boss_pilot", name="Boss Pilot", portrait_id="boss_portrait",
            stat_shooting=BOSS_CONFIG['pilot_shooting'],
            stat_melee=BOSS_CONFIG['pilot_melee'],
            stat_reaction=BOSS_CONFIG['pilot_reaction'],
            stat_awakening=BOSS_CONFIG['pilot_awakening'],
            stat_defense=BOSS_CONFIG['pilot_defense']
        )

        dodge_rate = BOSS_CONFIG['dodge_rate']
        if dodge_rate is None:
            dodge_rate = BOSS_CONFIG['mobility'] * 0.1

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
        """创建挑战者机体实例。

        该方法根据预设的CHALLENGER_CONFIG配置创建一个挑战者机体，
        用于与Boss进行战斗测试，通常是一个配置较高的机体以测试Boss的防御能力。

        Returns:
            Mecha: 配置完成的挑战者机体实例
        """
        mecha_config = self.loader.get_mecha_config(CHALLENGER_CONFIG['mecha_id'])
        pilot_config = self.loader.get_pilot_config(CHALLENGER_CONFIG['pilot_id'])

        equip_configs = []
        if CHALLENGER_CONFIG['equip_ids']:
            for equip_id in CHALLENGER_CONFIG['equip_ids']:
                if equip_id in self.loader.equipments:
                    equip_configs.append(self.loader.equipments[equip_id])

        challenger = MechaFactory.create_mecha_snapshot(
            mecha_config,
            pilot_conf=pilot_config,
            equipments=equip_configs if equip_configs else None,
            weapon_configs=self.loader.equipments
        )

        self.challenger_name = challenger.name

        if CHALLENGER_CONFIG['weapon_ids']:
            new_weapons = []
            for weapon_id in CHALLENGER_CONFIG['weapon_ids']:
                weapon_config = self.loader.get_equipment_config(weapon_id)
                weapon_snapshot = MechaFactory.create_weapon_snapshot(weapon_config)
                new_weapons.append(weapon_snapshot)
            challenger.weapons = new_weapons

        return challenger

    def apply_random_skills(self, mecha: Mecha):
        """为机体应用随机技能组合。

        该方法从可用技能池中随机选择指定数量的精神和特性技能，
        并将其应用到给定的机体上，用于测试不同技能组合的效果。

        Args:
            mecha (Mecha): 要应用技能的机体实例

        Returns:
            list: 包含所应用技能ID的列表
        """
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

        for s_id in selected_spirits:
            EffectManager.add_effect(mecha, s_id, duration=100)
        mecha.skills = selected_traits
        TraitManager.apply_traits(mecha)

        return selected_spirits + selected_traits

    def run_challenge(self, round_idx: int, quiet: bool = False) -> BattleStatistics:
        """执行单轮Boss挑战测试。

        该方法执行一次完整的挑战者与Boss之间的战斗测试，
        并收集战斗过程中的统计数据。

        Args:
            round_idx (int): 当前测试轮次的索引
            quiet (bool): 是否静默运行（减少输出），默认为False

        Returns:
            BattleStatistics: 包含该轮战斗详细统计信息的对象
        """
        if not quiet and self.verbose:
            print("\n" + "="*70)
            print(f"【第 {round_idx} 轮测试】")
            print("="*70)
            print(f"\nBoss HP: {BOSS_CONFIG['hp']:,}")
            print(f"Boss 防御: {BOSS_CONFIG['defense']:,}")
            print(f"Boss 机动: {BOSS_CONFIG['mobility']:,}")
            print(f"Boss EN: {BOSS_CONFIG['en']}")

        attacker = self.create_challenger()
        boss = self.create_boss()

        skills_applied = self.apply_random_skills(attacker)
        attacker.effects.append(get_maintain_skill())

        if not quiet and self.verbose:
            print(f"\n--- 战斗开始: {attacker.name} vs {boss.name} ---")
            print(f"挑战者 HP: {attacker.current_hp:,} | Boss HP: {boss.current_hp:,}")

        from src.skill_system.event_manager import EventManager
        EventManager.clear_statistics()

        sim = DummyBossSimulator(attacker, boss, battle_id=round_idx, verbose=self.verbose, quiet=quiet)
        stats = sim.run_battle_with_stats()
        stats.skills_applied = skills_applied

        all_skill_stats = EventManager.get_statistics()

        if not quiet and self.verbose and all_skill_stats:
            print(f"\n[DEBUG] 技能触发统计 (本场战斗):")
            for skill_id, trigger_data in all_skill_stats.items():
                attempts = trigger_data.get("attempts", 0)
                success = trigger_data.get("success", 0)
                skill_name = self.get_skill_name(skill_id)
                print(f"  {skill_name}({skill_id}): 尝试 {attempts} 次, 成功 {success} 次")

        stats.skill_trigger_stats = all_skill_stats

        if not quiet and self.verbose:
            print(f"\n{'─'*70}")
            print(f"【测试结束】")
            print(f"{'─'*70}")
            print(f"最终回合数: {stats.rounds}")
            print(f"获胜方: {stats.winner} ({stats.end_reason})")
            print(f"挑战者剩余 HP: {attacker.current_hp:,} ({attacker.get_hp_percentage():.1f}%)")
            print(f"Boss 剩余 HP: {boss.current_hp:,} ({boss.get_hp_percentage():.1f}%)")
        elif not quiet:
            print(f"  第 {round_idx} 轮完成: {stats.rounds} 回合, 获胜者: {stats.winner}")

        return stats


# ============================================================================
# 5. 统计辅助函数（重构后）
# ============================================================================

def print_damage_distribution(all_damages: List[int], title: str):
    """打印伤害分布统计（复用函数）"""
    if not all_damages:
        return

    all_damages.sort()
    total_hits = len(all_damages)

    print(f"\n【{title}】(总计 {total_hits} 次命中)")
    print(f"  伤害范围: {min(all_damages):,.0f} - {max(all_damages):,.0f}")
    print(f"  平均伤害: {sum(all_damages) / total_hits:.1f}")

    if total_hits >= 4:
        p25 = all_damages[int(total_hits * 0.25)]
        p50 = all_damages[int(total_hits * 0.50)]
        p75 = all_damages[int(total_hits * 0.75)]
        print(f"  分位数: P25={p25:,.0f}, P50={p50:,.0f}, P75={p75:,.0f}")

    # 分区间统计
    ranges = ["0-1000", "1000-2000", "2000-3000", "3000-4000",
              "4000-5000", "5000-6000", "6000-7000", "7000-8000", "8000+"]
    bounds = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000]

    damage_ranges = {r: 0 for r in ranges}
    for dmg in all_damages:
        for i, bound in enumerate(bounds):
            if dmg < bound:
                damage_ranges[ranges[i]] += 1
                break
        else:
            damage_ranges["8000+"] += 1

    print(f"\n  伤害区间分布:")
    for range_name in ranges:
        count = damage_ranges[range_name]
        percentage = count / total_hits * 100
        bar = "█" * int(percentage / 2)
        print(f"    {range_name:<10} {count:>4} 次 ({percentage:>5.1f}%) {bar}")


def print_survival_stats(win_stats: List[BattleStatistics], challenger: Mecha, challenger_name: str):
    """打印生存统计"""
    if not win_stats:
        return

    # 使用新的 round_snapshots 结构
    final_hp_list = [s.round_snapshots[-1].mecha_a_hp for s in win_stats if s.round_snapshots]
    if not final_hp_list:
        return

    avg_hp = sum(final_hp_list) / len(final_hp_list)
    max_hp = challenger.final_max_hp if challenger else 5000
    avg_pct = (avg_hp / max_hp) * 100

    print(f"\n胜利时生存情况:")
    print(f"  平均剩余HP: {avg_hp:,.0f} ({avg_pct:.1f}%)")
    print(f"  最惨胜HP: {min(final_hp_list):,.0f}")
    print(f"  最好胜HP: {max(final_hp_list):,.0f}")


def print_skill_statistics(all_stats: List[BattleStatistics], total_battles: int, challenger_obj):
    """打印技能统计"""
    from collections import defaultdict as dd

    skill_appearance_count = Counter()
    skill_trigger_stats = defaultdict(lambda: {"attempts": 0, "success": 0})

    for s in all_stats:
        for skill_id in s.skills_applied:
            skill_appearance_count[skill_id] += 1
        for skill_id, trigger_data in s.skill_trigger_stats.items():
            skill_trigger_stats[skill_id]["attempts"] += trigger_data.get("attempts", 0)
            skill_trigger_stats[skill_id]["success"] += trigger_data.get("success", 0)

    if not skill_appearance_count:
        return

    try:
        import os
        data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')
        skills_path = os.path.join(data_dir, "skills.json")
        with open(skills_path, "r", encoding="utf-8") as f:
            skills_data = json.load(f)

        def get_skill_name(skill_id):
            if skill_id in skills_data:
                effects_list = skills_data[skill_id]
                if isinstance(effects_list, list) and len(effects_list) > 0:
                    return effects_list[0].get("name", skill_id)
            return skill_id

        def get_skill_chance(skill_id):
            if skill_id in skills_data:
                effects_list = skills_data[skill_id]
                if isinstance(effects_list, list) and len(effects_list) > 0:
                    effect = effects_list[0]
                    trigger_chance = effect.get("trigger_chance", 1.0)
                    if trigger_chance < 1.0:
                        return trigger_chance
            return None

        spirit_skills = []
        trait_skills = []
        never_triggered = []

        for skill_id, appearance_count in skill_appearance_count.items():
            appearance_rate = (appearance_count / total_battles) * 100

            trigger_data = skill_trigger_stats[skill_id]
            attempts = trigger_data["attempts"]
            success = trigger_data["success"]
            actual_rate = (success / attempts * 100) if attempts > 0 else 0
            theory_chance = get_skill_chance(skill_id)
            skill_hook = ""
            if challenger_obj:
                skill_info_full = challenger_obj.get_skill_info(skill_id)
                skill_hook = skill_info_full.get('hook', '')

            skill_info = {
                'id': skill_id,
                'name': get_skill_name(skill_id),
                'appearance_count': appearance_count,
                'appearance_rate': appearance_rate,
                'attempts': attempts,
                'success': success,
                'actual_rate': actual_rate,
                'theory_rate': theory_chance * 100 if theory_chance else None,
                'hook': skill_hook
            }

            if skill_id.startswith("spirit_"):
                spirit_skills.append(skill_info)
            elif skill_id.startswith("trait_"):
                trait_skills.append(skill_info)

            if attempts == 0:
                never_triggered.append(skill_info)

        spirit_skills.sort(key=lambda x: (-x['appearance_rate'], -x['success']))
        trait_skills.sort(key=lambda x: (-x['appearance_rate'], -x['success']))

        print(f"\n【技能统计】(共 {len(skill_appearance_count)} 个不同技能，总场数: {total_battles})")

        if spirit_skills:
            print(f"\n  【精神指令】(共 {len(spirit_skills)} 个)")
            print(f"  {'技能名称':<12} | {'出现场次':<8} | {'出现率':<8} | {'尝试/成功':<12} | {'实际触发率':<10} | {'理论触发率'}")
            print(f"  {'-'*90}")
            for skill in spirit_skills[:15]:
                theory_rate = f"{skill['theory_rate']:.1f}%" if skill['theory_rate'] is not None else "-"
                attempts_success = f"{skill['attempts']}/{skill['success']}"
                print(f"  {skill['name']:<12} | {skill['appearance_count']:<8} | {skill['appearance_rate']:>6.1f}% | {attempts_success:<12} | {skill['actual_rate']:>8.1f}% | {theory_rate:>12}")

        if trait_skills:
            print(f"\n  【机体特性】(共 {len(trait_skills)} 个)")
            print(f"  {'技能名称':<12} | {'出现场次':<8} | {'出现率':<8} | {'尝试/成功':<12} | {'实际触发率':<10} | {'理论触发率'}")
            print(f"  {'-'*90}")
            for skill in trait_skills[:15]:
                theory_rate = f"{skill['theory_rate']:.1f}%" if skill['theory_rate'] is not None else "-"
                attempts_success = f"{skill['attempts']}/{skill['success']}"
                print(f"  {skill['name']:<12} | {skill['appearance_count']:<8} | {skill['appearance_rate']:>6.1f}% | {attempts_success:<12} | {skill['actual_rate']:>8.1f}% | {theory_rate:>12}")

    except FileNotFoundError:
        print(f"\n【技能应用情况】(共 {len(skill_appearance_count)} 个不同技能)")
        for skill_id, appearance_count in skill_appearance_count.most_common(10):
            appearance_rate = (appearance_count / total_battles) * 100
            trigger_data = skill_trigger_stats[skill_id]
            attempts = trigger_data["attempts"]
            success = trigger_data["success"]
            actual_rate = (success / attempts * 100) if attempts > 0 else 0
            print(f"  {skill_id}: 出现 {appearance_count} 次 ({appearance_rate:.1f}%) | 触发 {success}/{attempts} ({actual_rate:.1f}%)")


def print_statistics(all_stats: List[BattleStatistics], challenger_mecha: Mecha | None = None, mecha_config = None, challenger_obj: Any = None, boss_mecha: Mecha | None = None):
    """打印统计分析结果（重构简化版）"""
    print("\n" + "="*80)
    print("【统计分析报告】")
    print("="*80)

    total_battles = len(all_stats)
    challenger_name = all_stats[0].winner if all_stats and all_stats[0].winner != BOSS_CONFIG['name'] else None

    wins = sum(1 for s in all_stats if s.winner == challenger_name)
    avg_rounds = sum(s.rounds for s in all_stats) / total_battles

    print(f"\n【基础数据】")
    print(f"测试次数: {total_battles}")
    print(f"胜利次数: {wins} ({wins/total_battles*100:.1f}%)")
    print(f"平均回合数: {avg_rounds:.1f} (最短: {min(s.rounds for s in all_stats)}, 最长: {max(s.rounds for s in all_stats)})")

    # 伤害统计
    avg_damage = sum(s.total_damage_dealt for s in all_stats) / total_battles
    max_damage = max(s.total_damage_dealt for s in all_stats)
    min_damage = min(s.total_damage_dealt for s in all_stats)
    avg_max_single = sum(s.max_single_damage for s in all_stats) / total_battles
    avg_min_single = sum(s.min_single_damage for s in all_stats) / total_battles

    print(f"\n【伤害统计】")
    print(f"场均总输出: {avg_damage:,.0f} (最高: {max_damage:,}, 最低: {min_damage:,})")
    print(f"场均最大单次伤害: {avg_max_single:,.0f}")
    print(f"场均最小单次伤害: {avg_min_single:,.0f}")

    # 挑战者伤害分布（移到攻击分析块内）
    all_damages = []
    for s in all_stats:
        all_damages.extend(s.damage_distribution)

    # 攻击判定
    challenger_attacks = sum(sum(s.challenger_attack_results.values()) for s in all_stats)
    challenger_results = Counter()
    for s in all_stats:
        challenger_results.update(s.challenger_attack_results)

    # 获取挑战者基础属性用于对比理论值
    if mecha_config:
        base_hit = mecha_config.init_hit
        base_crit = mecha_config.init_crit
        base_precision = mecha_config.init_precision
        base_dodge = mecha_config.init_dodge
        base_parry = mecha_config.init_parry
        base_block = mecha_config.init_block
    else:
        base_hit = base_crit = base_precision = base_dodge = base_parry = base_block = 15.0

    print("\n" + "="*80)
    print("【挑战者攻击情况分析】")
    print("="*80)

    # 伤害分布（移到这里）
    print_damage_distribution(all_damages, "挑战者伤害分布")

    result_desc = {"MISS": "未命中", "DODGE": "闪避", "PARRY": "招架", "BLOCK": "格挡", "CRIT": "暴击", "HIT": "普通命中"}

    if challenger_name:
        print(f"\n【攻击判定】({challenger_name} vs Boss, 总计 {challenger_attacks} 次攻击)")
    else:
        print(f"\n【攻击判定】(挑战者 vs Boss, 总计 {challenger_attacks} 次攻击)")

    print(f"  {'判定类型':<10} | {'次数':<8} | {'百分比':<8} | {'说明'}")
    print(f"  {'-'*60}")
    for result_name in ["MISS", "DODGE", "PARRY", "BLOCK", "CRIT", "HIT"]:
        count = challenger_results.get(result_name, 0)
        percentage = count / challenger_attacks * 100 if challenger_attacks > 0 else 0
        description = result_desc.get(result_name, "")
        if result_name in ["DODGE", "PARRY", "BLOCK"]:
            description = f"被Boss{description}"
        print(f"  {result_name:<10} | {count:<8} | {percentage:>6.2f}% | {description}")

    avg_dpr = avg_damage / avg_rounds if avg_rounds > 0 else 0
    print(f"\n【输出节奏】")
    print(f"  平均每回合输出(DPR): {avg_dpr:,.1f}")
    if avg_dpr > 0:
        ttk = BOSS_CONFIG['hp'] / avg_dpr
        print(f"  估算击杀Boss需: {ttk:.1f} 回合")

    # 伤害效率（显示对比理论值 - 使用Round Table实际概率）
    if challenger_attacks > 0 and challenger_mecha:
        from src.combat.resolver import AttackTableResolver

        crit_count = challenger_results.get("CRIT", 0)
        hit_count = challenger_results.get("HIT", 0)
        total_hits = crit_count + hit_count
        if total_hits > 0:
            avg_per_hit = avg_damage / total_hits
            actual_hit_rate = total_hits / challenger_attacks * 100
            actual_crit_rate = crit_count / challenger_attacks * 100

            # 计算真正的理论值：使用Round Table
            test_weapon = challenger_mecha.weapons[0] if challenger_mecha.weapons else None
            if test_weapon and boss_mecha:
                from src.models import BattleContext
                test_ctx = BattleContext(
                    round_number=1, distance=3000,
                    mecha_a=challenger_mecha, mecha_b=boss_mecha,
                    weapon=test_weapon
                )
                test_segments = AttackTableResolver.calculate_attack_table_segments(test_ctx)
                theory_hit = test_segments.get('HIT', {}).get('rate', 0) + test_segments.get('CRIT', {}).get('rate', 0)
                theory_crit = test_segments.get('CRIT', {}).get('rate', 0)
            else:
                theory_hit = base_hit + base_precision
                theory_crit = base_crit

            print(f"\n【伤害效率】")
            print(f"  平均每次攻击伤害: {avg_damage/challenger_attacks:,.1f}")
            print(f"  平均每次命中伤害: {avg_per_hit:,.1f}")
            print(f"  命中率: {actual_hit_rate:.2f}% (理论值: {theory_hit:.2f}%)")
            print(f"  暴击率: {actual_crit_rate:.2f}% (理论值: {theory_crit:.2f}%)")

    # 防御情况
    boss_attacks = sum(sum(s.boss_attack_results.values()) for s in all_stats)
    boss_results = Counter()
    for s in all_stats:
        boss_results.update(s.boss_attack_results)

    print("\n" + "="*80)
    print("【挑战者防御情况分析】")
    print("="*80)

    if boss_attacks > 0:
        print(f"\n【防御判定】(Boss vs 挑战者, 总计 {boss_attacks} 次攻击)")
        print(f"  {'判定类型':<10} | {'次数':<8} | {'百分比':<8} | {'说明'}")
        print(f"  {'-'*60}")
        for result_name in ["MISS", "DODGE", "PARRY", "BLOCK", "CRIT", "HIT"]:
            count = boss_results.get(result_name, 0)
            percentage = count / boss_attacks * 100 if boss_attacks > 0 else 0
            description = result_desc.get(result_name, "")
            if result_name in ["DODGE", "PARRY", "BLOCK"]:
                description = f"挑战者{description}"
            print(f"  {result_name:<10} | {count:<8} | {percentage:>6.2f}% | {description}")

        total_def = (boss_results.get("DODGE", 0) + boss_results.get("PARRY", 0) +
                     boss_results.get("BLOCK", 0) + boss_results.get("MISS", 0))

        # 防御效率（显示对比理论值 - 使用Round Table实际概率）
        actual_dodge_rate = boss_results.get("DODGE", 0) / boss_attacks * 100
        actual_parry_rate = boss_results.get("PARRY", 0) / boss_attacks * 100
        actual_block_rate = boss_results.get("BLOCK", 0) / boss_attacks * 100

        # 计算真正的理论值：使用Round Table
        if boss_mecha and challenger_mecha:
            from src.combat.resolver import AttackTableResolver
            from src.models import BattleContext

            boss_weapon = boss_mecha.weapons[0] if boss_mecha.weapons else None
            if boss_weapon:
                test_ctx = BattleContext(
                    round_number=1, distance=3000,
                    mecha_a=boss_mecha, mecha_b=challenger_mecha,
                    weapon=boss_weapon
                )
                test_segments = AttackTableResolver.calculate_attack_table_segments(test_ctx)
                theory_dodge = test_segments.get('DODGE', {}).get('rate', 0)
                theory_parry = test_segments.get('PARRY', {}).get('rate', 0)
                theory_block = test_segments.get('BLOCK', {}).get('rate', 0)
            else:
                theory_dodge = base_dodge + base_precision
                theory_parry = base_parry
                theory_block = base_block
        else:
            theory_dodge = base_dodge + base_precision
            theory_parry = base_parry
            theory_block = base_block

        print(f"\n【防御效率】")
        print(f"  综合防御率: {total_def/boss_attacks*100:.2f}%")
        print(f"  闪避率: {actual_dodge_rate:.2f}% (理论值: {theory_dodge:.2f}%)")
        print(f"  招架率: {actual_parry_rate:.2f}% (理论值: {theory_parry:.2f}%)")
        print(f"  格挡率: {actual_block_rate:.2f}% (理论值: {theory_block:.2f}%)")
        print(f"  未命中率: {boss_results.get('MISS', 0)/boss_attacks*100:.2f}%")

    # 生存统计
    if challenger_name and challenger_mecha:
        win_stats = [s for s in all_stats if s.winner == challenger_name]
        print_survival_stats(win_stats, challenger_mecha, challenger_name)

    # 资源消耗
    avg_taken = sum(s.total_damage_taken for s in all_stats) / total_battles
    avg_en = sum(s.total_en_consumed for s in all_stats) / total_battles
    avg_en_regened = sum(s.total_en_regened for s in all_stats) / total_battles

    print(f"\n【承受伤害】")
    print(f"  场均承受伤害: {avg_taken:,.0f} (最高: {max(s.total_damage_taken for s in all_stats):,}, "
          f"最低: {min(s.total_damage_taken for s in all_stats):,})")
    if avg_rounds > 0:
        print(f" 平均每回合承受: {avg_taken/avg_rounds:,.1f}")

    print(f"\n【资源消耗】")
    print(f"  场均EN消耗: {avg_en:,.1f}")
    print(f"  场均EN回复: {avg_en_regened:,.1f}")
    print(f"  EN净消耗: {avg_en - avg_en_regened:,.1f}")
    if avg_rounds > 0:
        print(f"  每回合EN消耗: {avg_en/avg_rounds:.1f}")
        print(f"  每回合EN回复: {avg_en_regened/avg_rounds:.1f}")

    # 技能统计
    print_skill_statistics(all_stats, total_battles, challenger_obj)

    print("\n" + "="*80)


# ============================================================================
# 6. 主程序
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="数值验证木桩模拟",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python sim_challenge_boss.py              # 运行 10 轮测试（默认）
  python sim_challenge_boss.py --rounds 20 # 运行 20 轮测试
  python sim_challenge_boss.py --verbose   # 显示详细战斗过程
  python sim_challenge_boss.py --quiet     # 静默模式，只显示统计报告
        """
    )
    parser.add_argument("--rounds", "-r", type=int, default=10, help="测试轮数 (默认: 10)")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细战斗过程")
    parser.add_argument("--quiet", "-q", action="store_true", help="静默模式，只显示统计报告")

    args = parser.parse_args()
    challenger = BossChallenger(verbose=args.verbose)

    # Boss配置
    if not args.quiet:
        print("\n" + "="*80)
        print("【木桩测试配置】")
        print("="*80)

    print(f"\n【Boss 配置】({BOSS_CONFIG['name']})")
    print(f"  HP: {BOSS_CONFIG['hp']:,}")
    print(f"  EN: {BOSS_CONFIG['en']:,}")
    print(f"  护甲: {BOSS_CONFIG['defense']:,}")
    print(f"  机动: {BOSS_CONFIG['mobility']:,}")
    print(f"  命中/精准/暴击: {BOSS_CONFIG['hit_rate']}% / {BOSS_CONFIG['precision']}% / {BOSS_CONFIG['crit_rate']}%")
    dodge_rate = BOSS_CONFIG['dodge_rate'] if BOSS_CONFIG['dodge_rate'] is not None else BOSS_CONFIG['mobility'] * 0.1
    print(f"  躲闪/招架/格挡: {dodge_rate}% / {BOSS_CONFIG['parry_rate']}% / {BOSS_CONFIG['block_rate']}%")

    # 挑战者配置
    mecha_config = challenger.loader.get_mecha_config(CHALLENGER_CONFIG['mecha_id'])
    print(f"\n【挑战者配置】({mecha_config.name})")
    print(f"  机体ID: {CHALLENGER_CONFIG['mecha_id']}")

    # 创建测试实例查看快照属性
    test_mecha = challenger.create_challenger()

    def format_with_mod(final_val, base_val, is_float=False):
        modifier = final_val - base_val
        sign = "+" if modifier > 0 else "" if modifier == 0 else "-"
        if is_float:
            return f"{final_val} ({sign}{modifier:.1f})"
        return f"{final_val:,} ({sign}{modifier:,})"

    print(f"\n【挑战者快照属性】")
    print(f"  HP: {format_with_mod(test_mecha.final_max_hp, mecha_config.init_hp)}")
    print(f"  EN: {format_with_mod(test_mecha.final_max_en, mecha_config.init_en)}")
    print(f"  护甲: {format_with_mod(test_mecha.final_armor, mecha_config.init_armor)}")
    print(f"  机动: {format_with_mod(test_mecha.final_mobility, mecha_config.init_mobility)}")
    print(f"  命中: {format_with_mod(test_mecha.final_hit, mecha_config.init_hit, True)}%")
    print(f"  精准: {format_with_mod(test_mecha.final_precision, mecha_config.init_precision, True)}%")
    print(f"  暴击: {format_with_mod(test_mecha.final_crit, mecha_config.init_crit, True)}%")
    print(f"  躲闪: {format_with_mod(test_mecha.final_dodge, mecha_config.init_dodge, True)}%")
    print(f"  招架: {format_with_mod(test_mecha.final_parry, mecha_config.init_parry, True)}%")
    print(f"  格挡: {format_with_mod(test_mecha.final_block, mecha_config.init_block, True)}%")
    print(f"  EN回能: {format_with_mod(test_mecha.final_en_regen_rate, mecha_config.init_en_regen_rate, True)}% + {format_with_mod(test_mecha.final_en_regen_fixed, mecha_config.init_en_regen_fixed)}")

    # 测试设置
    print(f"\n【测试设置】")
    print(f"  测试轮数: {args.rounds}")
    print(f"  详细输出: {'是' if args.verbose else '否'}")
    print(f"  静默模式: {'是' if args.quiet else '否'}")

    # 运行测试
    all_stats: List[BattleStatistics] = []
    for i in range(1, args.rounds + 1):
        stats = challenger.run_challenge(i, quiet=args.quiet)
        all_stats.append(stats)
        if not args.verbose and not args.quiet and i < args.rounds and sys.stdin.isatty():
            try:
                input(f"\n第 {i}/{args.rounds} 轮完成，按 Enter 继续...")
            except (EOFError, KeyboardInterrupt):
                pass

    # 打印统计分析
    if not args.quiet:
        mecha_config = challenger.loader.get_mecha_config(CHALLENGER_CONFIG['mecha_id'])
        challenger_mecha = challenger.create_challenger()
        boss_mecha = challenger.create_boss()
        print_statistics(all_stats, challenger_mecha, mecha_config, challenger_obj=challenger, boss_mecha=boss_mecha)
    else:
        # 静默模式：只输出简要统计
        print(f"\n{'='*80}")
        print(f"测试完成: {args.rounds} 轮")
        wins = sum(1 for s in all_stats if s.winner != BOSS_CONFIG['name'])
        print(f"胜利次数: {wins}/{args.rounds} ({wins/args.rounds*100:.1f}%)")
        print(f"平均回合数: {sum(s.rounds for s in all_stats) / len(all_stats):.1f}")
        print(f"平均输出: {sum(s.total_damage_dealt for s in all_stats) / len(all_stats):,.0f}")
        print(f"{'='*80}")


if __name__ == "__main__":
    main()
