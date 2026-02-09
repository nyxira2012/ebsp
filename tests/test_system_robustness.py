"""
系统健壮性破坏性测试 (System Robustness & Destructive Testing)
旨在挖掘边界条件下的 Bug，验证系统的容错力、递归保护及优先级逻辑。
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
from src.combat.engine import BattleSimulator
from src.skill_system.processor import EffectProcessor
from src.skills import SkillRegistry, EffectManager

def create_bare_mecha(mecha_id="test", pilot_id="p"):
    p = Pilot(
        id=pilot_id, name="TestPilot", 
        stat_shooting=100, stat_melee=100, stat_awakening=100, stat_defense=100, stat_reaction=100
    )
    return Mecha(
        id=mecha_id, name=mecha_id, pilot=p, 
        max_hp=1000, current_hp=1000, max_en=100, current_en=100,
        mobility=100, defense_level=1000,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=5.0, block_rate=5.0
    )

# ============================================================================
# 测试项 1: 递归陷阱保护 (Recursion Guard)
# ============================================================================
def test_recursion_protection():
    print("\n[Robustness 1] 验证递归异常保护")
    
    # 设计 A -> B -> A 的循环触发
    @SkillRegistry.register_callback("cb_infinite_a")
    def cb_a(val, ctx, owner):
        # 再次触发同类钩子，尝试导致死循环
        return SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", val, ctx)
        
    eff_cycle = Effect(
        id="eff_recursion_trap", name="递归陷阱",
        hook="HOOK_PRE_HIT_RATE", operation="callback", value="cb_infinite_a",
        duration=-1
    )
    
    m = create_bare_mecha()
    ctx = BattleContext(attacker=m, defender=m, round_number=1, distance=1000)
    m.effects.append(eff_cycle)
    
    # 执行
    try:
        # 这个 process 会调用 cb_a，cb_a 再调用 SkillRegistry.process_hook
        # 我们的 Processor.process 里有 count(hook_name) > 3 的检查
        res = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 50.0, ctx)
        print(f"   结果: {res} (未崩溃)")
        print("   [PASS] 递归拦截成功生效。")
    except RecursionError:
        print("   [FAIL] 触发了 Python 系统级别的递归错误。")
    except Exception as e:
        print(f"   [FAIL] 发生非预期错误: {e}")

# ============================================================================
# 测试项 2: 优先级“矛盾之争” (Priority Conflict)
# ============================================================================
def test_priority_conflict():
    print("\n[Robustness 2] 验证优先级冲突 (必中 vs 必闪)")
    
    eff_flash = Effect(id="flash", name="超强必闪", hook="HOOK_PRE_HIT_RATE", operation="set", value=0.0, priority=200)
    eff_strike = Effect(id="strike", name="标准必中", hook="HOOK_PRE_HIT_RATE", operation="set", value=100.0, priority=100)
    eff_buff = Effect(id="buff", name="超级增益", hook="HOOK_PRE_HIT_RATE", operation="add", value=999.0, priority=10)
    
    m = create_bare_mecha()
    ctx = BattleContext(attacker=m, defender=m, round_number=1, distance=1000)
    m.effects.extend([eff_buff, eff_strike, eff_flash])
    
    res = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 50.0, ctx)
    print(f"   最终结果: {res} (期望应为最高优先级的 0.0)")
    
    if res == 0.0:
        print("   [PASS] 优先级排序逻辑准确拦截了低优先级的后续修改。")
    else:
        print("   [FAIL] 逻辑未严格遵循优先级排序。")

# ============================================================================
# 测试项 3: 零属性与除零风险 (Zero Stat Stress)
# ============================================================================
def test_zero_stats():
    print("\n[Robustness 3] 验证零属性与除零容错")
    
    # 驾驶员属性全 0
    p = Pilot(id="zero_pilot", name="空壳", stat_shooting=0, stat_melee=0, stat_reaction=0, stat_defense=0, stat_awakening=0)
    # 机体属性极低
    m = Mecha(
        id="zero_mech", name="报废机", pilot=p, 
        max_hp=10, current_hp=10, max_en=10, current_en=10,
        defense_level=0, mobility=0,
        hit_rate=0.0, precision=0.0, crit_rate=0.0,
        dodge_rate=0.0, parry_rate=0.0, block_rate=0.0
    )
    m.weapons = [Weapon(id="w", name="牙签", weapon_type=WeaponType.MELEE, power=1, en_cost=0, range_min=0, range_max=1)]
    
    try:
        # 修改：为了触发可能的计算逻辑，我们需要两个不同的对象或者克隆
        m_enemy = Mecha(
            id="enemy", name="敌人", pilot=p, max_hp=10, current_hp=10, max_en=10, current_en=10,
            defense_level=0, mobility=0,
            hit_rate=0.0, precision=0.0, crit_rate=0.0,
            dodge_rate=0.0, parry_rate=0.0, block_rate=0.0
        )
        sim = BattleSimulator(m, m_enemy)
        sim._execute_round()
        print("   [PASS] 全 0 属性环境下计算引擎未出现除零错误。")
    except ZeroDivisionError:
        print("   [FAIL] 触发了 ZeroDivisionError！")
    except Exception as e:
        print(f"   [FAIL] 发生非预期错误: {e}")

# ============================================================================
# 测试项 4: 资源死锁测试 (Resource Deadlock)
# ============================================================================
def test_resource_deadlock():
    print("\n[Robustness 4] 验证战斗死锁 (无 EN, 无 Fallback)")
    
    m = create_bare_mecha()
    m.max_en = 0
    m.current_en = 0
    # 给一把昂贵的武器，但清空 fallback (在 models.py 中，fallback 通常由外部逻辑判定)
    # 这里我们直接把机体的武器库清空或只留不可用的
    m.weapons = [Weapon(id="w", name="核弹", weapon_type=WeaponType.HEAVY, power=999, en_cost=1000, range_min=0, range_max=1000)]
    
    # 注入一个确保继续战斗的钩子
    @SkillRegistry.register_callback("cb_deadlock_maintain")
    def cb_maintain(val, ctx, owner): return True
    m.effects.append(Effect(id="e", name="死斗", hook="HOOK_CHECK_MAINTAIN_BATTLE", operation="callback", value="cb_deadlock_maintain", duration=-1))

    print("   尝试启动死锁战斗判定...")
    sim = BattleSimulator(m, m)
    
    # 模拟攻击选择
    from src.combat.engine import WeaponSelector
    attacker_weapon = WeaponSelector.select_best_weapon(m, 1000)
    print(f"   选择的攻击武器: {attacker_weapon}")
    
    # 在当前 engine 逻辑下，如果不提供默认武器，它应该返回 None 或空
    if attacker_weapon is None or (hasattr(attacker_weapon, 'id') and attacker_weapon.id == 'wpn_fallback'):
         # 检查 engine.py，如果没找到武器，它可能会生成一个临时的 "撞击"
         # 如果我们连撞击都没给（这里是根据距离选的），我们看它是否返回 None
         print("   [PASS] 成功处理无可用武器状态。")
    else:
        print(f"   [INFO] 引擎自动选择了: {attacker_weapon.name}")

# ============================================================================
# 执行全部测试
# ============================================================================
if __name__ == "__main__":
    print("="*60)
    print("🔥 开始执行系统健壮性破坏性测试")
    print("="*60)
    
    test_recursion_protection()
    test_priority_conflict()
    test_zero_stats()
    test_resource_deadlock()
    
    print("\n" + "="*60)
    print("✅ 健壮性测试完成。")
    print("="*60)
