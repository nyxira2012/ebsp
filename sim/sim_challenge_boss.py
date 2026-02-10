"""
木桩挑战测试 - 打爆 Boss 木桩
===============================
验证：
1. 大规模回合累积：验证死斗机制能否支持超长战斗
2. 随机技能组合稳定性：每轮随机抽取 2 精神 + 3 特性
3. 伤害累积：验证在极端属性叠加下的伤害输出
4. 多种难度 Boss 挑战

使用方法：
    python sim_challenge_boss.py              # 默认难度
    python sim_challenge_boss.py --hard       # 困难模式
    python sim_challenge_boss.py --extreme    # 极限模式
"""

import sys
import os
import io
import random
import argparse
from typing import List

# 确保导入路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Windows UTF-8 支持
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.models import Mecha, Pilot, Weapon, WeaponType, BattleContext, Effect
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
        # 防止死循环，设置硬上限 1000 回合
        if ctx.round_number < 1000:
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
# 2. Boss 配置
# ============================================================================

BOSS_CONFIGS = {
    "easy": {
        "name": "新手 Boss",
        "hp": 100000,
        "defense": 1500,
        "mobility": 100,
        "en": 300,
    },
    "normal": {
        "name": "标准 Boss",
        "hp": 500000,
        "defense": 2000,
        "mobility": 120,
        "en": 400,
    },
    "hard": {
        "name": "困难 Boss",
        "hp": 1000000,
        "defense": 2500,
        "mobility": 150,
        "en": 500,
    },
    "extreme": {
        "name": "极限 Boss",
        "hp": 5000000,
        "defense": 3500,
        "mobility": 200,
        "en": 1000,
    },
}

# ============================================================================
# 3. 挑战者类
# ============================================================================

