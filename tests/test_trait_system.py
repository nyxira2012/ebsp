"""
验证 Phase 5: 机体特性 (Trait) 系统
验证特性如何从 JSON 定义变成永久 Effect，并参与 Hook 计算。
"""

import sys
import os
import io

# 确保导入路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Windows UTF-8
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.models import Mecha, Pilot, Weapon, WeaponType, BattleContext, Terrain
from src.skills import TraitManager, SkillRegistry

def test_newtype_trait():
    print("\n[Trait Test] 验证 Newtype (NT) 特性")
    
    # 初始化一个拥有 trait_nt 的机体
    pilot = Pilot(
        id="p_amuro", name="Amuro", 
        stat_shooting=180, stat_melee=180, stat_reaction=170,
        stat_awakening=150, stat_defense=120
    )
    nu = Mecha(
        id="m_nu", name="Nu Gundam", pilot=pilot, 
        max_hp=5000, current_hp=5000, max_en=100, current_en=100,
        hit_rate=0, precision=0, crit_rate=0,
        dodge_rate=0, parry_rate=0, block_rate=0,
        defense_level=1000, mobility=150,
        traits=["trait_nt"]  # 赋予特性
    )
    
    # 刚开始没有效果
    print(f"   初始化后效果数: {len(nu.effects)}")
    assert len(nu.effects) == 0
    
    # 应用特性 (将 trait_nt 转换为永久 Effect)
    TraitManager.apply_traits(nu)
    print(f"   应用特性后效果数: {len(nu.effects)}")
    assert len(nu.effects) == 2 # NT 包含 命中和回避 两个效果
    
    # 模拟战斗
    ctx = BattleContext(round_number=1, distance=1000, attacker=nu, defender=nu)
    
    # 验证命中率加成 (NT 应 +15.0)
    final_hit = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 50.0, ctx)
    print(f"   基础命中 50 + NT加成 = {final_hit}%")
    assert final_hit == 65.0
    
    # 验证躲闪率加成 (NT 应 +15.0)
    final_eva = SkillRegistry.process_hook("HOOK_PRE_DODGE_RATE", 40.0, ctx)
    print(f"   基础躲闪 40 + NT加成 = {final_eva}%")
    assert final_eva == 55.0
    
    print("   [PASS] NT特性正确转化为 Effect 并参与计算")

def test_expert_trait():
    print("\n[Trait Test] 验证精英驾驶员 (Expert) 特性")
    
    pilot = Pilot(id="p_exp", name="Expert", stat_shooting=150, stat_melee=150, stat_reaction=150, stat_awakening=0, stat_defense=100)
    mecha = Mecha(
        id="m_custom", name="Custom Mecha", pilot=pilot, 
        max_hp=4000, current_hp=4000, max_en=100, current_en=100,
        hit_rate=0, precision=0, crit_rate=0,
        dodge_rate=0, parry_rate=0, block_rate=0,
        defense_level=1000, mobility=100,
        traits=["trait_expert"] 
    )
    
    TraitManager.apply_traits(mecha)
    ctx = BattleContext(round_number=1, distance=1000, attacker=mecha, defender=mecha)
    
    # 验证伤害加成 (+0.1)
    val = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)
    print(f"   精英伤害倍率: {val}")
    assert val == 1.1
    
    # 验证 EN 节省 (x0.9)
    en_cost = SkillRegistry.process_hook("HOOK_PRE_EN_COST_MULT", 100.0, ctx)
    print(f"   精英节能后消耗: {en_cost}")
    assert en_cost == 90.0
    
    print("   [PASS] 精英特性正确生效")

if __name__ == "__main__":
    test_newtype_trait()
    test_expert_trait()
    print("\n" + "="*60)
    print("Phase 5: 特性系统验证通过！")
    print("="*60)
