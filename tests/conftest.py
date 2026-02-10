"""
pytest 共享配置和 Fixtures
这个文件会被 pytest 自动加载，所有测试都可以使用这里定义的 fixtures
"""

import sys
import os
import io
from pathlib import Path
import pytest  # pytest fixture 装饰器需要

# 确保 src 模块能被导入
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 注意：pytest 会自己处理 stdout/stderr，不需要在这里重定向
# 以避免与 pytest 的输出捕获机制冲突

# ============================================================================
# 导入项目模块
# ============================================================================
from src.models import (
    Mecha, Pilot, Weapon, WeaponType,
    BattleContext, Effect, Terrain
)
from src.skills import SkillRegistry, EffectManager, TraitManager
from src.combat.engine import BattleSimulator

# ============================================================================
# 自动执行的 Fixtures（每个测试前后自动运行）
# ============================================================================

@pytest.fixture(autouse=True)
def reset_skill_registry():
    """
    每个测试结束后自动清理 SkillRegistry
    防止测试之间的 Hook 和 Callback 相互干扰
    """
    yield  # 测试执行到这里
    # 测试结束后执行清理
    SkillRegistry._hooks.clear()
    SkillRegistry._callbacks.clear()

# ============================================================================
# 基础 Fixtures（测试数据）
# ============================================================================

@pytest.fixture
def basic_pilot():
    """基础驾驶员（标准属性）"""
    return Pilot(
        id="p_test", name="TestPilot",
        stat_shooting=100, stat_melee=100, stat_reaction=100,
        stat_awakening=100, stat_defense=100
    )

@pytest.fixture
def ace_pilot():
    """王牌驾驶员（高属性，用于测试高级功能）"""
    return Pilot(
        id="p_ace", name="AcePilot",
        stat_shooting=180, stat_melee=180, stat_reaction=170,
        stat_awakening=150, stat_defense=120
    )

@pytest.fixture
def basic_mecha(basic_pilot):
    """基础机体（标准属性）"""
    return Mecha(
        id="m_test", name="TestMecha", pilot=basic_pilot,
        max_hp=5000, current_hp=5000,
        max_en=100, current_en=100,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100
    )

@pytest.fixture
def heavy_mecha():
    """重型机体（高血量高防御，用于多回合测试）"""
    pilot = Pilot(
        id="p_heavy", name="HeavyPilot",
        stat_shooting=100, stat_melee=100, stat_reaction=100,
        stat_awakening=100, stat_defense=100
    )
    return Mecha(
        id="m_heavy", name="HeavyMecha", pilot=pilot,
        max_hp=50000, current_hp=50000,
        max_en=100, current_en=100,
        hit_rate=20.0, precision=10.0, crit_rate=0.0,
        dodge_rate=0.0, parry_rate=0.0, block_rate=0.0,
        defense_level=2000, mobility=50
    )

@pytest.fixture
def basic_weapon():
    """基础武器（光束步枪）"""
    return Weapon(
        id="w_rifle", name="Beam Rifle",
        weapon_type=WeaponType.RIFLE,
        power=1000, en_cost=10,
        range_min=1000, range_max=6000
    )

@pytest.fixture
def heavy_weapon():
    """重型武器（火箭筒，高伤害高消耗）"""
    return Weapon(
        id="w_bazooka", name="Hyper Bazooka",
        weapon_type=WeaponType.HEAVY,
        power=4000, en_cost=50,
        range_min=2, range_max=6
    )

@pytest.fixture
def basic_context(basic_mecha, basic_weapon):
    """基础战斗上下文"""
    return BattleContext(
        round_number=1,
        distance=1000,
        terrain=Terrain.SPACE,
        attacker=basic_mecha,
        defender=basic_mecha,
        weapon=basic_weapon
    )

# ============================================================================
# 测试辅助函数
# ============================================================================

def create_mock_effect(effect_id: str, **kwargs) -> Effect:
    """
    创建模拟效果（用于测试，不依赖 data/skills.json）

    参数:
        effect_id: 效果ID
        **kwargs: 覆盖 Effect 的其他字段

    返回:
        Effect 对象
    """
    defaults = {
        "id": effect_id,
        "name": effect_id,
        "hook": "HOOK_DUMMY",  # 默认虚拟钩子
        "operation": "add",
        "value": 0.0,
        "duration": 1,
        "priority": 50,
        "charges": -1,
        "conditions": [],
        "side_effects": []
    }
    defaults.update(kwargs)
    return Effect(**defaults)


