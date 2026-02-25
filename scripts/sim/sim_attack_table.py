"""
圆桌判定统计测试
=================
验证攻击判定表（Attack Table）在不同数值分布下的表现。

测试场景：
1. 标准场景：50命中/50暴击 vs 30躲闪/40招架/10格挡
2. 高命中场景：80命中/20暴击 vs 10躲闪/10招架/10格挡
3. 高闪避场景：30命中/30暴击 vs 50躲闪/30招架/20格挡
4. 极端压制：100命中 vs 各种防御
5. 边界条件：极低命中率

使用方法：
    python sim_attack_table.py              # 运行所有场景
    python sim_attack_table.py --scenario 1 # 只运行场景1
    python sim_attack_table.py --iterations 5000  # 增加迭代次数
"""

import sys
import os
import io
import random
import argparse
from collections import Counter
from typing import Tuple, List

# 确保导入路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Windows UTF-8 支持
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.models import (
    Mecha, Pilot, Weapon, WeaponType,
    BattleContext, AttackResult
)
from src.combat.resolver import AttackTableResolver
from src.config import Config

# ============================================================================
# 测试场景配置
# ============================================================================

TEST_SCENARIOS = {
    1: {
        "name": "标准场景",
        "description": "命中+50%/暴击+50% vs 躲闪+30%/招架+40%/格挡+10%",
        "attacker": {"hit_bonus": 50.0, "crit_bonus": 50.0},
        "defender": {"dodge_bonus": 30.0, "parry_bonus": 40.0, "block_bonus": 10.0},
    },
    2: {
        "name": "高命中场景",
        "description": "命中+80%/暴击+20% vs 躲闪+10%/招架+10%/格挡+10%",
        "attacker": {"hit_bonus": 80.0, "crit_bonus": 20.0},
        "defender": {"dodge_bonus": 10.0, "parry_bonus": 10.0, "block_bonus": 10.0},
    },
    3: {
        "name": "高闪避场景",
        "description": "命中+30%/暴击+30% vs 躲闪+50%/招架+30%/格挡+20%",
        "attacker": {"hit_bonus": 30.0, "crit_bonus": 30.0},
        "defender": {"dodge_bonus": 50.0, "parry_bonus": 30.0, "block_bonus": 20.0},
    },
    4: {
        "name": "极端压制场景",
        "description": "命中+100%/暴击+30% vs 躲闪+30%/招架+40%/格挡+10%",
        "attacker": {"hit_bonus": 100.0, "crit_bonus": 30.0},
        "defender": {"dodge_bonus": 30.0, "parry_bonus": 40.0, "block_bonus": 10.0},
    },
    5: {
        "name": "边界条件场景",
        "description": "命中+10%/暴击+5% vs 躲闪+40%/招架+30%/格挡+20%",
        "attacker": {"hit_bonus": 10.0, "crit_bonus": 5.0},
        "defender": {"dodge_bonus": 40.0, "parry_bonus": 30.0, "block_bonus": 20.0},
    },
}

# ============================================================================
# 测试函数
# ============================================================================

def create_test_mechas(
    attacker_stats: dict,
    defender_stats: dict
) -> Tuple[Mecha, Mecha]:
    """创建测试用的攻防机体。

    该函数根据给定的统计数据创建攻击方和防御方的机体实例，
    用于圆桌判定测试。注意：stats中的值是加成值（bonus），会在基础值上增加。

    Args:
        attacker_stats (dict): 攻击方的额外统计数据，包括命中加成、暴击加成等
        defender_stats (dict): 防御方的额外统计数据，包括闪避、招架、格挡加成等

    Returns:
        Tuple[Mecha, Mecha]: 返回一个元组，包含攻击方机体和防御方机体
    """

    # 攻击方驾驶员属性
    attacker_weapon_prof = 1000  # 满熟练度

    # 命中加成（在基础命中上加成）
    hit_bonus = attacker_stats.get("hit_bonus", 0.0)
    crit_bonus = attacker_stats.get("crit_bonus", 0.0)

    m_a = Mecha(
        instance_id="m_a", mecha_name="Attacker",
        final_max_hp=1000, current_hp=1000,
        final_max_en=100, current_en=100,
        final_mobility=100, final_armor=1000,
        final_hit=hit_bonus,
        final_precision=0.0,
        final_crit=crit_bonus,
        final_dodge=0.0, final_parry=0.0, final_block=0.0,
        # 备份驾驶员属性，供 MockPilot 使用
        pilot_stats_backup={
            'stat_shooting': 100,
            'stat_melee': 100,
            'stat_awakening': 100,
            'stat_defense': 100,
            'stat_reaction': 100,
            'weapon_proficiency': attacker_weapon_prof,
            'mecha_proficiency': 2000
        }
    )
    m_a.block_reduction = 0
    m_a.weapons = []

    # 防御方驾驶员属性
    defender_mecha_prof = 4000  # 满熟练度

    # 防御加成（在基础防御上加成）
    dodge_bonus = defender_stats.get("dodge_bonus", 0.0)
    parry_bonus = defender_stats.get("parry_bonus", 0.0)
    block_bonus = defender_stats.get("block_bonus", 0.0)

    m_b = Mecha(
        instance_id="m_b", mecha_name="Defender",
        final_max_hp=1000, current_hp=1000,
        final_max_en=100, current_en=100,
        final_mobility=100, final_armor=1000,
        final_hit=0.0, final_precision=0.0, final_crit=0.0,
        final_dodge=dodge_bonus,
        final_parry=parry_bonus,
        final_block=block_bonus,
        # 备份驾驶员属性，供 MockPilot 使用
        pilot_stats_backup={
            'stat_shooting': 100,
            'stat_melee': 100,
            'stat_awakening': 100,
            'stat_defense': 100,
            'stat_reaction': 100,
            'weapon_proficiency': 500,
            'mecha_proficiency': defender_mecha_prof
        }
    )
    m_b.block_reduction = 100
    m_b.weapons = []

    return m_a, m_b

