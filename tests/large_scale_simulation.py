"""
大规模实机模拟测试 - 高达背景 30 技能大乱斗
验证：
1. 30 个不同类型的技能/特性在大量随机战斗中的表现。
2. 统计技能触发频率、胜率分布、资源消耗情况。
3. 验证动态回合限制与死等机制在随机环境下的稳定性。
"""

import sys
import os
import io
import random
from dataclasses import dataclass, field
from collections import Counter

# 确保导入路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Windows UTF-8 支持
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from src.models import Mecha, Pilot, Weapon, WeaponType, BattleContext, Effect, AttackResult
from src.skills import SkillRegistry, EffectManager, TraitManager
from src.combat.engine import BattleSimulator
from src.config import Config
from src.skill_system.processor import EffectProcessor

# ============================================================================
# 1. 扩展 EffectFactory (Mock)
# ============================================================================

class SimulationEffectFactory:
    """模拟专用的扩展效果工厂"""
    
    @staticmethod
    def get_mock_skill_pool():
        """定义 30 个高达背景的技能/特性 ID 列表"""
        return [
            # 精神/主动类 (通常由 EffectManager.add_effect 添加)
            "spirit_strike", "spirit_alert", "spirit_valor", "spirit_iron_wall", "spirit_focus",
            "spirit_zeal", "spirit_charge", "spirit_luck", "spirit_flash", "spirit_persist",
            # 特性/被动类 (机体或驾驶员自带)
            "trait_nt", "trait_expert", "trait_guard", "trait_seed", "trait_zero",
            "trait_transam", "trait_ps_armor", "trait_ifield", "trait_funnels", "trait_potential",
            "trait_hero", "trait_berserk", "trait_solar", "trait_bio_sensor", "trait_heavy_armor",
            "trait_sniper", "trait_learning", "trait_counter", "trait_shield", "trait_multi"
        ]

    @staticmethod
    def create_effect(effect_id: str, duration: int = 1) -> list[Effect]:
        """创建效果对象"""
        effs = []
        
        # 基础精神 (复用原有的或新增)
        if effect_id == "spirit_strike":
            effs.append(Effect(id="spirit_strike", name="必中", hook="HOOK_PRE_HIT_RATE", operation="set", value=100.0, duration=1, priority=100))
        elif effect_id == "spirit_alert":
            effs.append(Effect(id="spirit_alert", name="必闪", hook="HOOK_PRE_HIT_RATE", operation="set", value=0.0, duration=1, charges=1, priority=100))
        elif effect_id == "spirit_valor":
            effs.append(Effect(id="spirit_valor", name="热血", hook="HOOK_PRE_DAMAGE_MULT", operation="mul", value=2.0, duration=1, charges=1, priority=60))
        elif effect_id == "spirit_iron_wall":
             effs.append(Effect(id="spirit_iron_wall", name="铁壁", hook="HOOK_PRE_MITIGATION", operation="max", value=0.75, duration=1, priority=70))
        elif effect_id == "spirit_focus":
             effs.append(Effect(id="spirit_focus_hit", name="集中(命中)", hook="HOOK_PRE_HIT_RATE", operation="add", value=30.0, duration=1))
             effs.append(Effect(id="spirit_focus_eva", name="集中(回避)", hook="HOOK_PRE_DODGE_RATE", operation="add", value=30.0, duration=1))
        
        # 扩展精神
        elif effect_id == "spirit_zeal": # 加速 (简单模拟：增加先攻得分)
             effs.append(Effect(id="spirit_zeal", name="加速", hook="HOOK_INITIATIVE_SCORE", operation="add", value=50.0, duration=1))
        elif effect_id == "spirit_charge": # 突击 (无视距离惩罚 - 简化为全命中+20)
             effs.append(Effect(id="spirit_charge", name="突击", hook="HOOK_PRE_HIT_RATE", operation="add", value=20.0, duration=1))
        elif effect_id == "spirit_luck": # 幸运 (简化为下一次攻击提升 20% 伤害以模拟刷钱动力)
             effs.append(Effect(id="spirit_luck", name="幸运", hook="HOOK_PRE_DAMAGE_MULT", operation="mul", value=1.2, duration=1, charges=1))
        elif effect_id == "spirit_flash": # 直感 (必中+必闪)
             effs.extend(SimulationEffectFactory.create_effect("spirit_strike"))
             effs.extend(SimulationEffectFactory.create_effect("spirit_alert"))
        elif effect_id == "spirit_persist": # 不屈 (受到伤害变为 10)
             effs.append(Effect(id="spirit_persist", name="不屈", hook="HOOK_ON_DAMAGE_TAKEN", operation="set", value=10, duration=1, charges=1, priority=100))
        
        # 特性 (永久)
        elif effect_id == "trait_nt": # Newtype
             effs.append(Effect(id="trait_nt_hit", name="新人类(命中)", hook="HOOK_PRE_HIT_RATE", operation="add", value=15.0, duration=-1))
             effs.append(Effect(id="trait_nt_eva", name="新人类(回避)", hook="HOOK_PRE_DODGE_RATE", operation="add", value=15.0, duration=-1))
        elif effect_id == "trait_expert": # 精英驾驶员
             effs.append(Effect(id="trait_exp_dmg", name="精英(伤害)", hook="HOOK_PRE_DAMAGE_MULT", operation="add", value=0.1, duration=-1))
             effs.append(Effect(id="trait_exp_save", name="精英(节能)", hook="HOOK_PRE_EN_COST_MULT", operation="mul", value=0.8, duration=-1))
        elif effect_id == "trait_seed": # SEED 爆发
             effs.append(Effect(id="trait_seed_burst", name="SEED爆发", hook="HOOK_PRE_DAMAGE_MULT", operation="mul", value=1.25, duration=-1,
                               conditions=[{"type": "hp_threshold", "val": 0.5, "op": "<"}]))
        elif effect_id == "trait_zero": # ZERO System
             effs.append(Effect(id="trait_zero", name="ZERO系统", hook="HOOK_PRE_HIT_RATE", operation="add", value=40.0, duration=-1,
                               side_effects=[{"type": "modify_will", "val": -2}])) # 每次攻击掉气力
        elif effect_id == "trait_transam": # Trans-AM
             effs.append(Effect(id="trait_transam_init", name="Trans-AM(加速)", hook="HOOK_INITIATIVE_SCORE", operation="add", value=60.0, duration=-1))
             effs.append(Effect(id="trait_transam_eva", name="Trans-AM(回避)", hook="HOOK_PRE_DODGE_RATE", operation="add", value=20.0, duration=-1))
        elif effect_id == "trait_ps_armor": # PS 装甲
             effs.append(Effect(id="trait_ps_armor", name="PS装甲", hook="HOOK_PRE_MITIGATION", operation="max", value=0.3, duration=-1,
                               conditions=[{"type": "weapon_type", "val": "MELEE", "op": "=="}])) # 对物理(格斗)减伤
        elif effect_id == "trait_ifield": # I-Field
             effs.append(Effect(id="trait_ifield", name="I-Field", hook="HOOK_PRE_MITIGATION", operation="max", value=0.4, duration=-1,
                               conditions=[{"type": "weapon_type", "val": "RIFLE", "op": "=="}])) # 对光束(射击)减伤
        elif effect_id == "trait_funnels": # 浮游炮强化
             effs.append(Effect(id="trait_funnels", name="浮游炮精准", hook="HOOK_PRE_PRECISION", operation="add", value=20.0, duration=-1))
        elif effect_id == "trait_potential": # 底力
             @SkillRegistry.register_callback("cb_potential")
             def cb_potential(val, ctx, owner):
                 # 核心逻辑：HP越低加成越高
                 ratio = 1.0 - (owner.current_hp / owner.max_hp)
                 bonus = 0.5 * (ratio ** 2) # 最大+0.5
                 return val + bonus
             effs.append(Effect(id="trait_potential", name="底力", hook="HOOK_PRE_MITIGATION", operation="callback", value="cb_potential", duration=-1))
        elif effect_id == "trait_hero": # 勇者
             effs.append(Effect(id="trait_hero_crit", name="勇者(暴击)", hook="HOOK_PRE_CRIT_RATE", operation="add", value=20.0, duration=-1))
        elif effect_id == "trait_berserk": # 狂暴
             effs.append(Effect(id="trait_berserk_atk", name="狂暴(攻击)", hook="HOOK_PRE_DAMAGE_MULT", operation="mul", value=1.5, duration=-1))
             effs.append(Effect(id="trait_berserk_eva", name="狂暴(减防)", hook="HOOK_PRE_DODGE_RATE", operation="sub", value=20.0, duration=-1))
        elif effect_id == "trait_solar": # 太阳能/GN炉 (EN 回复)
             @SkillRegistry.register_callback("cb_gn_recover")
             def cb_gn(val, ctx, owner):
                 owner.current_en = min(owner.max_en, owner.current_en + 10)
                 print(f"   [Trait] {owner.name} GN炉回复了 10 EN")
                 return val
             effs.append(Effect(id="trait_solar", name="GN炉", hook="HOOK_ON_TURN_END", operation="callback", value="cb_gn_recover", duration=-1))
        elif effect_id == "trait_bio_sensor": # 生物感应器
             effs.append(Effect(id="trait_bio_sensor", name="生物感应器", hook="HOOK_PRE_PRECISION", operation="add", value=25.0, duration=-1,
                               conditions=[{"type": "will_threshold", "val": 130, "op": ">="}]))
        elif effect_id == "trait_heavy_armor": # 厚重装甲
             effs.append(Effect(id="trait_heavy_armor", name="厚重装甲", hook="HOOK_PRE_DEFENSE_LEVEL", operation="add", value=600.0, duration=-1))
        elif effect_id == "trait_sniper": # 狙击手
             effs.append(Effect(id="trait_sniper", name="狙击手(命中)", hook="HOOK_PRE_HIT_RATE", operation="add", value=25.0, duration=-1,
                               conditions=[{"type": "round_number", "val": 3, "op": ">="}])) # 后期发力
        elif effect_id == "trait_learning": # 学习电脑
             @SkillRegistry.register_callback("cb_learning")
             def cb_learning(val, ctx, owner):
                 # 每回合+5%命中
                 bonus = ctx.round_number * 5.0
                 return val + bonus
             effs.append(Effect(id="trait_learning", name="学习电脑", hook="HOOK_PRE_HIT_RATE", operation="callback", value="cb_learning", duration=-1))
        elif effect_id == "trait_counter": # 斩切/反击 (简单模拟为全方位伤害倍率修正)
             effs.append(Effect(id="trait_counter", name="反击加成", hook="HOOK_PRE_DAMAGE_MULT", operation="add", value=0.15, duration=-1))
        elif effect_id == "trait_shield": # 盾牌强化
             effs.append(Effect(id="trait_shield", name="盾牌强化(格挡)", hook="HOOK_PRE_BLOCK_RATE", operation="add", value=25.0, duration=-1))
        elif effect_id == "trait_multi": # 多重锁定 (气力优势)
             effs.append(Effect(id="trait_multi", name="多重锁定", hook="HOOK_PRE_DAMAGE_MULT", operation="add", value=0.2, duration=-1,
                               conditions=[{"type": "will_threshold", "val": 140, "op": ">="}]))
        elif effect_id == "trait_guard": # 防御
             effs.append(Effect(id="trait_guard", name="防御", hook="HOOK_PRE_MITIGATION", operation="add", value=0.15, duration=-1))
        else:
            effs.append(Effect(id=effect_id, name=effect_id, duration=duration))
            
        return effs

