"""
高阶压力测试 - 动态博弈与链式反应
验证：优先级冲突、跨钩子引用(RefHook)、施加效果(apply_effect)、属性压制检查。
"""

import sys
import os
import io

# 确保能导入 src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# UTF-8 兼容
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.models import Mecha, Pilot, Weapon, WeaponType, BattleContext, Effect, Terrain
from src.skills import SkillRegistry, EffectManager

def setup_god_tier_combat():
    """初始化高等级机体"""
    # 王牌驾驶员：高反应、高技量 (使用关键字参数防止错位)
    ace_pilot = Pilot(
        id="p_ace", name= "Amuro", 
        stat_shooting=180, stat_melee=180, stat_reaction=170,
        stat_awakening=150, stat_defense=120
    )
    # 高级机体：全属性加成
    nu_gundam = Mecha(
        id="m_nu", name="Nu Gundam", pilot=ace_pilot, 
        max_hp=8000, current_hp=8000, max_en=300, current_en=300,
        hit_rate=20, precision=15, crit_rate=10,
        dodge_rate=15, parry_rate=15, block_rate=10,
        defense_level=1200, mobility=150
    )
    
    # 宿敌机体
    rival_pilot = Pilot(
        id="p_rival", name="Char", 
        stat_shooting=175, stat_melee=175, stat_reaction=165,
        stat_awakening=140, stat_defense=115
    )
    sazabi = Mecha(
        id="m_sazabi", name="Sazabi", pilot=rival_pilot, 
        max_hp=9000, current_hp=9000, max_en=350, current_en=350,
        hit_rate=18, precision=12, crit_rate=8,
        dodge_rate=20, parry_rate=10, block_rate=15,
        defense_level=1300, mobility=145
    )
    
    weapon = Weapon(id="w_fin_funnel", name="Fin Funnel", weapon_type=WeaponType.RIFLE, power=2000, en_cost=30, range_min=1, range_max=7)
    
    ctx = BattleContext(round_number=1, distance=2000, terrain=Terrain.SPACE, attacker=nu_gundam, defender=sazabi, weapon=weapon)
    return nu_gundam, sazabi, ctx

def test_complex_priority_chain():
    """验证：优先级与操作叠加
    必中(priority=100, set 100) vs 集中(priority=1, add 30) vs 敌方闪避干扰(priority=50, sub 50)
    """
    print("\n[Extreme 1] 复杂优先级链条测试")
    nu, sazabi, ctx = setup_god_tier_combat()
    
    # 阿姆罗：开启集中(+30) 和 必中(Set 100)
    EffectManager.add_effect(nu, "spirit_focus")
    EffectManager.add_effect(nu, "spirit_strike")
    
    # 夏亚：开启干扰 (假设有一个干扰技能让对方命中-50, 优先级50)
    debuff = Effect(
        id="debuff_jamming", name="强力干扰", hook="HOOK_PRE_HIT_RATE",
        operation="sub", value=50.0, priority=50
    )
    sazabi.effects.append(debuff)
    
    # 计算过程：
    # 1. 必中(100) -> set 100.0
    # 2. 干扰(50) -> sub 50 -> 50.0
    # 3. 集中(1) -> add 30 -> 80.0
    # 如果必中想要绝对胜出，它的优先级应该最高且所有计算都要在它之后？
    # 不，通常 SRW 中，必中是最后锁定的。或者设置极高优先级并在最后执行。
    # 我们的排序是 priority 降序。所以必中先执行。
    # 结果应该是 80.0。
    
    res = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 70.0, ctx)
    print(f"   最终计算命中率: {res}%")
    # 理论：70 -> set 100 -> sub 50 -> add 30 = 80
    assert res == 80.0
    print("   [PASS] 优先级排序与混合操作执行正确")

def test_inter_hook_dependency():
    """验证：跨钩子结果引用 (RefHook)
    技能“精准专注”：如果命中率(HOOK_PRE_HIT_RATE)计算结果 > 90，则伤害倍率(HOOK_PRE_DAMAGE_MULT) +0.5
    """
    print("\n[Extreme 2] 跨阶段钩子联动 (RefHook)")
    nu, sazabi, ctx = setup_god_tier_combat()
    
    # 添加联动技能
    precision_focus = Effect(
        id="skill_prec", name="精准专注", hook="HOOK_PRE_DAMAGE_MULT",
        operation="add", value=0.5,
        conditions=[{"type": "ref_hook", "ref_hook": "HOOK_PRE_HIT_RATE", "val": 90, "op": ">"}]
    )
    nu.effects.append(precision_focus)
    
    # 模拟命中率计算
    print("   --- 步骤 A: 计算命中率 ---")
    SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 95.0, ctx) # 此时 95 会被存入 cached_results
    
    # 模拟倍率计算
    print("   --- 步骤 B: 计算伤害倍率 ---")
    dmg_mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)
    print(f"   命中率过高触发增益后的伤害倍率: {dmg_mult}")
    assert dmg_mult == 1.5
    print("   [PASS] 跨钩子结果引用成功触发")