class BossChallenger:
    """Boss 挑战者"""

    def __init__(self, difficulty: str = "normal"):
        self.loader = DataLoader()
        self.loader.load_all()

        self.difficulty = difficulty
        self.boss_config = BOSS_CONFIGS[difficulty]

        # 加载所有技能 ID
        import json
        with open("data/skills.json", "r", encoding="utf-8") as f:
            self.all_skill_ids = list(json.load(f).keys())

        self.spirits = [s for s in self.all_skill_ids if s.startswith("spirit_")]
        self.traits = [t for t in self.all_skill_ids if t.startswith("trait_")]

        print(f"\n{'='*70}")
        print(f"【Boss 挑战模式】难度: {self.boss_config['name']}")
        print(f"{'='*70}")
        print(f"Boss HP: {self.boss_config['hp']:,}")
        print(f"Boss 防御: {self.boss_config['defense']}")
        print(f"Boss 机动: {self.boss_config['mobility']}")
        print(f"Boss EN: {self.boss_config['en']}")

    def create_boss(self) -> Mecha:
        """创建 Boss 机体"""
        pilot = Pilot(
            id="boss_pilot", name="Boss Pilot",
            stat_shooting=150, stat_melee=150, stat_reaction=150,
            stat_awakening=150, stat_defense=150
        )

        boss = Mecha(
            id="boss", name=self.boss_config['name'],
            pilot=pilot,
            max_hp=self.boss_config['hp'],
            current_hp=self.boss_config['hp'],
            max_en=self.boss_config['en'],
            current_en=self.boss_config['en'],
            hit_rate=20.0, precision=15.0, crit_rate=10.0,
            dodge_rate=self.boss_config['mobility'] * 0.1,
            parry_rate=15.0, block_rate=15.0,
            defense_level=self.boss_config['defense'],
            mobility=self.boss_config['mobility']
        )

        # Boss 武器
        boss.weapons = [
            Weapon(
                id="boss_weapon", name="Boss Attack",
                weapon_type=WeaponType.HEAVY,
                power=self.boss_config['hp'] * 0.01,  # 每次造成 1% 最大 HP 的伤害
                en_cost=0,
                range_min=0, range_max=10000
            )
        ]

        return boss

    def create_challenger(self) -> Mecha:
        """创建挑战者机体"""
        # 使用阿姆罗 + 高达作为基底
        attacker = self.loader.get_mecha("mech_rx78")

        # 强化挑战者
        god_weapon = Weapon(
            id="w_god", name="上帝之雷",
            weapon_type=WeaponType.HEAVY,
            power=50000,  # 超高伤害武器
            en_cost=0,
            range_min=0, range_max=10000
        )
        attacker.weapons = [god_weapon]
        attacker.current_hp = attacker.max_hp
        attacker.current_en = attacker.max_en
        attacker.effects = []  # 清空

        return attacker

    def apply_random_skills(self, mecha: Mecha):
        """应用随机技能组合"""
        # 随机分配 2-3 精神
        spirit_count = 3 if self.difficulty in ["hard", "extreme"] else 2
        selected_spirits = random.sample(self.spirits, min(spirit_count, len(self.spirits)))

        # 随机分配 3-5 特性
        trait_count = 5 if self.difficulty == "extreme" else 3
        selected_traits = random.sample(self.traits, min(trait_count, len(self.traits)))

        print(f"\n随机抽取的精神 ({len(selected_spirits)}):")
        for s in selected_spirits:
            print(f"  - {s}")

        print(f"\n随机抽取的特性 ({len(selected_traits)}):")
        for t in selected_traits:
            print(f"  - {t}")

        # 应用精神 (持续 100 回合)
        for s_id in selected_spirits:
            EffectManager.add_effect(mecha, s_id, duration=100)

        # 应用特性
        mecha.traits = selected_traits
        TraitManager.apply_traits(mecha)

    def run_challenge(self, round_idx: int):
        """执行一轮挑战"""
        print("\n" + "="*70)
        print(f"【第 {round_idx} 轮挑战】")
        print("="*70)

        # 1. 初始化挑战者
        attacker = self.create_challenger()

        # 2. 初始化 Boss
        boss = self.create_boss()

        # 3. 应用随机技能
        self.apply_random_skills(attacker)

        # 4. 强制注入死斗技能
        attacker.effects.append(get_maintain_skill())

        print(f"\n--- 战斗开始: {attacker.name} vs {boss.name} ---")
        print(f"挑战者 HP: {attacker.current_hp:,} | Boss HP: {boss.current_hp:,}")

        # 5. 执行战斗
        sim = BattleSimulator(attacker, boss)
        sim.run_battle()

        # 6. 结果统计
        print(f"\n{'─'*70}")
        print(f"【挑战结束】")
        print(f"{'─'*70}")
        print(f"最终回合数: {sim.round_number}")
        print(f"挑战者剩余 HP: {attacker.current_hp:,} ({attacker.get_hp_percentage():.1f}%)")
        print(f"Boss 剩余 HP: {boss.current_hp:,} ({boss.get_hp_percentage():.1f}%)")

        if not boss.is_alive():
            print("✨ 成功击破 Boss！")
            return "WIN"
        elif not attacker.is_alive():
            print("❌ 挑战失败，机体被击破")
            return "LOSE"
        else:
            if boss.current_hp < boss.max_hp * 0.1:
                print("⚠️ 未能击破，但造成重创")
            elif boss.current_hp < boss.max_hp * 0.5:
                print("⚠️ 未能击破，造成中等伤害")
            else:
                print("⚠️ 未能击破，伤害不足")
            return "DRAW"

# ============================================================================
# 4. 主程序
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Boss 挑战测试")
    parser.add_argument("--difficulty", choices=["easy", "normal", "hard", "extreme"],
                       default="normal", help="Boss 难度")
    parser.add_argument("--rounds", type=int, default=5,
                       help="挑战轮数")

    args = parser.parse_args()

    challenger = BossChallenger(args.difficulty)

    results = {"WIN": 0, "LOSE": 0, "DRAW": 0}

    for i in range(1, args.rounds + 1):
        result = challenger.run_challenge(i)
        results[result] += 1

        # 回合间暂停（仅在交互模式下）
        if i < args.rounds and sys.stdin.isatty():
            try:
                input("\n按 Enter 继续下一轮...")
            except (EOFError, KeyboardInterrupt):
                pass

    # 总结
    print("\n" + "="*70)
    print("【挑战总结】")
    print("="*70)
    print(f"总轮数: {args.rounds}")
    print(f"胜利: {results['WIN']} ({results['WIN']/args.rounds*100:.1f}%)")
    print(f"失败: {results['LOSE']} ({results['LOSE']/args.rounds*100:.1f}%)")
    print(f"平局: {results['DRAW']} ({results['DRAW']/args.rounds*100:.1f}%)")
    print("="*70)

if __name__ == "__main__":
    main()
