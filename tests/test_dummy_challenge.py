"""
木桩挑战测试 - 打爆 1M HP 木桩
验证：
1. 大规模回合累积：验证死斗机制（HOOK_CHECK_MAINTAIN_BATTLE）能否支持超长战斗。
2. 随机技能组合稳定性：每轮随机抽取 2 精神 + 3 特性。
3. 伤害累积：验证在极端属性叠加下的伤害输出。
进行 5 轮完整测试。
"""

import sys
import os
import io
import random
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
    # 只要防御方还活着，就继续战斗
    if ctx.defender and ctx.defender.is_alive():
        # 为了防止死循环（比如伤害为0），设置一个硬上限 1000 回合
        if ctx.round_number < 1000:
            return True
    return False

def get_maintain_skill():
    return Effect(
        id="skill_maintain_battle", name="无限延时",
        hook="HOOK_CHECK_MAINTAIN_BATTLE", operation="callback", value="cb_test_maintain",
        duration=-1
    )

# ============================================================================
# 2. 模拟器类
# ============================================================================

class DummyChallenge:
    def __init__(self):
        self.loader = DataLoader()
        self.loader.load_all()
        
        # 挑选所有可用技能 ID
        import json
        with open("data/skills.json", "r", encoding="utf-8") as f:
            self.all_skill_ids = list(json.load(f).keys())
            
        self.spirits = [s for s in self.all_skill_ids if s.startswith("spirit_")]
        self.traits = [t for t in self.all_skill_ids if t.startswith("trait_")]

    def run_round(self, round_idx: int):
        print("\n" + "="*80)
        print(f"【木桩挑战 第 {round_idx} 轮】")
        print("="*80)

        # 1. 初始化攻击者 (使用阿姆罗+高达作为基底)
        attacker = self.loader.get_mecha("mech_rx78")
        # 强化攻击者，否则打 1M HP 太慢了
        god_weapon = Weapon(
            id="w_god", name="上帝之雷", weapon_type=WeaponType.HEAVY, 
            power=10000, en_cost=0, range_min=0, range_max=10000
        )
        attacker.weapons = [god_weapon]
        attacker.current_hp = attacker.max_hp
        attacker.current_en = attacker.max_en
        attacker.effects = [] # 清空

        # 2. 初始化木桩
        dummy = self.loader.get_mecha("mech_dummy")
        dummy.current_hp = dummy.max_hp
        dummy.current_en = dummy.max_en
        dummy.effects = []

        # 3. 随机分配 2 精神 + 3 特性
        selected_spirits = random.sample(self.spirits, 2)
        selected_traits = random.sample(self.traits, 3)
        
        print(f"随机抽取的精神: {selected_spirits}")
        print(f"随机抽取的特性: {selected_traits}")

        # 应用精神 (持续 100 回合防止过期，或者每回合补，这里我们设长一点方便观察)
        for s_id in selected_spirits:
            EffectManager.add_effect(attacker, s_id, duration=100)
        
        # 应用特性
        attacker.traits = selected_traits
        TraitManager.apply_traits(attacker)

        # 4. 强制注入死斗技能
        attacker.effects.append(get_maintain_skill())

        print(f"\n--- 战斗开始: {attacker.name} vs {dummy.name} (HP: {dummy.current_hp}) ---")
        
        # 5. 执行战斗
        sim = BattleSimulator(attacker, dummy)
        # 为了测试效率，我们只打印每 10 回合的状态，或者最终结果
        # 这里包装一下输出
        sim.run_battle()

        print(f"\n🏆 挑战结束！最终回合数: {sim.round_number}")
        print(f"木桩剩余 HP: {dummy.current_hp}")
        if not dummy.is_alive():
            print("✨ 成功打爆内桩！")
        else:
            print("❌ 未能击破木桩（可能触发了 1000 回合保底）")

if __name__ == "__main__":
    challenge = DummyChallenge()
    for i in range(1, 6):
        challenge.run_round(i)