# ============================================================================
# 2. 统计观察者 (Observer)
# ============================================================================

class SimulationObserver:
    """观察并统计技能触发情况"""
    stats_triggers = Counter()
    stats_wins = Counter()
    stats_draws = 0
    total_battles = 0

    @classmethod
    def reset(cls):
        cls.stats_triggers.clear()
        cls.stats_wins.clear()
        cls.stats_draws = 0
        cls.total_battles = 0

    @classmethod
    def report(cls):
        print("\n" + "="*80)
        print("【大规模模拟战斗统计报告】")
        print("="*80)
        print(f"总战斗场次: {cls.total_battles}")
        print(f"平立场次: {cls.stats_draws}")
        
        print("\n1. 机体胜率统计 (Win counts):")
        for mecha_id, wins in cls.stats_wins.most_common():
             win_rate = (wins / cls.total_battles) * 100
             print(f"   - {mecha_id:<15}: {wins} 胜 ({win_rate:.1f}%)")
             
        print("\n2. 技能触发频率 Top 15 (Trigger counts):")
        for effect_id, count in cls.stats_triggers.most_common(15):
             print(f"   - {effect_id:<20}: {count} 次")
        print("="*80 + "\n")

# 注入 Hook 到 EffectProcessor 以捕获统计
original_process = EffectProcessor.process
def hooked_process(hook_name, input_value, context):
    # 这里通过包装原有的 process 逻辑来获取触发情况
    # 为了精确获取哪个 Effect 触发了，我们可以看 process 内部是否有日志
    # 实际上为了简单，我们直接拦截 collect_effects 后的执行循环
    return original_process(hook_name, input_value, context)