def create_spirit_effect(spirit_id: str, duration: int = 1):
    """
    从 EffectFactory 创建精神指令效果（用于集成测试）

    参数:
        spirit_id: 精神指令ID（如 "spirit_strike", "spirit_valor"）
        duration: 持续时间

    返回:
        Effect 对象列表

    示例:
        effects = create_spirit_effect("spirit_strike")
        assert effects[0].value == 100.0
    """
    from src.skill_system.effect_factory import EffectFactory
    return EffectFactory.create_effect(spirit_id, duration=duration)

# ============================================================================
# 战斗场景 Fixtures
# ============================================================================

@pytest.fixture
def high_hit_mecha(basic_pilot):
    """高命中率机体 (hit_rate=80)"""
    return Mecha(
        id="m_high_hit", name="HighHitMecha", pilot=basic_pilot,
        max_hp=5000, current_hp=5000,
        max_en=100, current_en=100,
        hit_rate=80.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100
    )

@pytest.fixture
def high_dodge_mecha(basic_pilot):
    """高躲闪机体 (dodge_rate=50)"""
    return Mecha(
        id="m_high_dodge", name="HighDodgeMecha", pilot=basic_pilot,
        max_hp=5000, current_hp=5000,
        max_en=100, current_en=100,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=50.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100
    )

@pytest.fixture
def crit_mecha(basic_pilot):
    """高暴击机体 (crit_rate=30)"""
    return Mecha(
        id="m_crit", name="CritMecha", pilot=basic_pilot,
        max_hp=5000, current_hp=5000,
        max_en=100, current_en=100,
        hit_rate=20.0, precision=10.0, crit_rate=30.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100
    )

@pytest.fixture
def low_hp_mecha(basic_pilot):
    """低HP机体 (HP=30%)"""
    mecha = Mecha(
        id="m_low_hp", name="LowHPMecha", pilot=basic_pilot,
        max_hp=5000, current_hp=1500,  # 30% HP
        max_en=100, current_en=100,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100
    )
    return mecha

@pytest.fixture
def high_will_mecha(basic_pilot):
    """高气力机体 (will=150)"""
    mecha = Mecha(
        id="m_high_will", name="HighWillMecha", pilot=basic_pilot,
        max_hp=5000, current_hp=5000,
        max_en=100, current_en=100,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100,
        current_will=150
    )
    return mecha


# ============================================================================
# 武器 Fixtures
# ============================================================================

@pytest.fixture
def melee_weapon():
    """格斗武器 (1000-1800m)"""
    return Weapon(
        id="w_saber", name="Beam Saber",
        weapon_type=WeaponType.MELEE,
        power=1500, en_cost=15,
        range_min=1000, range_max=1800
    )

@pytest.fixture
def rifle_weapon():
    """射击武器 (1000-6000m)"""
    return Weapon(
        id="w_rifle", name="Beam Rifle",
        weapon_type=WeaponType.RIFLE,
        power=1200, en_cost=10,
        range_min=1000, range_max=6000
    )

@pytest.fixture
def sniper_weapon():
    """狙击武器 (3000-8000m)"""
    return Weapon(
        id="w_sniper", name="Sniper Rifle",
        weapon_type=WeaponType.HEAVY,
        power=2500, en_cost=30,
        range_min=3000, range_max=8000
    )

@pytest.fixture
def beam_weapon():
    """光束武器 (用于I力场测试)"""
    return Weapon(
        id="w_beam", name="Beam Cannon",
        weapon_type=WeaponType.RIFLE,
        power=1800, en_cost=20,
        range_min=2000, range_max=5000
    )

@pytest.fixture
def low_damage_weapon():
    """低伤害武器 (伤害<2000, 用于I力场测试)"""
    return Weapon(
        id="w_weak", name="Weak Gun",
        weapon_type=WeaponType.RIFLE,
        power=800, en_cost=5,
        range_min=500, range_max=2000
    )