def run_simulation(
    scenario_id: int,
    iterations: int = 2000
) -> Tuple[Counter, Mecha, Mecha, Weapon]:
    """运行指定场景的圆桌判定模拟。

    该函数执行指定场景的多次模拟，统计不同攻击结果的分布情况，
    用于验证圆桌判定机制的正确性。

    Args:
        scenario_id (int): 测试场景的ID，对应TEST_SCENARIOS中的键
        iterations (int): 模拟迭代次数，默认为2000次

    Returns:
        Tuple[Counter, Mecha, Mecha, Weapon]: 返回一个元组，包含：
            - Counter: 统计结果，记录各种攻击结果的发生次数
            - Mecha: 攻击方机体实例
            - Mecha: 防御方机体实例
            - Weapon: 用于测试的武器实例
    """

    scenario = TEST_SCENARIOS[scenario_id]

    print(f"\n{'='*70}")
    print(f"【场景 {scenario_id}: {scenario['name']}】")
    print(f"{'='*70}")
    print(f"描述: {scenario['description']}")
    print(f"迭代次数: {iterations:,}")
    print(f"\n说明:")
    print(f"  - 命中/暴击/防御数值为在基础值上的加成")
    print(f"  - 攻击方武器熟练度: 1000 (满值)")
    print(f"  - 防御方机体熟练度: 4000 (满值)")
    print(f"  - 精准: 0 (无削减)")

    # 创建机体
    m_a, m_b = create_test_mechas(scenario["attacker"], scenario["defender"])

    # 创建武器
    weapon = Weapon(
        uid="w_uid", definition_id="w", name="Test Weapon",
        type=WeaponType.MELEE,
        final_power=1000, en_cost=0,
        range_min=0, range_max=1000,
        will_req=0, anim_id="default_anim"
    )

    # 运行模拟
    results = []
    for _ in range(iterations):
        ctx = BattleContext(
            mecha_a=m_a, mecha_b=m_b, weapon=weapon,
            round_number=1, distance=1000
        )
        res, _ = AttackTableResolver.resolve_attack(ctx)
        results.append(res.name)

    return Counter(results), m_a, m_b, weapon

def print_statistics(stats: Counter, iterations: int, segments: dict | None = None):
    """打印圆桌判定统计结果。

    该函数以表格形式输出攻击结果的统计信息，包括实际发生次数、百分比，
    并可选择性地与理论值进行比较。

    Args:
        stats (Counter): 统计结果，记录各种攻击结果的发生次数
        iterations (int): 模拟的迭代总次数
        segments (dict | None): 圆桌判定表理论值，用于与实际结果比较，默认为None
    """

    print(f"\n{'─'*70}")
    print(f"{'判定结果':<9} | {'触发次数':<6} | {' 百分比':<6} | {'理论值'}")
    print(f"{'─'*70}")

    for res_name in ["MISS", "DODGE", "PARRY", "BLOCK", "CRIT", "HIT"]:
        count = stats.get(res_name, 0)
        percentage = count / iterations * 100
        theoretical = f"{segments[res_name]['rate']:.1f}%" if segments and res_name in segments else "-"
        print(f"{res_name:<12} | {count:<10} | {percentage:>6.2f}%   | {theoretical:>8}")

    print(f"{'─'*70}")

