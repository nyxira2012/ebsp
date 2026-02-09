"""
综合验证脚本 - 技能系统全流程测试
验证：Hook、Condition、SideEffect、Processor、Factory 五大组件协作。
"""

import sys
import os
import io
from unittest.mock import MagicMock

# Windows UTF-8 兼容性处理
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 确保能导入 src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models import Mecha, Pilot, Weapon, WeaponType, BattleContext, AttackResult, Terrain
from src.skills import SkillRegistry, EffectManager
from src.skill_system.processor import EffectProcessor

def setup_mock_combat():
    """初始化测试用的机体和上下文"""
    pilot_a = Pilot(
        id="p_a", name="Attacker", 
        stat_melee=150, stat_shooting=150, stat_reaction=140,
        stat_awakening=100, stat_defense=100
    )
    mecha_a = Mecha(
        id="m_a", name="Gundam", pilot=pilot_a, 
        max_hp=5000, current_hp=5000, max_en=200, current_en=200,
        hit_rate=10, precision=10, crit_rate=5,
        dodge_rate=10, parry_rate=10, block_rate=10,
        defense_level=1000, mobility=100
    )
    
    pilot_b = Pilot(
        id="p_b", name="Defender", 
        stat_melee=120, stat_shooting=120, stat_reaction=110,
        stat_awakening=80, stat_defense=80
    )
    mecha_b = Mecha(
        id="m_b", name="Zaku", pilot=pilot_b, 
        max_hp=3000, current_hp=3000, max_en=100, current_en=100,
        hit_rate=5, precision=5, crit_rate=2,
        dodge_rate=5, parry_rate=5, block_rate=5,
        defense_level=800, mobility=80
    )
    
    weapon = Weapon(
        id="w_vfm", name="Beam Rifle", weapon_type=WeaponType.RIFLE, 
        power=1500, en_cost=10, range_min=1, range_max=5
    )
    
    ctx = BattleContext(
        round_number=1,
        distance=1000,
        terrain=Terrain.SPACE,
        attacker=mecha_a,
        defender=mecha_b,
        weapon=weapon
    )
    return mecha_a, mecha_b, ctx

def test_spirit_strike():
    """验证 [必中]: 命中率应强制设为 100"""
    print("\n[Case 1] 验证精神: 必中 (Strike)")
    mecha_a, mecha_b, ctx = setup_mock_combat()
    
    # 初始状态调用 hook (假设基础加成 30)
    val = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 30.0, ctx)
    print(f"   基础命中加成: {val}%")
    
    # 施加必中
    EffectManager.add_effect(mecha_a, "spirit_strike")
    
    val_after = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 30.0, ctx)
    print(f"   必中后命中加成: {val_after}%")
    assert val_after == 100.0
    print("   [PASS] 成功强制设为 100")

def test_spirit_alert():
    """验证 [必闪]: 防御方拥有时，攻击方命中应为 0"""
    print("\n[Case 2] 验证精神: 必闪 (Alert)")
    mecha_a, mecha_b, ctx = setup_mock_combat()
    
    # 给防御方施加必闪
    EffectManager.add_effect(mecha_b, "spirit_alert")
    
    # 在计算命中率钩子时（此时 ctx.attacker 是 mecha_a，但 processor 会检查 defender 的效果）
    val = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 80.0, ctx)
    print(f"   防御方有必闪时，攻击方命中率: {val}%")
    assert val == 0.0
    print("   [PASS] 成功强制设为 0")

def test_spirit_valor_and_charges():
    """验证 [热血] 及其消耗机制: 一次后应失效"""
    print("\n[Case 3] 验证精神: 热血 (Valor) & 次数消耗")
    mecha_a, mecha_b, ctx = setup_mock_combat()
    
    EffectManager.add_effect(mecha_a, "spirit_valor")
    print(f"   施加热血后效果数: {len(mecha_a.effects)}")
    
    # 第一次触发攻击倍率 Hook
    val1 = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)
    print(f"   第一次触发倍率: x{val1}")
    assert val1 == 2.0
    
    # 第二次触发
    val2 = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)
    print(f"   第二次触发倍率: x{val2}")
    assert val2 == 1.0
    
    # 检查效果是否被标记为过期 (duration=0)
    # 注意：在实际流程中，tick_effects 会清理它。我们这里手动检查状态
    for eff in mecha_a.effects:
        if eff.id == "spirit_valor":
            assert eff.duration == 0
            assert eff.charges == 0
    print("   [PASS] 次数消耗正确且已失效")

