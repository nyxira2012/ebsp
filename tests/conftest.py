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
    MechaSnapshot, PilotConfig, WeaponSnapshot, WeaponType,
    BattleContext, Effect, Terrain, SlotType,
    Mecha, Pilot, Weapon
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
    """基础驾驶员（标准属性）- 使用 PilotConfig"""
    return PilotConfig(
        id="p_test", name="TestPilot", portrait_id="p_001",
        stat_shooting=100, stat_melee=100, stat_reaction=100,
        stat_awakening=100, stat_defense=100
    )

@pytest.fixture
def ace_pilot():
    """王牌驾驶员（高属性）"""
    return PilotConfig(
        id="p_ace", name="AcePilot", portrait_id="p_002",
        stat_shooting=180, stat_melee=180, stat_reaction=170,
        stat_awakening=150, stat_defense=120
    )

@pytest.fixture
def basic_mecha(basic_pilot):
    """基础机体快照"""
    # 模拟 pilot_stats_backup
    pilot_stats = {
        "stat_shooting": basic_pilot.stat_shooting,
        "stat_melee": basic_pilot.stat_melee,
        "stat_awakening": basic_pilot.stat_awakening,
        "stat_defense": basic_pilot.stat_defense,
        "stat_reaction": basic_pilot.stat_reaction
    }

    return MechaSnapshot(
        instance_id="m_test", mecha_name="TestMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )

@pytest.fixture
def heavy_mecha():
    """重型机体（高血量高防御，用于多回合测试）"""
    pilot = Pilot(
        id="p_heavy", name="HeavyPilot", portrait_id="p_heavy_img",
        stat_shooting=100, stat_melee=100, stat_reaction=100,
        stat_awakening=100, stat_defense=100
    )
    return Mecha(
        instance_id="m_heavy", mecha_name="HeavyMecha", 
        main_portrait="m_heavy_img", model_asset="default",
        final_max_hp=50000, current_hp=50000,
        final_max_en=100, current_en=100,
        final_hit=20.0, final_precision=10.0, final_crit=0.0,
        final_dodge=0.0, final_parry=0.0, final_block=0.0,
        final_armor=2000, final_mobility=50,
        block_reduction=1000,
        pilot_stats_backup={
            "stat_shooting": pilot.stat_shooting,
            "stat_melee": pilot.stat_melee,
            "stat_reaction": pilot.stat_reaction,
            "stat_awakening": pilot.stat_awakening,
            "stat_defense": pilot.stat_defense,
        }
    )

@pytest.fixture
def basic_weapon():
    """基础武器（光束步枪）"""
    return WeaponSnapshot(
        uid="w_rifle_uid", definition_id="w_rifle", name="Beam Rifle",
        type=WeaponType.SHOOTING,
        final_power=1000, en_cost=10,
        range_min=1000, range_max=6000,
        will_req=0, anim_id="anim_01"
    )

@pytest.fixture
def heavy_weapon():
    """重型武器（火箭筒）- 这里的分类可能需要后续调整，暂用 SPECIAL 或 SHOOTING"""
    return WeaponSnapshot(
        uid="w_bazooka_uid", definition_id="w_bazooka", name="Hyper Bazooka",
        type=WeaponType.SHOOTING, # 这里以前是 HEAVY，现在只有 MELEE/SHOOTING/SPECIAL
        final_power=4000, en_cost=50,
        range_min=2000, range_max=6000, # 射程调整适配新逻辑
        will_req=0, anim_id="anim_02"
    )

@pytest.fixture
def basic_context(basic_mecha, basic_weapon):
    """基础战斗上下文"""
    return BattleContext(
        round_number=1,
        distance=1000,
        terrain=Terrain.SPACE,
        mecha_a=basic_mecha,
        mecha_b=basic_mecha,
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
    """高命中率机体"""
    pilot_stats = {
        "stat_shooting": basic_pilot.stat_shooting,
        "stat_melee": basic_pilot.stat_melee,
        "stat_awakening": basic_pilot.stat_awakening,
        "stat_defense": basic_pilot.stat_defense,
        "stat_reaction": basic_pilot.stat_reaction
    }
    return MechaSnapshot(
        instance_id="m_high_hit", mecha_name="HighHitMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=80.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )

@pytest.fixture
def high_dodge_mecha(basic_pilot):
    pilot_stats = {
        "stat_shooting": basic_pilot.stat_shooting,
        "stat_melee": basic_pilot.stat_melee,
        "stat_awakening": basic_pilot.stat_awakening,
        "stat_defense": basic_pilot.stat_defense,
        "stat_reaction": basic_pilot.stat_reaction
    }
    return MechaSnapshot(
        instance_id="m_high_dodge", mecha_name="HighDodgeMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=50.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )

@pytest.fixture
def crit_mecha(basic_pilot):
    pilot_stats = {
        "stat_shooting": basic_pilot.stat_shooting,
        "stat_melee": basic_pilot.stat_melee,
        "stat_awakening": basic_pilot.stat_awakening,
        "stat_defense": basic_pilot.stat_defense,
        "stat_reaction": basic_pilot.stat_reaction
    }
    return MechaSnapshot(
        instance_id="m_crit", mecha_name="CritMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=20.0, final_precision=10.0, final_crit=30.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )

@pytest.fixture
def low_hp_mecha(basic_pilot):
    """低HP机体 (30% HP)"""
    pilot_stats = {
        "stat_shooting": basic_pilot.stat_shooting,
        "stat_melee": basic_pilot.stat_melee,
        "stat_awakening": basic_pilot.stat_awakening,
        "stat_defense": basic_pilot.stat_defense,
        "stat_reaction": basic_pilot.stat_reaction
    }
    return MechaSnapshot(
        instance_id="m_low_hp", mecha_name="LowHPMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=1500, # 30%
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )

@pytest.fixture
def high_will_mecha(basic_pilot):
    """高气力机体"""
    pilot_stats = {
        "stat_shooting": basic_pilot.stat_shooting,
        "stat_melee": basic_pilot.stat_melee,
        "stat_awakening": basic_pilot.stat_awakening,
        "stat_defense": basic_pilot.stat_defense,
        "stat_reaction": basic_pilot.stat_reaction
    }
    snap = MechaSnapshot(
        instance_id="m_high_will", mecha_name="HighWillMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )
    snap.current_will = 150
    return snap


# ============================================================================
# 武器 Fixtures
# ============================================================================

@pytest.fixture
def melee_weapon():
    """格斗武器 (1000-1800m)"""
    return WeaponSnapshot(
        uid="w_saber_uid", definition_id="w_saber", name="Beam Saber",
        type=WeaponType.MELEE,
        final_power=1500, en_cost=15,
        range_min=1000, range_max=1800,
        will_req=0, anim_id="anim_saber"
    )

@pytest.fixture
def rifle_weapon():
    """射击武器 (1000-6000m)"""
    return WeaponSnapshot(
        uid="w_rifle_uid", definition_id="w_rifle", name="Beam Rifle",
        type=WeaponType.SHOOTING,
        final_power=1200, en_cost=10,
        range_min=1000, range_max=6000,
        will_req=0, anim_id="anim_rifle"
    )

@pytest.fixture
def sniper_weapon():
    """狙击武器 (SHOOTING type, long range)"""
    return WeaponSnapshot(
        uid="w_sniper_uid", definition_id="w_sniper", name="Sniper Rifle",
        type=WeaponType.SHOOTING, # 原 HEAVY，现归为 SHOOTING 或 SPECIAL
        final_power=2500, en_cost=30,
        range_min=3000, range_max=8000,
        will_req=0, anim_id="anim_sniper"
    )

@pytest.fixture
def beam_weapon():
    """光束武器"""
    return WeaponSnapshot(
        uid="w_beam_uid", definition_id="w_beam", name="Beam Cannon",
        type=WeaponType.SHOOTING,
        final_power=1800, en_cost=20,
        range_min=2000, range_max=5000, will_req=0, anim_id="anim_beam"
    )

@pytest.fixture
def low_damage_weapon():
    """低伤害武器"""
    return WeaponSnapshot(
        uid="w_weak_uid", definition_id="w_weak", name="Weak Gun",
        type=WeaponType.SHOOTING,
        final_power=800, en_cost=5,
        range_min=500, range_max=2000, will_req=0, anim_id="anim_weak"
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
    from src.models import Condition
    return Effect(
        id="test_low_hp_berserk", name="Low HP Berserk",
        hook="HOOK_PRE_DAMAGE_MULT",
        operation="mul", value=1.5,
        conditions=[Condition(type="hp_threshold", params={"val": 0.3, "op": "<"})],
        duration=-1, priority=60
    )

@pytest.fixture
def effect_conditional_high_will():
    """气力>=130触发伤害x1.3"""
    from src.models import Condition
    return Effect(
        id="test_high_will", name="High Will Boost",
        hook="HOOK_PRE_DAMAGE_MULT",
        operation="mul", value=1.3,
        conditions=[Condition(type="will_threshold", params={"val": 130, "op": ">="})],
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
    from src.models import SideEffect
    return Effect(
        id="test_side_effect", name="Test Side Effect",
        hook="HOOK_PRE_DAMAGE_MULT",
        operation="mul", value=2.0,
        side_effects=[SideEffect(type="consume_en", params={"val": 10})],
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
        mecha_a=basic_mecha,
        mecha_b=basic_mecha,
        weapon=melee_weapon
    )

@pytest.fixture
def mid_range_context(basic_mecha, rifle_weapon):
    """中距离战斗上下文 (3000m)"""
    return BattleContext(
        round_number=1,
        distance=3000,
        terrain=Terrain.SPACE,
        mecha_a=basic_mecha,
        mecha_b=basic_mecha,
        weapon=rifle_weapon
    )

@pytest.fixture
def long_range_context(basic_mecha, sniper_weapon):
    """远距离战斗上下文 (6000m)"""
    return BattleContext(
        round_number=1,
        distance=6000,
        terrain=Terrain.SPACE,
        mecha_a=basic_mecha,
        mecha_b=basic_mecha,
        weapon=sniper_weapon
    )

@pytest.fixture
def out_of_range_context(basic_mecha, rifle_weapon):
    """超出射程的战斗上下文 (8000m, 武器射程6000m)"""
    return BattleContext(
        round_number=1,
        distance=8000,
        terrain=Terrain.SPACE,
        mecha_a=basic_mecha,
        mecha_b=basic_mecha,
        weapon=rifle_weapon
    )


# ============================================================================
# 边界条件 Fixtures
# ============================================================================

@pytest.fixture
def zero_hp_mecha(basic_pilot):
    """HP=0的机体"""
    pilot_stats = {
        "stat_shooting": basic_pilot.stat_shooting,
        "stat_melee": basic_pilot.stat_melee,
        "stat_awakening": basic_pilot.stat_awakening,
        "stat_defense": basic_pilot.stat_defense,
        "stat_reaction": basic_pilot.stat_reaction
    }
    return MechaSnapshot(
        instance_id="m_zero_hp", mecha_name="ZeroHPMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=0,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )

@pytest.fixture
def zero_en_mecha(basic_pilot):
    """EN=0的机体"""
    pilot_stats = {
        "stat_shooting": basic_pilot.stat_shooting,
        "stat_melee": basic_pilot.stat_melee,
        "stat_awakening": basic_pilot.stat_awakening,
        "stat_defense": basic_pilot.stat_defense,
        "stat_reaction": basic_pilot.stat_reaction
    }
    return MechaSnapshot(
        instance_id="m_zero_en", mecha_name="ZeroENMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=0,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )

@pytest.fixture
def max_will_mecha(basic_pilot):
    """最大气力机体"""
    from src.config import Config
    pilot_stats = {
        "stat_shooting": basic_pilot.stat_shooting,
        "stat_melee": basic_pilot.stat_melee,
        "stat_awakening": basic_pilot.stat_awakening,
        "stat_defense": basic_pilot.stat_defense,
        "stat_reaction": basic_pilot.stat_reaction
    }
    snap = MechaSnapshot(
        instance_id="m_max_will", mecha_name="MaxWillMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )
    snap.current_will = Config.WILL_MAX
    return snap


# ============================================================================
# 熟练度相关 Fixtures (用于 test_resolver_coverage.py)
# ============================================================================

@pytest.fixture
def standard_pilot():
    """标准驾驶员（旧字段 weapon_proficiency 和 mecha_proficiency 已移除/不在 PilotConfig 中）"""
    # 如果这些是测试必须的，可能需要在 PilotConfig 中临时加回或者测试逻辑更改
    # 暂时只初始化基础属性
    return PilotConfig(
        id="p_standard", name="StandardPilot", portrait_id="p_std",
        stat_shooting=100, stat_melee=100, stat_reaction=100,
        stat_awakening=100, stat_defense=100
    )

@pytest.fixture
def high_proficiency_pilot():
    """高熟练度驾驶员"""
    return PilotConfig(
        id="p_high_prof", name="HighProficiencyPilot", portrait_id="p_high",
        stat_shooting=180, stat_melee=180, stat_reaction=170,
        stat_awakening=150, stat_defense=120
    )

@pytest.fixture
def low_proficiency_pilot():
    """低熟练度驾驶员"""
    return PilotConfig(
        id="p_rookie", name="RookiePilot", portrait_id="p_low",
        stat_shooting=50, stat_melee=50, stat_reaction=50,
        stat_awakening=50, stat_defense=50,
    )

@pytest.fixture
def normal_pilot():
    return PilotConfig(
        id="p_normal", name="NormalPilot", portrait_id="p_norm",
        stat_shooting=100, stat_melee=100, stat_reaction=100,
        stat_awakening=100, stat_defense=100,
    )


# ============================================================================
# 特殊机体类型 Fixtures (用于 test_resolver_coverage.py)
# ============================================================================

@pytest.fixture
def balanced_mecha(standard_pilot):
    """平衡机体"""
    pilot_stats = {
        "stat_shooting": standard_pilot.stat_shooting,
        "stat_melee": standard_pilot.stat_melee,
        "stat_awakening": standard_pilot.stat_awakening,
        "stat_defense": standard_pilot.stat_defense,
        "stat_reaction": standard_pilot.stat_reaction
    }
    return MechaSnapshot(
        instance_id="m_balanced", mecha_name="BalancedMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )

@pytest.fixture
def offensive_mecha(standard_pilot):
    """进攻型机体"""
    pilot_stats = {
        "stat_shooting": standard_pilot.stat_shooting,
        "stat_melee": standard_pilot.stat_melee,
        "stat_awakening": standard_pilot.stat_awakening,
        "stat_defense": standard_pilot.stat_defense,
        "stat_reaction": standard_pilot.stat_reaction
    }
    return MechaSnapshot(
        instance_id="m_offensive", mecha_name="OffensiveMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=4000, current_hp=4000,
        final_max_en=100, current_en=100,
        final_armor=800, final_mobility=120,
        final_hit=30.0, final_precision=20.0, final_crit=20.0,
        final_dodge=5.0, final_parry=5.0, final_block=5.0, block_reduction=400,
        pilot_stats_backup=pilot_stats
    )

@pytest.fixture
def defensive_mecha(standard_pilot):
    """防御型机体"""
    pilot_stats = {
        "stat_shooting": standard_pilot.stat_shooting,
        "stat_melee": standard_pilot.stat_melee,
        "stat_awakening": standard_pilot.stat_awakening,
        "stat_defense": standard_pilot.stat_defense,
        "stat_reaction": standard_pilot.stat_reaction
    }
    return MechaSnapshot(
        instance_id="m_defensive", mecha_name="DefensiveMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=6000, current_hp=6000,
        final_max_en=100, current_en=100,
        final_armor=1500, final_mobility=80,
        final_hit=5.0, final_precision=5.0, final_crit=0.0,
        final_dodge=30.0, final_parry=25.0, final_block=20.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )


# ============================================================================
# 满资源机体 Fixtures (用于 test_side_effects.py)
# ============================================================================

@pytest.fixture
def full_mecha(basic_pilot):
    """满资源机体"""
    pilot_stats = {
        "stat_shooting": basic_pilot.stat_shooting,
        "stat_melee": basic_pilot.stat_melee,
        "stat_awakening": basic_pilot.stat_awakening,
        "stat_defense": basic_pilot.stat_defense,
        "stat_reaction": basic_pilot.stat_reaction
    }
    snap = MechaSnapshot(
        instance_id="m_full", mecha_name="FullMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=pilot_stats
    )
    snap.current_will = 120
    return snap


# ============================================================================
# 特殊机体 Fixtures (用于 test_complex_scenarios.py)
# ============================================================================

@pytest.fixture
def gundam_rx78(ace_pilot):
    """RX-78高达"""
    pilot_stats = {"stat_shooting": ace_pilot.stat_shooting}
    mecha = MechaSnapshot(
        instance_id="m_rx78", mecha_name="RX-78高达",
        main_portrait="m_gundam", model_asset="gundam",
        final_max_hp=5500, current_hp=5500,
        final_max_en=120, current_en=120,
        final_armor=1200, final_mobility=120,
        final_hit=25.0, final_precision=20.0, final_crit=15.0,
        final_dodge=15.0, final_parry=10.0, final_block=5.0, block_reduction=600,
        pilot_stats_backup=pilot_stats
    )
    # Traits (legacy support or new system) can be added via skills or manually
    mecha.skills = ["trait_newtype", "trait_gundam"]

    # 添加武器
    beam_rifle = WeaponSnapshot(
        uid="w_br_01", definition_id="w_beam_rifle", name="光束步枪",
        type=WeaponType.SHOOTING,
        final_power=1500, en_cost=12,
        range_min=1000, range_max=6000, will_req=0, anim_id="a_br",
        hit_mod=0.0
    )
    beam_saber = WeaponSnapshot(
        uid="w_bs_01", definition_id="w_beam_saber", name="光束军刀",
        type=WeaponType.MELEE,
        final_power=2000, en_cost=15,
        range_min=1000, range_max=1800, will_req=0, anim_id="a_bs",
        hit_mod=5.0
    )

    mecha.weapons = [beam_rifle, beam_saber]
    return mecha

@pytest.fixture
def zaku_ii(normal_pilot):
    """扎古II"""
    mecha = MechaSnapshot(
        instance_id="m_zaku", mecha_name="扎古II",
        main_portrait="m_zaku", model_asset="zaku",
        final_max_hp=4500, current_hp=4500,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup={}
    )

    # 添加武器
    machine_gun = WeaponSnapshot(
        uid="w_mg_01", definition_id="w_mgun", name="机关枪",
        type=WeaponType.SHOOTING,
        final_power=800, en_cost=5,
        range_min=500, range_max=4000, will_req=0, anim_id="a_mg",
        hit_mod=0.0
    )
    heat_hawk = WeaponSnapshot(
        uid="w_hh_01", definition_id="w_heat_hawk", name="热能斧",
        type=WeaponType.MELEE,
        final_power=1200, en_cost=10,
        range_min=1000, range_max=1500, will_req=0, anim_id="a_hh",
        hit_mod=10.0
    )

    mecha.weapons = [machine_gun, heat_hawk]
    return mecha


# ============================================================================
# 特殊上下文 Fixtures
# ============================================================================

@pytest.fixture
def standard_context(balanced_mecha):
    """标准战斗上下文"""
    mecha_b = MechaSnapshot(
        instance_id="m_defender", mecha_name="Defender",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup=balanced_mecha.pilot_stats_backup
    )

    return BattleContext(
        round_number=1,
        distance=1000,
        terrain=Terrain.SPACE,
        mecha_a=balanced_mecha,
        mecha_b=mecha_b,
        weapon=None
    )

@pytest.fixture
def full_context(full_mecha):
    """满资源战斗上下文"""
    mecha_b = MechaSnapshot(
        instance_id="m_enemy", mecha_name="EnemyMecha",
        main_portrait="m_001", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0, block_reduction=500,
        pilot_stats_backup={}
    )

    return BattleContext(
        round_number=1,
        distance=1000,
        terrain=Terrain.SPACE,
        mecha_a=full_mecha,
        mecha_b=mecha_b,
        weapon=None
    )

@pytest.fixture
def battlefield(gundam_rx78, zaku_ii):
    """战场环境（高达 VS 扎古，用于 test_complex_scenarios.py）"""
    return BattleContext(
        round_number=1,
        distance=3000,  # 中距离
        terrain=Terrain.SPACE,
        mecha_a=gundam_rx78,
        mecha_b=zaku_ii,
        weapon=gundam_rx78.weapons[0]  # 使用光束步枪
    )