def analyze_attack_table(
    mecha_a: Mecha,
    mecha_b: Mecha,
    weapon: Weapon
):
    """分析圆桌判定表的理论分布。

    该函数使用项目提供的公共 API 获取圆桌判定表的理论值，
    通过分析各种判定因素（如命中、闪避、招架等）来了解
    攻击结果的概率分布，确保模拟器与实际游戏逻辑完全一致。

    Args:
        mecha_a (Mecha): 攻击方机体
        mecha_b (Mecha): 防御方机体
        weapon (Weapon): 攻击使用的武器
    """

    print(f"\n【理论分析】")

    # 创建战场上下文
    ctx = BattleContext(
        mecha_a=mecha_a,
        mecha_b=mecha_b,
        weapon=weapon,
        round_number=1,
        distance=1000
    )

    # 使用项目提供的公共 API 获取圆桌判定表的理论分布
    # 这样确保模拟器与实际游戏逻辑完全一致
    segments = AttackTableResolver.calculate_attack_table_segments(ctx)

    # 打印各段的详细信息
    from src.combat.calculator import CombatCalculator
    from src.config import Config

    # === MISS段详情 ===
    weapon_proficiency = mecha_a.pilot_stats_backup.get('weapon_proficiency', 500)
    base_miss = CombatCalculator.calculate_proficiency_miss_penalty(weapon_proficiency)
    hit_bonus = mecha_a.final_hit

    print(f"\n--- MISS段 ---")
    print(f"  基础MISS惩罚: {base_miss:.1f}% (武器熟练度 {weapon_proficiency})")
    print(f"  命中加成: -{hit_bonus:.1f}%")
    if 'MISS' in segments:
        print(f"  最终MISS率: {segments['MISS']['rate']:.1f}%")
    else:
        print(f"  最终MISS率: 0.0% (被命中加成完全抵消)")

    # === 防御段详情 ===
    mecha_proficiency = mecha_b.pilot_stats_backup.get('mecha_proficiency', 2000)
    precision = mecha_a.final_precision
    precision_reduction = CombatCalculator.calculate_precision_reduction(precision)

    if 'DODGE' in segments:
        dodge_base = CombatCalculator.calculate_proficiency_defense_ratio(
            mecha_proficiency, Config.BASE_DODGE_RATE
        )
        dodge_bonus = mecha_b.final_dodge
        print(f"\n--- DODGE段 ---")
        print(f"  基础躲闪: {Config.BASE_DODGE_RATE:.1f}% (机体熟练度 {mecha_proficiency}) -> {dodge_base:.1f}%")
        print(f"  躲闪加成: +{dodge_bonus:.1f}%")
        print(f"  精准削减: {precision_reduction*100:.1f}%")
        print(f"  最终躲闪率: {segments['DODGE']['rate']:.1f}%")

    if 'PARRY' in segments:
        parry_base = CombatCalculator.calculate_proficiency_defense_ratio(
            mecha_proficiency, Config.BASE_PARRY_RATE
        )
        parry_bonus = mecha_b.final_parry
        print(f"\n--- PARRY段 ---")
        print(f"  基础招架: {Config.BASE_PARRY_RATE:.1f}% (机体熟练度 {mecha_proficiency}) -> {parry_base:.1f}%")
        print(f"  招架加成: +{parry_bonus:.1f}%")
        print(f"  精准削减: {precision_reduction*100:.1f}%")
        print(f"  最终招架率: {segments['PARRY']['rate']:.1f}% (上限50%)")

    if 'BLOCK' in segments:
        block_bonus = mecha_b.final_block
        print(f"\n--- BLOCK段 ---")
        print(f"  基础格挡: {Config.BASE_BLOCK_RATE:.1f}%")
        print(f"  格挡加成: +{block_bonus:.1f}%")
        print(f"  精准削减: {precision_reduction*100:.1f}%")
        print(f"  最终格挡率: {segments['BLOCK']['rate']:.1f}% (上限80%)")

    if 'CRIT' in segments:
        crit_bonus = mecha_a.final_crit
        print(f"\n--- CRIT段 ---")
        print(f"  基础暴击: {Config.BASE_CRIT_RATE:.1f}%")
        print(f"  暴击加成: +{crit_bonus:.1f}%")
        print(f"  最终暴击率: {segments['CRIT']['rate']:.1f}%")

    if 'HIT' in segments:
        print(f"\n--- HIT段 ---")
        print(f"  普通命中: {segments['HIT']['rate']:.1f}% (剩余空间)")

    # 打印圆桌分布
    print(f"\n{'='*70}")
    print("【圆桌判定表分布】")
    print(f"{'='*70}")

    total = segments['total']
    print(f"总计: {min(100, total):.1f}%\n")

    for name in ["MISS", "DODGE", "PARRY", "BLOCK", "CRIT", "HIT"]:
        if name in segments:
            seg = segments[name]
            print(f"  {name:<6}: {seg['rate']:>5.1f}%  [ {seg['start']:>5.1f} - {seg['end']:>5.1f}]")

    # 溢出警告
    if total > 100:
        print(f"\n⚠️  警告: 圆桌总比例 ({total:.1f}%) 超过 100%!")
        print(f"   后续的判定会被挤压（HIT 可能消失甚至CRIT被压缩）")
    elif total < 100:
        print(f"\n✓ 剩余空间: {100 - total:.1f}% 分配给HIT")