def test_conditions_hp():
    """验证条件检查: HP 限制"""
    print("\n[Case 4] 验证条件控制: HP 阈值")
    mecha_a, mecha_b, ctx = setup_mock_combat()
    
    from src.models import Effect
    # 创建一个只有 HP < 30% 才会触发的增益
    berserk = Effect(
        id="trait_berserk", name="狂战士",
        hook="HOOK_PRE_DAMAGE_MULT", operation="add", value=0.5,
        conditions=[{"type": "hp_threshold", "val": 0.3, "op": "<"}]
    )
    mecha_a.effects.append(berserk)
    
    # 当前 HP 100%，不应触发
    val_full = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)
    print(f"   满血时倍率: {val_full}")
    assert val_full == 1.0
    
    # 降低 HP 到 10%
    mecha_a.current_hp = 500
    val_low = SkillRegistry.process_hook("HOOK_PRE_DAMAGE_MULT", 1.0, ctx)
    print(f"   残血时倍率: {val_low}")
    assert val_low == 1.5
    print("   [PASS] HP条件检查生效")

def test_side_effects_en():
    """验证副作用: 消耗 EN"""
    print("\n[Case 5] 验证副作用: 消耗 EN")
    mecha_a, mecha_b, ctx = setup_mock_combat()
    
    from src.models import Effect
    # 模拟“高出力攻击”：每次攻击额外消耗 20 EN
    power_attack = Effect(
        id="power_atk", name="Power Attack",
        hook="HOOK_ON_DAMAGE_DEALT", operation="callback", value="dummy",
        side_effects=[{"type": "consume_en", "val": 20, "target": "self"}]
    )
    mecha_a.effects.append(power_attack)
    initial_en = mecha_a.current_en
    
    # 模拟攻击结束触发钩子
    SkillRegistry.process_hook("HOOK_ON_DAMAGE_DEALT", 1000, ctx)
    print(f"   触发副作用后 EN: {mecha_a.current_en} (初始: {initial_en})")
    assert mecha_a.current_en == initial_en - 20
    print("   [PASS] 副作用成功消耗 EN")

def test_recursion_prevention():
    """验证防递归机制"""
    print("\n[Case 6] 验证防递归判定")
    mecha_a, mecha_b, ctx = setup_mock_combat()
    
    from src.models import Effect
    # 注册一个会导致递归的回调
    @SkillRegistry.register_callback("recursive_cb")
    def recursive_cb(val, c, o):
        # 再次调用同名钩子，模拟逻辑死循环
        return SkillRegistry.process_hook("HOOK_RECURSIVE", val, c)

    bad_effect = Effect(
        id="bad_loop", name="Loop",
        hook="HOOK_RECURSIVE", operation="callback", value="recursive_cb"
    )
    mecha_a.effects.append(bad_effect)
    
    # 执行，不应死机
    print("   执行可能递归的钩子...")
    result = SkillRegistry.process_hook("HOOK_RECURSIVE", 100, ctx)
    print(f"   递归处理结果: {result} (正常返回)")
    assert result == 100
    print("   [PASS] 成功阻止无限递归")

if __name__ == "__main__":
    print("="*60)
    print("技能系统集成测试 - 详细验证")
    print("="*60)
    
    try:
        test_spirit_strike()
        test_spirit_alert()
        test_spirit_valor_and_charges()
        test_conditions_hp()
        test_side_effects_en()
        test_recursion_prevention()
        
        print("\n" + "="*60)
        print("所有集成验证通过！重构工作处于极高可靠性水平。")
        print("="*60)
    except Exception as e:
        print(f"\n[FAIL] 验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