# ============================================================================
# 效果对象 Fixtures (用于测试各种Effect类型)
# ============================================================================

@pytest.fixture
def effect_add_hit():
    """命中+30% (add操作)"""
    return Effect(
        id="test_add_hit", name="Test Hit+",
        hook="HOOK_PRE_HIT_RATE",
        operation="add", value=30.0,
        duration=1, priority=50
    )

@pytest.fixture
def effect_mul_damage():
    """伤害x2 (mul操作)"""
    return Effect(
        id="test_mul_dmg", name="Test Dmg x2",
        hook="HOOK_PRE_DAMAGE_MULT",
        operation="mul", value=2.0,
        duration=1, priority=60
    )

@pytest.fixture
def effect_set_hit():
    """命中=100 (set操作)"""
    return Effect(
        id="test_set_hit", name="Test Set Hit",
        hook="HOOK_PRE_HIT_RATE",
        operation="set", value=100.0,
        duration=1, priority=100
    )

@pytest.fixture
def effect_prob_dodge():
    """50%概率躲闪 (trigger_chance=0.5)"""
    return Effect(
        id="test_prob_dodge", name="Test Prob Dodge",
        hook="HOOK_PRE_DODGE_RATE",
        operation="add", value=50.0,
        trigger_chance=0.5,
        duration=1, priority=80
    )

@pytest.fixture
def effect_conditional_low_hp():
    """HP<30%触发伤害x1.5"""
    return Effect(
        id="test_low_hp_berserk", name="Low HP Berserk",
        hook="HOOK_PRE_DAMAGE_MULT",
        operation="mul", value=1.5,
        conditions=[{"type": "hp_threshold", "val": 0.3, "op": "<"}],
        duration=-1, priority=60
    )

@pytest.fixture
def effect_conditional_high_will():
    """气力>=130触发伤害x1.3"""
    return Effect(
        id="test_high_will", name="High Will Boost",
        hook="HOOK_PRE_DAMAGE_MULT",
        operation="mul", value=1.3,
        conditions=[{"type": "will_threshold", "val": 130, "op": ">="}],
        duration=1, priority=60
    )

@pytest.fixture
def effect_with_charges():
    """有次数限制的效果 (charges=3)"""
    return Effect(
        id="test_charges", name="Test Charges",
        hook="HOOK_PRE_DAMAGE_MULT",
        operation="mul", value=1.5,
        charges=3, duration=1, priority=60
    )

@pytest.fixture
def effect_with_side_effects():
    """带副作用的效果 (消耗EN)"""
    return Effect(
        id="test_side_effect", name="Test Side Effect",
        hook="HOOK_PRE_DAMAGE_MULT",
        operation="mul", value=2.0,
        side_effects=[{"type": "consume_en", "val": 10}],
        duration=1, priority=60
    )


# ============================================================================
# 距离场景 Fixtures
# ============================================================================

@pytest.fixture
def close_range_context(basic_mecha, melee_weapon):
    """近距离战斗上下文 (500m)"""
    return BattleContext(
        round_number=1,
        distance=500,
        terrain=Terrain.SPACE,
        attacker=basic_mecha,
        defender=basic_mecha,
        weapon=melee_weapon
    )

@pytest.fixture
def mid_range_context(basic_mecha, rifle_weapon):
    """中距离战斗上下文 (3000m)"""
    return BattleContext(
        round_number=1,
        distance=3000,
        terrain=Terrain.SPACE,
        attacker=basic_mecha,
        defender=basic_mecha,
        weapon=rifle_weapon
    )

@pytest.fixture
def long_range_context(basic_mecha, sniper_weapon):
    """远距离战斗上下文 (6000m)"""
    return BattleContext(
        round_number=1,
        distance=6000,
        terrain=Terrain.SPACE,
        attacker=basic_mecha,
        defender=basic_mecha,
        weapon=sniper_weapon
    )

@pytest.fixture
def out_of_range_context(basic_mecha, rifle_weapon):
    """超出射程的战斗上下文 (8000m, 武器射程6000m)"""
    return BattleContext(
        round_number=1,
        distance=8000,
        terrain=Terrain.SPACE,
        attacker=basic_mecha,
        defender=basic_mecha,
        weapon=rifle_weapon
    )