# 更加简单的拦截：拦截 _apply_operation
original_apply = EffectProcessor._apply_operation
def hooked_apply(effect, current_value, context, owner):
    res = original_apply(effect, current_value, context, owner)
    is_triggered = False
    if res != current_value or effect.operation == 'callback':
        is_triggered = True
    
    if is_triggered:
        SimulationObserver.stats_triggers[effect.id] += 1
    return res

EffectProcessor._apply_operation = hooked_apply

# ============================================================================
# 3. 模拟逻辑
# ============================================================================

def create_mock_mecha(mecha_id: str, pilot_name: str):
    """创建模拟机体和驾驶员"""
    pilot = Pilot(
        id=f"p_{mecha_id}", name=pilot_name,
        stat_shooting=150 + random.randint(0, 50),
        stat_melee=150 + random.randint(0, 50),
        stat_reaction=160 + random.randint(0, 40),
        stat_awakening=140 + random.randint(0, 60),
        stat_defense=120 + random.randint(0, 30)
    )
    
    mecha = Mecha(
        id=mecha_id, name=mecha_id, pilot=pilot,
        max_hp=8000 + random.randint(0, 4000),
        current_hp=0, # 会在下面重置
        max_en=200 + random.randint(0, 100),
        current_en=0,
        hit_rate=20.0, precision=15.0, crit_rate=10.0,
        dodge_rate=15.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1200 + random.randint(0, 400),
        mobility=140 + random.randint(0, 40)
    )
    mecha.current_hp = mecha.max_hp
    mecha.current_en = mecha.max_en
    
    # 分配随机武器
    w1 = Weapon(id=f"w_{mecha_id}_1", name="Standard Rifle", weapon_type=WeaponType.RIFLE, power=2000, en_cost=15, range_min=1, range_max=6)
    w2 = Weapon(id=f"w_{mecha_id}_2", name="Beam Saber", weapon_type=WeaponType.MELEE, power=1800, en_cost=0, range_min=0, range_max=1)
    mecha.weapons = [w1, w2]
    
    # 随机分配 3-5 个被动特性
    all_traits = [t for t in SimulationEffectFactory.get_mock_skill_pool() if t.startswith("trait_")]
    assigned_traits = random.sample(all_traits, k=random.randint(3, 5))
    mecha.traits = assigned_traits
    
    return mecha

