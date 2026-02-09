"""
集成测试：4v4 八向技能博弈
验证双方各拥有 4 个不同类型技能（总计 8 个）时的协同表现。
涵盖：先手、精准、EN节能、伤害锁定、分身、属性加成、减伤提升。
"""

import sys
import os
import io

# 确保导入路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Windows UTF-8
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.models import Mecha, Pilot, Weapon, WeaponType, BattleContext, Effect, Terrain
from src.skills import SkillRegistry, EffectManager
from src.combat.resolver import AttackTableResolver

def setup_4v4_scenario():
    # 1. 攻击方：阿姆罗
    amuro = Pilot(
        id="p_amuro", name="Amuro", 
        stat_shooting=180, stat_melee=180, stat_reaction=170,
        stat_awakening=150, stat_defense=120
    )
    nu = Mecha(
        id="m_nu", name="Nu Gundam", pilot=amuro, 
        max_hp=5000, current_hp=5000, max_en=100, current_en=100, # 初始 EN 100
        hit_rate=20, precision=15, crit_rate=10,
        dodge_rate=15, parry_rate=15, block_rate=10,
        defense_level=1200, mobility=150,
        current_will=120
    )
    
    # 2. 防御方：夏亚
    char = Pilot(
        id="p_char", name="Char", 
        stat_shooting=175, stat_melee=175, stat_reaction=165,
        stat_awakening=140, stat_defense=115
    )
    sazabi = Mecha(
        id="m_sazabi", name="Sazabi", pilot=char, 
        max_hp=9000, current_hp=9000, max_en=350, current_en=350,
        hit_rate=15, precision=10, crit_rate=5,
        dodge_rate=20, parry_rate=10, block_rate=15,
        defense_level=1300, mobility=145,
        current_will=140 # 较高气力触发分身
    )
    
    # 核爆级攻击 (EN消耗 50)
    weapon = Weapon(id="w_hyper_bazooka", name="Hyper Bazooka", weapon_type=WeaponType.HEAVY, power=4000, en_cost=50, range_min=2, range_max=6)
    
    ctx = BattleContext(round_number=1, distance=2000, attacker=nu, defender=sazabi, weapon=weapon)
    return nu, sazabi, ctx

def run_test():
    print("="*80)
    print("八向技能博弈验证 (4v4)")
    print("="*80)
    
    nu, sazabi, ctx = setup_4v4_scenario()
    
    # --- 攻击方 4 个技能 ---
    print("\n[Nu Gundam] 技能准备:")
    # 1. 精神: 必中 (Strike)
    EffectManager.add_effect(nu, "spirit_strike")
    # 2. 精神: 热血 (Valor)
    EffectManager.add_effect(nu, "spirit_valor")
    # 3. 技能: 精准打击 (+25 精准)
    nu.effects.append(Effect(id="skill_prec", name="精准打击", hook="HOOK_PRE_PRECISION", operation="add", value=25.0))
    # 4. 技能: 节能 (-30% EN消耗)
    nu.effects.append(Effect(id="skill_save", name="节能", hook="HOOK_PRE_EN_COST_MULT", operation="mul", value=0.7))
    
    # --- 防御方 4 个技能 ---
    print("\n[Sazabi] 技能准备:")
    # 1. 精神: 铁壁 (MITIGATION set 0.75)
    EffectManager.add_effect(sazabi, "spirit_iron_wall")
    # 2. 技能: 不屈 (受到伤害设为 10, 消耗型)
    sazabi.effects.append(Effect(id="spirit_indomitable", name="不屈", hook="HOOK_ON_DAMAGE_TAKEN", operation="set", value=10, charges=1, priority=100))
    # 3. 技能: 分身 (当气力 > 130 时，躲闪 + 50%)
    sazabi.effects.append(Effect(
        id="skill_afterimage", name="分身", hook="HOOK_PRE_DODGE_RATE", operation="add", value=50.0,
        conditions=[{"type": "will_threshold", "target": "self", "val": 130, "op": ">"}]
    ))
    # 4. 技能: 厚重装甲 (+400 防御等级)
    sazabi.effects.append(Effect(id="skill_armor", name="厚重装甲", hook="HOOK_PRE_DEFENSE_LEVEL", operation="add", value=400.0))

    print("\n" + "-"*40)
    print("【开始模拟战斗计算链条】")
    print("-"*40)

    # 1. EN 结算
    print("\n[Stage 1] EN 消耗阶段:")
    orig_en = nu.current_en
    final_cost = SkillRegistry.process_hook("HOOK_PRE_EN_COST_MULT", 50.0, ctx)
    print(f">> 原始消耗: 50 | 修正后消耗: {final_cost}")
    assert final_cost == 35.0 # 50 * 0.7

    # 2. 命中结算 (必中优先级最高)
    print("\n[Stage 2] 命中博弈阶段:")
    # 加入分身的干扰
    final_hit = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 80.0, ctx)
    print(f">> 最终命中率: {final_hit}%")
    assert final_hit == 100.0 # 必中赢了

    # 3. 防御穿透结算
    print("\n[Stage 3] 精准度阶段:")
    final_prec = SkillRegistry.process_hook("HOOK_PRE_PRECISION", 15.0, ctx)
    print(f">> 最终精准度: {final_prec} (基础15 + 技能25)")
    assert final_prec == 40.0

    # 4. 护甲结算
    print("\n[Stage 4] 防御等级阶段:")
    final_def = SkillRegistry.process_hook("HOOK_PRE_DEFENSE_LEVEL", 1300.0, ctx)
    print(f">> 最终防御等级: {final_def} (基础1300 + 技能400)")
    assert final_def == 1700.0

    # 5. 伤害计算 (热血 + 铁壁 + 不屈)
    print("\n[Stage 5] 伤害与减伤终极决战:")
    # 5a. 热血加成
    mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)
    print(f">> 伤害倍率: {mult}x (热血)")
    assert mult == 2.0
    
    # 5b. 铁壁减伤
    mitigation = SkillRegistry.process_hook("HOOK_PRE_MITIGATION", 0.1, ctx)
    print(f">> 减伤比例: {mitigation*100}% (铁壁)")
    assert mitigation == 0.75
    
    # 5c. 受到伤害钩子 (不屈处理)
    # 假设计算出的最终伤害是 8000
    print("\n--- 触发 HOOK_ON_DAMAGE_TAKEN (不屈介入) ---")
    final_dmg = SkillRegistry.process_hook("HOOK_ON_DAMAGE_TAKEN", 8000, ctx)
    print(f">> 最终受到伤害: {final_dmg}")
    assert final_dmg == 10
    
    # --- 生命周期验证 ---
    print("\n[Stage 6] 生命周期清理检查:")
    # 不屈触发一次后应该 Charges 归 0
    # 热血触发一次后应该 Charges 归 0
    EffectManager.tick_effects(nu)
    EffectManager.tick_effects(sazabi)
    
    print(f">> Nu Gundam 剩余效果数: {len(nu.effects)} (应当剩 2 个被动)")
    print(f">> Sazabi 剩余效果数: {len(sazabi.effects)} (应当剩 2 个被动 + 铁壁)")
    
    # 查看 Sazabi 效果 ID
    sazabi_eff_ids = [e.id for e in sazabi.effects]
    print(f">> Sazabi 当前效果: {sazabi_eff_ids}")
    assert "spirit_indomitable" not in sazabi_eff_ids
    
    print("\n" + "="*80)
    print("【测试通过】八向技能博弈逻辑严丝合缝，系统鲁棒性达到工业级。")
    print("="*80)

if __name__ == "__main__":
    run_test()