def run_all_scenarios(iterations: int = 2000):
    """运行所有预定义的测试场景。

    该函数依次执行所有的测试场景，每个场景都会运行指定次数的模拟，
    并输出统计结果和理论分析，用于全面验证圆桌判定机制。

    Args:
        iterations (int): 每个场景的模拟迭代次数，默认为2000次
    """

    print("\n" + "="*70)
    print("圆桌判定统计测试 - 开始执行")
    print("="*70)

    for scenario_id in TEST_SCENARIOS:
        # 运行模拟
        stats, m_a, m_b, weapon = run_simulation(scenario_id, iterations)

        # 获取理论值
        ctx = BattleContext(
            mecha_a=m_a, mecha_b=m_b, weapon=weapon,
            round_number=1, distance=1000
        )
        segments = AttackTableResolver.calculate_attack_table_segments(ctx)

        # 打印统计（包含理论值）
        print_statistics(stats, iterations, segments)

        # 理论分析（使用项目提供的公共 API）
        analyze_attack_table(m_a, m_b, weapon)

    print("\n" + "="*70)
    print("所有场景测试完成!")
    print("="*70)

def run_single_scenario(scenario_id: int, iterations: int = 2000):
    """运行单个指定的测试场景。

    该函数执行指定ID的测试场景，运行指定次数的模拟，
    并输出统计结果和理论分析。

    Args:
        scenario_id (int): 要运行的测试场景ID
        iterations (int): 模拟迭代次数，默认为2000次
    """

    if scenario_id not in TEST_SCENARIOS:
        print(f"错误: 场景 {scenario_id} 不存在")
        print(f"可用场景: {list(TEST_SCENARIOS.keys())}")
        return

    # 运行模拟
    stats, m_a, m_b, weapon = run_simulation(scenario_id, iterations)

    # 获取理论值
    ctx = BattleContext(
        mecha_a=m_a, mecha_b=m_b, weapon=weapon,
        round_number=1, distance=1000
    )
    segments = AttackTableResolver.calculate_attack_table_segments(ctx)

    # 打印统计（包含理论值）
    print_statistics(stats, iterations, segments)

    # 理论分析（使用项目提供的公共 API）
    analyze_attack_table(m_a, m_b, weapon)

    print("\n" + "="*70)
    print("测试完成!")
    print("="*70)

# ============================================================================
# 主程序
# ============================================================================

def main():
    """圆桌判定统计测试的主函数。

    该函数解析命令行参数，根据参数决定是运行单个指定的测试场景
    还是运行所有测试场景，然后执行相应的测试并输出结果。
    支持通过命令行参数指定要运行的场景和迭代次数。
    """
    parser = argparse.ArgumentParser(
        description="圆桌判定统计测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
测试场景:
  1 - 标准场景 (50命中/50暴击 vs 30躲闪/40招架/10格挡)
  2 - 高命中场景 (80命中/20暴击 vs 10躲闪/10招架/10格挡)
  3 - 高闪避场景 (30命中/30暴击 vs 50躲闪/30招架/20格挡)
  4 - 极端压制场景 (100命中/30暴击 vs 30躲闪/40招架/10格挡)
  5 - 边界条件场景 (10命中/5暴击 vs 40躲闪/30招架/20格挡)

示例:
  python sim_attack_table.py                # 运行所有场景 (默认 2000 次迭代)
  python sim_attack_table.py --scenario 1   # 只运行场景 1
  python sim_attack_table.py --iterations 5000  # 增加迭代次数到 5000
        """
    )

    parser.add_argument(
        "--scenario", "-s",
        type=int,
        choices=list(TEST_SCENARIOS.keys()),
        help="运行指定场景 (不指定则运行所有)"
    )
    parser.add_argument(
        "--iterations", "-n",
        type=int,
        default=2000,
        help="每次模拟的迭代次数 (默认: 2000)"
    )

    args = parser.parse_args()

    if args.scenario:
        run_single_scenario(args.scenario, args.iterations)
    else:
        run_all_scenarios(args.iterations)

if __name__ == "__main__":
    main()