def run_simulation(iterations=20):
    SimulationObserver.reset()
    
    # 重新代理 EffectFactory.create_effect 
    # (注意：我们在 skills.py 中导入了 EffectFactory 可能会有缓存，这里我们直接注入到 Registry 让其能找到效果即可)
    # 此处假设我们通过一种方式让 EffectManager 使用我们的 Mock Factory
    # 简单办法：直接修改原 EffectFactory 的方法
    import src.skill_system.effect_factory as ef
    original_create = ef.EffectFactory.create_effect
    original_trait_create = ef.EffectFactory.create_trait_effects
    ef.EffectFactory.create_effect = SimulationEffectFactory.create_effect
    ef.EffectFactory.create_trait_effects = SimulationEffectFactory.create_effect # 都用一个
    
    # 定义 4 台机体
    mecha_pool = [
        ("Nu Gundam", "Amuro Ray"),
        ("Sazabi", "Char Aznable"),
        ("Freedom", "Kira Yamato"),
        ("Wing Zero", "Heero Yuy")
    ]
    
    print(f"\n🚀 开始执行 {iterations} 场大乱斗模拟...\n")
    
    for i in range(iterations):
        # 随机挑选两台
        m_configs = random.sample(mecha_pool, 2)
        m_a = create_mock_mecha(m_configs[0][0], m_configs[0][1])
        m_b = create_mock_mecha(m_configs[1][0], m_configs[1][1])
        
        # 应用特性
        TraitManager.apply_traits(m_a)
        TraitManager.apply_traits(m_b)
        
        # 模拟开始前各随机加 1-2 个精神 (主动 Buff)
        spirit_pool = [t for t in SimulationEffectFactory.get_mock_skill_pool() if t.startswith("spirit_")]
        for m in [m_a, m_b]:
             spirits = random.sample(spirit_pool, k=random.randint(1, 2))
             for sid in spirits:
                  EffectManager.add_effect(m, sid)
        
        # 运行战斗
        # 这里关闭 stdout 避免日志刷屏太厉害，只保留关键信息
        print(f"Battle {i+1:3}: {m_a.name} vs {m_b.name}", end=" -> ")
        
        # 暂时重定向 stdout 到 stringio
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        
        try:
            sim = BattleSimulator(m_a, m_b)
            sim.run_battle()
            
            # 记录结果
            SimulationObserver.total_battles += 1
            if not m_a.is_alive():
                 SimulationObserver.stats_wins[m_b.id] += 1
                 winner = m_b.id
            elif not m_b.is_alive():
                 SimulationObserver.stats_wins[m_a.id] += 1
                 winner = m_a.id
            else:
                 hp_a = m_a.get_hp_percentage()
                 hp_b = m_b.get_hp_percentage()
                 if hp_a > hp_b:
                      SimulationObserver.stats_wins[m_a.id] += 1
                      winner = m_a.id + " (判定)"
                 elif hp_b > hp_a:
                      SimulationObserver.stats_wins[m_b.id] += 1
                      winner = m_b.id + " (判定)"
                 else:
                      SimulationObserver.stats_draws += 1
                      winner = "Draw"
        finally:
            sys.stdout = old_stdout
            print(f"Winner: {winner}")

    # 还原 Factory
    ef.EffectFactory.create_effect = original_create
    ef.EffectFactory.create_trait_effects = original_trait_create
    
    SimulationObserver.report()

if __name__ == "__main__":
    # 执行 50 场模拟 (大规模)
    run_simulation(iterations=50)
