
import sys
from pathlib import Path
import random

# 设置项目根目录
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.models import MechaSnapshot, WeaponSnapshot, WeaponType
from src.combat.engine import BattleSimulator

def create_heavy_mecha():
    """创建一个重装格斗型机体"""
    w1 = WeaponSnapshot(
        uid="w_heavy_blade",
        definition_id="斩舰刀",
        name="超重型斩舰刀",
        type=WeaponType.MELEE,
        final_power=4200,
        range_min=0,
        range_max=1500,
        en_cost=40,
        will_req=110,
        anim_id="melee_slash_heavy",
        tags=["heavy", "blade"]
    )
    w2 = WeaponSnapshot(
        uid="w_heavy_fist",
        definition_id="破甲拳",
        name="液压强化破甲拳",
        type=WeaponType.MELEE,
        final_power=3200,
        range_min=0,
        range_max=1000,
        en_cost=10,
        will_req=100,
        anim_id="melee_strike_blunt",
        tags=["blunt", "impact"]
    )
    
    return MechaSnapshot(
        instance_id="RX-HG-01",
        mecha_name="[重装宿命]",
        final_max_hp=8500,
        current_hp=8500,
        final_max_en=250,
        current_en=250,
        current_will=120,
        final_armor=1800,
        final_mobility=90,
        final_block=40.0,
        block_reduction=1500,
        weapons=[w1, w2],
        pilot_stats_backup={"stat_defense": 180, "stat_melee": 220, "stat_shooting": 140}
    )

def create_sniper_mecha():
    """创建一个高能狙击型机体"""
    w1 = WeaponSnapshot(
        uid="w_mega_sniper",
        definition_id="米加粒子枪",
        name="米加粒子长程狙击枪",
        type=WeaponType.SHOOTING,
        final_power=4800,
        range_min=2000,
        range_max=8000,
        en_cost=70,
        will_req=115,
        anim_id="shoot_mega_cannon",
        tags=["beam", "massive", "mega"]
    )
    w2 = WeaponSnapshot(
        uid="w_vulcan",
        definition_id="火神炮",
        name="头部火神炮系统",
        type=WeaponType.SHOOTING,
        final_power=1200,
        range_min=0,
        range_max=1500,
        en_cost=0,
        will_req=100,
        anim_id="shoot_vulcan",
        tags=["rapid", "vulcan"]
    )
    
    return MechaSnapshot(
        instance_id="RX-SP-02",
        mecha_name="[白炽死神]",
        final_max_hp=5500,
        current_hp=5500,
        final_max_en=300,
        current_en=300,
        current_will=125,
        final_armor=1100,
        final_mobility=160,
        final_dodge=45.0,
        weapons=[w1, w2],
        pilot_stats_backup={"stat_defense": 120, "stat_melee": 130, "stat_shooting": 240}
    )

def run_presentation_demo():
    print("="*80)
    print(" 战斗演示：[重装宿命] VS [白炽死神] ")
    print(" 风格：超级机器人大战/高达小说风格文字演出")
    print("="*80)
    print()

    mecha_heavy = create_heavy_mecha()
    mecha_sniper = create_sniper_mecha()

    # 初始化模拟器，启用演出
    sim = BattleSimulator(mecha_heavy, mecha_sniper, enable_presentation=True)

    # 模拟三个不同距离的交战场景
    scenarios = [
        {"desc": "场景1：远距离狙击模式", "distance": 5000},
        {"desc": "场景2：中近距离缠斗模式", "distance": 1200},
        {"desc": "场景3：零距离决战模式", "distance": 500}
    ]

    for i, scene in enumerate(scenarios, 1):
        print(f"\n>>> {scene['desc']} (距离: {scene['distance']})")
        print("-" * 50)
        
        # 强制设置距离并模拟一个回合
        # 注意：run_battle 会重置 round_number 等，我们这里手动执行 _execute_round
        sim.round_number = i
        
        # 确定先手方（这里为了演示，手动交替）
        if i % 2 == 1:
            # 奇数回合：狙击型先手 (远距离优势)
            sim._execute_attack(mecha_sniper, mecha_heavy, scene['distance'], is_first=True)
            if mecha_heavy.is_alive():
                sim._execute_attack(mecha_heavy, mecha_sniper, scene['distance'], is_first=False)
        else:
            # 偶数回合：重装型先手
            sim._execute_attack(mecha_heavy, mecha_sniper, scene['distance'], is_first=True)
            if mecha_sniper.is_alive():
                sim._execute_attack(mecha_sniper, mecha_heavy, scene['distance'], is_first=False)
        
        print("-" * 50)

    print("\n演示结束。")

if __name__ == "__main__":
    run_presentation_demo()