# ============================================================================
# 边界条件 Fixtures
# ============================================================================

@pytest.fixture
def zero_hp_mecha(basic_pilot):
    """HP=0的机体"""
    return Mecha(
        id="m_zero_hp", name="ZeroHPMecha", pilot=basic_pilot,
        max_hp=5000, current_hp=0,
        max_en=100, current_en=100,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100
    )

@pytest.fixture
def zero_en_mecha(basic_pilot):
    """EN=0的机体"""
    return Mecha(
        id="m_zero_en", name="ZeroENMecha", pilot=basic_pilot,
        max_hp=5000, current_hp=5000,
        max_en=100, current_en=0,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100
    )

@pytest.fixture
def max_will_mecha(basic_pilot):
    """气力=最大值的机体"""
    from src.config import Config
    mecha = Mecha(
        id="m_max_will", name="MaxWillMecha", pilot=basic_pilot,
        max_hp=5000, current_hp=5000,
        max_en=100, current_en=100,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100,
        current_will=Config.WILL_MAX
    )
    return mecha


# ============================================================================
# 熟练度相关 Fixtures (用于 test_resolver_coverage.py)
# ============================================================================

@pytest.fixture
def standard_pilot():
    """标准驾驶员（带熟练度属性）"""
    return Pilot(
        id="p_standard", name="StandardPilot",
        stat_shooting=100, stat_melee=100, stat_reaction=100,
        stat_awakening=100, stat_defense=100,
        weapon_proficiency=500,
        mecha_proficiency=2000
    )

@pytest.fixture
def high_proficiency_pilot():
    """高熟练度驾驶员"""
    return Pilot(
        id="p_high_prof", name="HighProficiencyPilot",
        stat_shooting=180, stat_melee=180, stat_reaction=170,
        stat_awakening=150, stat_defense=120,
        weapon_proficiency=1000,
        mecha_proficiency=4000
    )

@pytest.fixture
def low_proficiency_pilot():
    """低熟练度驾驶员"""
    return Pilot(
        id="p_rookie", name="RookiePilot",
        stat_shooting=50, stat_melee=50, stat_reaction=50,
        stat_awakening=50, stat_defense=50,
        weapon_proficiency=100,
        mecha_proficiency=500
    )

@pytest.fixture
def normal_pilot():
    """普通驾驶员（用于复杂场景测试）"""
    return Pilot(
        id="p_normal", name="NormalPilot",
        stat_shooting=100, stat_melee=100, stat_reaction=100,
        stat_awakening=100, stat_defense=100,
        weapon_proficiency=500,
        mecha_proficiency=2000
    )


# ============================================================================
# 特殊机体类型 Fixtures (用于 test_resolver_coverage.py)
# ============================================================================

@pytest.fixture
def balanced_mecha(standard_pilot):
    """平衡机体（标准属性）"""
    return Mecha(
        id="m_balanced", name="BalancedMecha", pilot=standard_pilot,
        max_hp=5000, current_hp=5000,
        max_en=100, current_en=100,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100
    )

@pytest.fixture
def offensive_mecha(standard_pilot):
    """进攻型机体（高命中、高暴击、低防御）"""
    return Mecha(
        id="m_offensive", name="OffensiveMecha", pilot=standard_pilot,
        max_hp=4000, current_hp=4000,
        max_en=100, current_en=100,
        hit_rate=30.0, precision=20.0, crit_rate=20.0,
        dodge_rate=5.0, parry_rate=5.0, block_rate=5.0,
        defense_level=800, mobility=120
    )

@pytest.fixture
def defensive_mecha(standard_pilot):
    """防御型机体（低命中、高闪避、高格挡）"""
    return Mecha(
        id="m_defensive", name="DefensiveMecha", pilot=standard_pilot,
        max_hp=6000, current_hp=6000,
        max_en=100, current_en=100,
        hit_rate=5.0, precision=5.0, crit_rate=0.0,
        dodge_rate=30.0, parry_rate=25.0, block_rate=20.0,
        defense_level=1500, mobility=80
    )


# ============================================================================
# 满资源机体 Fixtures (用于 test_side_effects.py)
# ============================================================================

