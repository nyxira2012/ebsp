"""
验证特定数值下的圆桌判定结果 (针对用户问题: A有80命中 20暴击, B有10躲闪 10招架 10格挡)
"""

import sys
import os
import io
import random
from collections import Counter

# 确保导入路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Windows UTF-8 支持
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.models import Mecha, Pilot, Weapon, WeaponType, BattleContext, AttackResult
from src.combat.resolver import AttackTableResolver
from src.config import Config

def run_specific_logic_test(iterations=2000):
    print(f"执行 {iterations} 次模拟攻击判定 (A: 50命中/50暴击 vs B: 30躲闪/40招架/10格挡)\n")

    # 强制修改 Config 以精确匹配用户要求的 30/40/10
    Config.BASE_MISS_RATE = 12.0
    Config.BASE_DODGE_RATE = 30.0
    Config.BASE_PARRY_RATE = 40.0
    Config.BASE_BLOCK_RATE = 10.0

    # 构造攻击方
    p_a = Pilot(id="a", name="A", stat_shooting=100, stat_melee=100, stat_awakening=100, stat_defense=100, stat_reaction=100)
    p_a.weapon_proficiency = 1000 
    
    m_a = Mecha(
        id="m_a", name="A_Mecha", pilot=p_a,
        max_hp=1000, current_hp=1000, max_en=100, current_en=100,
        mobility=100, defense_level=1000,
        hit_rate=50.0, precision=0.0, crit_rate=50.0,
        dodge_rate=0.0, parry_rate=0.0, block_rate=0.0
    )
    m_a.block_value = 0
    m_a.weapons = []
    
    # 构造防御方
    p_b = Pilot(id="b", name="B", stat_shooting=100, stat_melee=100, stat_awakening=100, stat_defense=100, stat_reaction=100)
    p_b.mecha_proficiency = 4000 
    
    m_b = Mecha(
        id="m_b", name="B_Mecha", pilot=p_b,
        max_hp=1000, current_hp=1000, max_en=100, current_en=100,
        mobility=100, defense_level=1000,
        hit_rate=0.0, precision=0.0, crit_rate=0.0,
        dodge_rate=30.0, parry_rate=40.0, block_rate=10.0
    )
    m_b.block_value = 100
    m_b.weapons = []

    results = []
    weapon = Weapon(id="w", name="Test", weapon_type=WeaponType.MELEE, power=1000, en_cost=0, range_min=0, range_max=1000)

    for i in range(iterations):
        ctx = BattleContext(attacker=m_a, defender=m_b, weapon=weapon, round_number=1, distance=1000)
        res, dmg = AttackTableResolver.resolve_attack(ctx)
        results.append(res.name)

    stats = Counter(results)
    
    print("-" * 40)
    print(f"{'判定结果':<15} | {'触发次数':<10} | {'百分比'}")
    print("-" * 40)
    for res_name in ["MISS", "DODGE", "PARRY", "BLOCK", "CRIT", "HIT"]:
        count = stats.get(res_name, 0)
        print(f"{res_name:<15} | {count:<10} | {count/iterations*100:.1f}%")
    print("-" * 40)
    
    print("\n[当前逻辑分析 - 溢出挤压效应]")
    print("理论圆桌分片 (总计 130%):")
    print("1. MISS: 0%  (50命中 挤掉 12未命中)")
    print("2. DODGE: 30% [0-30]")
    print("3. PARRY: 40% [30-70]")
    print("4. BLOCK: 10% [70-80]")
    print("5. CRIT: 50%  [80-130] -> 实机只占 [80-100]，即 20%")
    print("6. HIT: 剩余  -> 已经被完全挤出圆桌，0%")
    print("\n结论：当总和超过 100% 时，排在后面的 Crit 被挤压，HIT 彻底消失。")

if __name__ == "__main__":
    run_specific_logic_test(2000)