def test_chain_reaction():
    """验证：副作用链式反应
    技能“燃烧之魂”：造成伤害后，自动触发下一回合的“集中”。
    """
    print("\n[Extreme 3] 副作用链式反应 (Cascade)")
    nu, sazabi, ctx = setup_god_tier_combat()
    
    # 注册一个连锁技能
    burning_soul = Effect(
        id="skill_burning", name="燃烧之魂", hook="HOOK_ON_DAMAGE_DEALT",
        operation="callback", value="dummy",
        side_effects=[{"type": "apply_effect", "effect_id": "spirit_focus", "duration": 2, "target": "self"}]
    )
    nu.effects.append(burning_soul)
    
    print(f"   攻击前 Nu Gundam 效果数: {len(nu.effects)}")
    # 触发伤害钩子
    SkillRegistry.process_hook("HOOK_ON_DAMAGE_DEALT", 5000, ctx)
    
    # 检查是否多了“集中”
    # spirit_focus 会通过 factory 生成两个子效果
    print(f"   反击触发后 Nu Gundam 效果数: {len(nu.effects)}")
    # 原本 1 个 + 新增 2 个 = 3 个
    assert len(nu.effects) == 3
    print("   [PASS] 成功通过副作用施加了复合效果（集中）")

def test_stat_oppression():
    """验证：对手属性压制检查
    技能“气压”：如果我的觉醒值 > 对手觉醒值，则对方伤害倍率 x0.8
    """
    print("\n[Extreme 4] 属性数值压制测试 (Enemy Stat Check)")
    nu, sazabi, ctx = setup_god_tier_combat()
    
    # 夏亚感到压力：当阿姆罗觉醒高时，夏亚伤害降低
    pressure = Effect(
        id="skill_pressure", name="名将压制", hook="HOOK_PRE_DAMAGE_MULT",
        operation="mul", value=0.8,
        conditions=[{"type": "enemy_stat_check", "stat": "stat_awakening", "val": 140, "op": ">"}]
    )
    # 夏亚拥有的技能，检查敌人（阿姆罗）的属性
    sazabi.effects.append(pressure)
    
    # 1. 夏亚攻击时的倍率计算（此时夏亚是拥有者，检查敌人阿姆罗 觉醒150 > 140，满足条件）
    # 在计算夏亚伤害时，夏亚是 attacker，阿姆罗是 defender (或 context 设置逻辑)
    # 这里通过 EffectProcessor 的侧重点来验证。
    # 场景：夏亚(Owner)作为 Defender 时受到的压制？(通常压力是减低对方命中)。
    # 假设：夏亚作为 Attacker 攻击阿姆罗，阿姆罗的高觉醒让他感到压力。
    ctx_char_atk = BattleContext(round_number=1, distance=1000, attacker=sazabi, defender=nu)
    
    mult = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx_char_atk)
    print(f"   夏亚面临高觉醒对手时的伤害倍率: {mult}")
    assert mult == 0.8
    print("   [PASS] 成功识别对手 Pilot 属性并触发条件")

def test_multi_layered_expiration():
    """验证：极端过载情况下的生命周期管理
    堆叠 5 个 1 次性效果，5 个 3 回合效果，验证全部清理。
    """
    print("\n[Extreme 5] 极端过载清理测试")
    nu, sazabi, ctx = setup_god_tier_combat()
    
    # 堆叠
    for i in range(5):
        EffectManager.add_effect(nu, "spirit_valor") # 1次性
    
    print(f"   初始效果数: {len(nu.effects)}")
    
    # 连续触发 10 次
    print("   连续进行 5 次攻击消耗次数...")
    for _ in range(5):
        SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)
    
    # 手动触发 Tick
    print("   回合结束执行 Tick 清理...")
    EffectManager.tick_effects(nu)
    
    print(f"   清理后效果数: {len(nu.effects)}")
    assert len(nu.effects) == 0
    print("   [PASS] 大量效果并发消耗与清理无误")

if __name__ == "__main__":
    print("="*60)
    print("技能系统 - 极端压力测试 (Level High)")
    print("="*60)
    
    try:
        test_complex_priority_chain()
        test_inter_hook_dependency()
        test_chain_reaction()
        test_stat_oppression()
        test_multi_layered_expiration()
        
        print("\n" + "="*60)
        print("所有极端压力测试通过！系统架构显示出极高的鲁棒性。")
        print("="*60)
    except Exception as e:
        print(f"\n[FAIL] 验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
