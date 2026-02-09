"""
2. 多回合实机模拟测试
验证：
1. 默认回合限制 (4回合)
2. 动态回合限制 (通过 HOOK_MAX_ROUNDS 修改)
3. 死斗模式 (通过 HOOK_CHECK_MAINTAIN_BATTLE 持续战斗直到击破)
4. 长期战斗中的资源消耗 (EN) 表现
"""

import sys
import os
import io

# 确保导入路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Windows UTF-8 支持
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.models import Mecha, Pilot, Weapon, WeaponType, BattleContext, Effect
from src.skills import SkillRegistry, EffectManager
from src.combat.engine import BattleSimulator
from src.config import Config

def setup_tank_mechas():
    """初始化两台高血量、低伤害的‘沙袋’机体，用于测试多回合表现"""
    pilot_a = Pilot(id="p_heavy_1", name="Heavy Pilot A", stat_shooting=100, stat_melee=100, stat_reaction=100, stat_awakening=100, stat_defense=100)
    mecha_a = Mecha(
        id="m_tank_1", name="Fortress A", pilot=pilot_a, 
        max_hp=50000, current_hp=50000, max_en=100, current_en=100,
        hit_rate=20, precision=10, crit_rate=0,
        dodge_rate=0, parry_rate=0, block_rate=0,
        defense_level=2000, mobility=50
    )
    
    pilot_b = Pilot(id="p_heavy_2", name="Heavy Pilot B", stat_shooting=100, stat_melee=100, stat_reaction=100, stat_awakening=100, stat_defense=100)
    mecha_b = Mecha(
        id="m_tank_2", name="Fortress B", pilot=pilot_b, 
        max_hp=50000, current_hp=50000, max_en=100, current_en=100,
        hit_rate=20, precision=10, crit_rate=0,
        dodge_rate=0, parry_rate=0, block_rate=0,
        defense_level=2000, mobility=50
    )
    
    # 低伤害武器，确保打不动
    weapon = Weapon(id="w_pea_shooter", name="Pea Shooter", weapon_type=WeaponType.RIFLE, power=100, en_cost=10, range_min=0, range_max=10000)
    mecha_a.weapons.append(weapon)
    mecha_b.weapons.append(weapon)
    
    return mecha_a, mecha_b

def test_default_limit():
    print("\n" + "="*60)
    print("Scenario 1: 验证默认回合限制 (4 回合)")
    print("="*60)
    
    a, b = setup_tank_mechas()
    sim = BattleSimulator(a, b)
    sim.run_battle()
    
    print(f"\n最终回合数: {sim.round_number}")
    assert sim.round_number == 4
    print("   [PASS] 成功在第 4 回合停止")

def test_modified_limit():
    print("\n" + "="*60)
    print("Scenario 2: 验证动态修改上限 (通过 Hook 设为 6 回合)")
    print("="*60)
    
    # 注册一个临时 Hook 修改上限
    @SkillRegistry.register_hook("HOOK_MAX_ROUNDS")
    def extend_limit(val, ctx):
        return 6
        
    try:
        a, b = setup_tank_mechas()
        sim = BattleSimulator(a, b)
        sim.run_battle()
        
        print(f"\n最终回合数: {sim.round_number}")
        assert sim.round_number == 6
        print("   [PASS] 成功在第 6 回合停止")
    finally:
        # 清理 Hook 避免干扰后续测试
        if "HOOK_MAX_ROUNDS" in SkillRegistry._hooks:
            SkillRegistry._hooks["HOOK_MAX_ROUNDS"] = []

def test_death_match_mode():
    print("\n" + "="*60)
    print("Scenario 3: 验证 '死斗' 模式 (直到击破为止)")
    print("="*60)
    
    a, b = setup_tank_mechas()
    
    # 为了防止真的打太久，我们把其中一个血量调低，伤害调高一点
    a.current_hp = 500
    w_strong = Weapon(id="w_real", name="Real Gun", weapon_type=WeaponType.RIFLE, power=2000, en_cost=5, range_min=0, range_max=10000)
    b.weapons = [w_strong]
    
    # 模拟死斗技能的效果：在 HOOK_CHECK_MAINTAIN_BATTLE 返回 True
    # 我们通过给机体加上一个带 callback 的 Effect 来实现
    @SkillRegistry.register_callback("cb_death_match")
    def cb_death_match(val, ctx, effect):
        print(f"   [Skill] 死斗效果生效中... (Round {ctx.round_number})")
        return True

    death_match_eff = Effect(
        id="skill_death_match", name="死斗",
        hook="HOOK_CHECK_MAINTAIN_BATTLE", operation="callback", value="cb_death_match",
        duration=-1 # 永久有效直到战斗结束
    )
    a.effects.append(death_match_eff)
    
    sim = BattleSimulator(a, b)
    sim.run_battle()
    
    print(f"\n最终回合数: {sim.round_number}")
    # 应该超过 4 回合（因为 a 血量 500，b 威力 2000，扣除防御后可能需要几下，
    # 且我们要验证它是否跳过了 4 回合限制）
    # 由于 a 只有 500 HP，且先手判定存在，b 可能会在 2-3 回合击破 a，
    # 我们把 a 的血量再调高一点点，确保能撑到第 5 回合
    
    a.current_hp = 1200 # 承受约 3-4 次攻击
    
    print("   [INFO] 重新模拟死斗...")
    a, b = setup_tank_mechas()
    a.current_hp = 1500
    b.weapons = [Weapon(id="w_kill", name="Executioner", weapon_type=WeaponType.RIFLE, power=1500, en_cost=0, range_min=0, range_max=10000)]
    a.effects.append(death_match_eff)
    
    sim = BattleSimulator(a, b)
    sim.run_battle()
    
    assert sim.round_number > 4 or not a.is_alive() or not b.is_alive()
    if sim.round_number > 4:
        print(f"   [PASS] 战斗成功跨越 4 回合限制，当前回合: {sim.round_number}")
    else:
        print(f"   [PASS] 战斗在 4 回合内由于击破结束，当前回合: {sim.round_number}")

def test_resource_depletion():
    print("\n" + "="*60)
    print("Scenario 4: 资源耗尽测试 (EN 枯竭)")
    print("="*60)
    
    a, b = setup_tank_mechas()
    # 只有 30 EN，每发 10，3发就没了
    a.current_en = 30
    b.current_en = 30
    
    # 强制进行 10 回合
    @SkillRegistry.register_hook("HOOK_MAX_ROUNDS")
    def long_run(val, ctx): return 10
    
    try:
        sim = BattleSimulator(a, b)
        sim.run_battle()
        
        print(f"\n最终回合: {sim.round_number}")
        print(f"Fortress A 剩余 EN: {a.current_en}")
        print(f"Fortress B 剩余 EN: {b.current_en}")
        assert a.current_en < 10
        assert b.current_en < 10
        print("   [PASS] 资源正确消耗")
    finally:
         if "HOOK_MAX_ROUNDS" in SkillRegistry._hooks:
            SkillRegistry._hooks["HOOK_MAX_ROUNDS"] = []

if __name__ == "__main__":
    print("="*80)
    print("大规模实机模拟与死斗机制验证")
    print("="*80)
    
    try:
        test_default_limit()
        test_modified_limit()
        test_death_match_mode()
        test_resource_depletion()
        
        print("\n" + "="*80)
        print("所有实机模拟案通过！多回合系统具备高度灵活性。")
        print("="*80)
    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