@pytest.fixture
def full_mecha(basic_pilot):
    """满资源机体（HP/EN/Will都是满值）"""
    return Mecha(
        id="m_full", name="FullMecha", pilot=basic_pilot,
        max_hp=5000, current_hp=5000,
        max_en=100, current_en=100,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100,
        current_will=120
    )


# ============================================================================
# 特殊机体 Fixtures (用于 test_complex_scenarios.py)
# ============================================================================

@pytest.fixture
def gundam_rx78(ace_pilot):
    """RX-78高达（进攻型，用于复杂场景测试）"""
    mecha = Mecha(
        id="m_rx78", name="RX-78高达",
        pilot=ace_pilot,
        max_hp=5500, current_hp=5500,
        max_en=120, current_en=120,
        hit_rate=25.0, precision=20.0, crit_rate=15.0,
        dodge_rate=15.0, parry_rate=10.0, block_rate=5.0,
        defense_level=1200, mobility=120,
        traits=["trait_newtype", "trait_gundam"]
    )

    # 添加武器
    beam_rifle = Weapon(
        id="w_beam_rifle", name="光束步枪",
        weapon_type=WeaponType.RIFLE,
        power=1500, en_cost=12,
        range_min=1000, range_max=6000,
        hit_penalty=0.0
    )
    beam_saber = Weapon(
        id="w_beam_saber", name="光束军刀",
        weapon_type=WeaponType.MELEE,
        power=2000, en_cost=15,
        range_min=1000, range_max=1800,
        hit_penalty=5.0
    )

    mecha.weapons = [beam_rifle, beam_saber]
    return mecha

@pytest.fixture
def zaku_ii(normal_pilot):
    """扎古II（平衡型，用于复杂场景测试）"""
    mecha = Mecha(
        id="m_zaku", name="扎古II",
        pilot=normal_pilot,
        max_hp=4500, current_hp=4500,
        max_en=100, current_en=100,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100
    )

    # 添加武器
    machine_gun = Weapon(
        id="w_mgun", name="机关枪",
        weapon_type=WeaponType.RIFLE,
        power=800, en_cost=5,
        range_min=500, range_max=4000,
        hit_penalty=0.0
    )
    heat_hawk = Weapon(
        id="w_heat_hawk", name="热能斧",
        weapon_type=WeaponType.MELEE,
        power=1200, en_cost=10,
        range_min=1000, range_max=1500,
        hit_penalty=10.0
    )

    mecha.weapons = [machine_gun, heat_hawk]
    return mecha


# ============================================================================
# 特殊上下文 Fixtures
# ============================================================================

@pytest.fixture
def standard_context(balanced_mecha):
    """标准战斗上下文（用于 test_resolver_coverage.py）"""
    defender = Mecha(
        id="m_defender", name="Defender",
        pilot=balanced_mecha.pilot,
        max_hp=5000, current_hp=5000,
        max_en=100, current_en=100,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100
    )

    return BattleContext(
        round_number=1,
        distance=1000,
        terrain=None,
        attacker=balanced_mecha,
        defender=defender,
        weapon=None
    )

@pytest.fixture
def full_context(full_mecha):
    """满资源战斗上下文（用于 test_side_effects.py）"""
    defender = Mecha(
        id="m_enemy", name="EnemyMecha",
        pilot=full_mecha.pilot,
        max_hp=5000, current_hp=5000,
        max_en=100, current_en=100,
        hit_rate=10.0, precision=10.0, crit_rate=5.0,
        dodge_rate=10.0, parry_rate=10.0, block_rate=10.0,
        defense_level=1000, mobility=100
    )

    return BattleContext(
        round_number=1,
        distance=1000,
        terrain=None,
        attacker=full_mecha,
        defender=defender,
        weapon=None
    )

@pytest.fixture
def battlefield(gundam_rx78, zaku_ii):
    """战场环境（高达 VS 扎古，用于 test_complex_scenarios.py）"""
    return BattleContext(
        round_number=1,
        distance=3000,  # 中距离
        terrain=None,
        attacker=gundam_rx78,
        defender=zaku_ii,
        weapon=gundam_rx78.weapons[0]  # 使用光束步枪
    )
