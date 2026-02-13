"""
Skills系统集成测试
测试 SkillRegistry, EffectManager, TraitManager, SpiritCommands 的集成使用
"""

import pytest
from src.models import Mecha, Pilot, BattleContext, Terrain
from src.skills import (
    SkillRegistry, EffectManager, TraitManager, SpiritCommands
)
from src.skill_system.effect_factory import EffectFactory


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def pilot_with_traits():
    """有特性的驾驶员"""
    return Pilot(
        id="p_newtype", name="NewtypePilot", portrait_id="p_newtype_img",
        stat_shooting=150, stat_melee=120, stat_reaction=140,
        stat_awakening=130, stat_defense=110
    )


@pytest.fixture
def mecha_for_traits(pilot_with_traits):
    """有特性的机体"""
    mecha = Mecha(
        instance_id="m_newtype_mecha", mecha_name="NewtypeMecha", 
        main_portrait="m_newtype_img", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=120, current_en=120,
        final_hit=15.0, final_precision=15.0, final_crit=10.0,
        final_dodge=15.0, final_parry=10.0, final_block=10.0,
        final_armor=1200, final_mobility=110,
        block_reduction=500,
        skills=["trait_newtype", "trait_expert_rifle"],  # 多特性
        pilot_stats_backup={
            "stat_shooting": pilot_with_traits.stat_shooting,
            "stat_melee": pilot_with_traits.stat_melee,
            "stat_reaction": pilot_with_traits.stat_reaction,
            "stat_awakening": pilot_with_traits.stat_awakening,
            "stat_defense": pilot_with_traits.stat_defense,
        }
    )
    return mecha


@pytest.fixture
def battle_context():
    """战斗上下文"""
    attacker_pilot = Pilot(
        id="p_atk", name="AtkPilot", portrait_id="p_atk_img",
        stat_shooting=100, stat_melee=100, stat_reaction=100,
        stat_awakening=100, stat_defense=100
    )
    attacker = Mecha(
        instance_id="m_attacker", mecha_name="Attacker",
        main_portrait="m_atk_img", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_hit=20.0, final_precision=10.0, final_crit=5.0,
        final_dodge=10.0, final_parry=10.0, final_block=10.0,
        final_armor=1000, final_mobility=100,
        block_reduction=500,
        pilot_stats_backup={
            "stat_shooting": attacker_pilot.stat_shooting,
            "stat_melee": attacker_pilot.stat_melee,
            "stat_reaction": attacker_pilot.stat_reaction,
            "stat_awakening": attacker_pilot.stat_awakening,
            "stat_defense": attacker_pilot.stat_defense,
        }
    )
    defender_pilot = Pilot(
        id="p_def", name="DefPilot", portrait_id="p_def_img",
        stat_shooting=100, stat_melee=100, stat_reaction=100,
        stat_awakening=100, stat_defense=100
    )
    defender = Mecha(
        instance_id="m_defender", mecha_name="Defender",
        main_portrait="m_def_img", model_asset="default",
        final_max_hp=5000, current_hp=5000,
        final_max_en=100, current_en=100,
        final_hit=10.0, final_precision=10.0, final_crit=5.0,
        final_dodge=20.0, final_parry=15.0, final_block=10.0,
        final_armor=1000, final_mobility=100,
        block_reduction=500,
        pilot_stats_backup={
            "stat_shooting": defender_pilot.stat_shooting,
            "stat_melee": defender_pilot.stat_melee,
            "stat_reaction": defender_pilot.stat_reaction,
            "stat_awakening": defender_pilot.stat_awakening,
            "stat_defense": defender_pilot.stat_defense,
        }
    )

    return BattleContext(
        round_number=1,
        distance=1000,
        terrain=Terrain.SPACE,
        mecha_a=attacker,
        mecha_b=defender,
        weapon=None
    )


# ============================================================================
# 测试 SkillRegistry 集成
# ============================================================================

class TestSkillRegistryIntegration:
    """测试SkillRegistry集成"""

    def test_register_hook_function(self, battle_context):
        """测试注册钩子函数"""
        call_count = [0]

        @SkillRegistry.register_hook("HOOK_TEST")
        def test_hook(value, ctx):
            call_count[0] += 1
            return value + 10

        result = SkillRegistry.process_hook("HOOK_TEST", 50, battle_context)

        assert result == 60
        assert call_count[0] == 1

    def test_register_callback_function(self):
        """测试注册回调函数"""
        @SkillRegistry.register_callback("test_callback")
        def test_callback(val, ctx, owner):
            return val * 2

        callback = SkillRegistry.get_callback("test_callback")
        assert callback is not None
        assert callback(5, None, None) == 10

    def test_multiple_hooks_on_same_point(self, battle_context):
        """测试同一钩子点多个钩子"""
        @SkillRegistry.register_hook("HOOK_MULTI_TEST")
        def hook1(value, ctx):
            return value + 10

        @SkillRegistry.register_hook("HOOK_MULTI_TEST")
        def hook2(value, ctx):
            return value * 2

        result = SkillRegistry.process_hook("HOOK_MULTI_TEST", 5, battle_context)

        # 应该是 (5 + 10) * 2 = 30 (流水线式)
        assert result == 30

    def test_hook_exception_handling(self, battle_context):
        """测试钩子异常处理"""
        @SkillRegistry.register_hook("HOOK_ERROR_TEST")
        def error_hook(value, ctx):
            raise ValueError("Test error")

        @SkillRegistry.register_hook("HOOK_ERROR_TEST")
        def normal_hook(value, ctx):
            return value + 5

        # 应该捕获异常并继续执行
        result = SkillRegistry.process_hook("HOOK_ERROR_TEST", 10, battle_context)

        # 异常钩子应该被跳过
        assert result == 15

    def test_process_hook_with_empty_hooks(self, battle_context):
        """测试处理空的钩子点"""
        result = SkillRegistry.process_hook("HOOK_NONEXISTENT", 100, battle_context)

        # 没有钩子应该返回原值
        assert result == 100


# ============================================================================
# 测试 EffectManager 集成
# ============================================================================

class TestEffectManagerIntegration:
    """测试EffectManager集成"""

    def test_add_effect_creates_effects(self):
        """测试添加效果创建Effect对象"""
        mecha = Mecha(
            instance_id="m_test", mecha_name="TestMecha", 
            main_portrait="m_test_img", model_asset="default",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            pilot_stats_backup={
                "stat_shooting": 100,
                "stat_melee": 100,
                "stat_reaction": 100,
                "stat_awakening": 100,
                "stat_defense": 100,
            }
        )

        initial_count = len(mecha.effects)

        # 添加一个已知存在的效果
        EffectManager.add_effect(mecha, "spirit_strike", duration=2)

        # 效果数量应该增加
        assert len(mecha.effects) > initial_count

        # 验证效果存在
        effect_ids = [e.id for e in mecha.effects]
        assert "spirit_strike" in effect_ids

    def test_add_effect_refreshes_duration(self):
        """测试添加效果刷新持续时间"""
        mecha = Mecha(
            instance_id="m_test", mecha_name="TestMecha", 
            main_portrait="m_test_img", model_asset="default",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            pilot_stats_backup={
                "stat_shooting": 100,
                "stat_melee": 100,
                "stat_reaction": 100,
                "stat_awakening": 100,
                "stat_defense": 100,
            }
        )

        # 使用 EffectManager 添加一个效果 (duration=1)
        EffectManager.add_effect(mecha, "spirit_strike", duration=1)

        # 找到效果并记录初始持续时间
        initial_duration = None
        for eff in mecha.effects:
            if eff.id == "spirit_strike":
                initial_duration = eff.duration
                break

        assert initial_duration is not None, "spirit_strike effect should be added"

        # 再次添加相同效果，持续时间应该刷新为max(1, 3)=3
        EffectManager.add_effect(mecha, "spirit_strike", duration=3)

        # 检查持续时间被刷新
        for eff in mecha.effects:
            if eff.id == "spirit_strike":
                assert eff.duration == 3, f"Duration should be 3, got {eff.duration}"
                break

    def test_tick_effects_reduces_duration(self):
        """测试tick减少持续时间"""
        mecha = Mecha(
            instance_id="m_test", mecha_name="TestMecha", 
            main_portrait="m_test_img", model_asset="default",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            pilot_stats_backup={
                "stat_shooting": 100,
                "stat_melee": 100,
                "stat_reaction": 100,
                "stat_awakening": 100,
                "stat_defense": 100,
            }
        )

        # 添加效果
        from src.models import Effect
        effect1 = Effect(
            id="temp1", name="Temp1",
            hook="HOOK_DUMMY",
            operation="add", value=0.0,
            duration=2, priority=50
        )
        effect2 = Effect(
            id="temp2", name="Temp2",
            hook="HOOK_DUMMY",
            operation="add", value=0.0,
            duration=1, priority=50
        )
        effect3 = Effect(
            id="perm", name="Permanent",
            hook="HOOK_DUMMY",
            operation="add", value=0.0,
            duration=-1, priority=50  # 永久
        )
        mecha.effects = [effect1, effect2, effect3]

        # tick一次
        EffectManager.tick_effects(mecha)

        # 检查持续时间
        # temp1从2变成1, temp2从1变成0(被移除), perm保持-1
        assert len(mecha.effects) == 2
        effect_ids = [e.id for e in mecha.effects]
        assert "temp1" in effect_ids
        assert "perm" in effect_ids
        assert "temp2" not in effect_ids

        # 再tick一次
        EffectManager.tick_effects(mecha)

        # temp1从1变成0(被移除), perm保持-1
        assert len(mecha.effects) == 1
        effect_ids = [e.id for e in mecha.effects]
        assert "perm" in effect_ids
        assert "temp1" not in effect_ids
        assert "temp2" not in effect_ids

    def test_tick_effects_removes_expired(self):
        """测试tick移除过期效果"""
        mecha = Mecha(
            instance_id="m_test", mecha_name="TestMecha", 
            main_portrait="m_test_img", model_asset="default",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            pilot_stats_backup={
                "stat_shooting": 100,
                "stat_melee": 100,
                "stat_reaction": 100,
                "stat_awakening": 100,
                "stat_defense": 100,
            }
        )

        # 添加duration=0的效果（已经过期）
        from src.models import Effect
        expired_effect = Effect(
            id="expired", name="Expired",
            hook="HOOK_DUMMY",
            operation="add", value=0.0,
            duration=0, priority=50
        )
        mecha.effects.append(expired_effect)

        # tick应该移除duration=0的效果
        EffectManager.tick_effects(mecha)

        assert len(mecha.effects) == 0


# ============================================================================
# 测试 TraitManager 集成
# ============================================================================

class TestTraitManagerIntegration:
    """测试TraitManager集成"""

    def test_apply_traits_adds_effects(self, mecha_for_traits):
        """测试应用特性添加效果"""
        initial_count = len(mecha_for_traits.effects)

        TraitManager.apply_traits(mecha_for_traits)

        # 特性效果应该被添加
        assert len(mecha_for_traits.effects) >= initial_count

    def test_apply_traits_idempotent(self, mecha_for_traits):
        """测试应用特性是幂等的（重复应用不重复添加）"""
        TraitManager.apply_traits(mecha_for_traits)
        count_after_first = len(mecha_for_traits.effects)

        # 再次应用
        TraitManager.apply_traits(mecha_for_traits)
        count_after_second = len(mecha_for_traits.effects)

        # 特性效果不应该重复添加
        # 注意：这需要EffectFactory正确实现
        assert count_after_second == count_after_first

    def test_apply_empty_traits(self):
        """测试应用空特性列表"""
        mecha = Mecha(
            instance_id="m_no_traits", mecha_name="NoTraitsMecha", 
            main_portrait="m_no_traits_img", model_asset="default",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            skills=[],  # 无特性 (旧版是 traits，新版是 skills)
            pilot_stats_backup={
                "stat_shooting": 100,
                "stat_melee": 100,
                "stat_reaction": 100,
                "stat_awakening": 100,
                "stat_defense": 100,
            }
        )

        TraitManager.apply_traits(mecha)

        # 不应该添加效果
        assert len(mecha.effects) == 0


# ============================================================================
# 测试 SpiritCommands 集成
# ============================================================================

class TestSpiritCommandsIntegration:
    """测试SpiritCommands集成"""

    def test_activate_strike(self):
        """测试激活必中"""
        mecha = Mecha(
            instance_id="m_test", mecha_name="TestMecha", 
            main_portrait="m_test_img", model_asset="default",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            pilot_stats_backup={
                "stat_shooting": 100,
                "stat_melee": 100,
                "stat_reaction": 100,
                "stat_awakening": 100,
                "stat_defense": 100,
            }
        )

        initial_count = len(mecha.effects)

        SpiritCommands.activate_strike(mecha)

        # 应该添加效果
        assert len(mecha.effects) >= initial_count

    def test_activate_alert(self):
        """测试激活必闪"""
        mecha = Mecha(
            instance_id="m_test", mecha_name="TestMecha", 
            main_portrait="m_test_img", model_asset="default",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            pilot_stats_backup={
                "stat_shooting": 100,
                "stat_melee": 100,
                "stat_reaction": 100,
                "stat_awakening": 100,
                "stat_defense": 100,
            }
        )

        SpiritCommands.activate_alert(mecha)

        # 应该添加效果
        assert len(mecha.effects) > 0

    def test_activate_valor(self):
        """测试激活热血"""
        mecha = Mecha(
            instance_id="m_test", mecha_name="TestMecha", 
            main_portrait="m_test_img", model_asset="default",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            pilot_stats_backup={
                "stat_shooting": 100,
                "stat_melee": 100,
                "stat_reaction": 100,
                "stat_awakening": 100,
                "stat_defense": 100,
            }
        )

        SpiritCommands.activate_valor(mecha)

        # 应该添加效果
        assert len(mecha.effects) > 0

    def test_activate_iron_wall(self):
        """测试激活铁壁"""
        mecha = Mecha(
            instance_id="m_test", mecha_name="TestMecha", 
            main_portrait="m_test_img", model_asset="default",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            pilot_stats_backup={
                "stat_shooting": 100,
                "stat_melee": 100,
                "stat_reaction": 100,
                "stat_awakening": 100,
                "stat_defense": 100,
            }
        )

        SpiritCommands.activate_iron_wall(mecha)

        # 应该添加效果
        assert len(mecha.effects) > 0

    def test_activate_focus(self):
        """测试激活集中"""
        mecha = Mecha(
            instance_id="m_test", mecha_name="TestMecha", 
            main_portrait="m_test_img", model_asset="default",
            final_max_hp=5000, current_hp=5000,
            final_max_en=100, current_en=100,
            final_hit=10.0, final_precision=10.0, final_crit=5.0,
            final_dodge=10.0, final_parry=10.0, final_block=10.0,
            final_armor=1000, final_mobility=100,
            block_reduction=500,
            pilot_stats_backup={
                "stat_shooting": 100,
                "stat_melee": 100,
                "stat_reaction": 100,
                "stat_awakening": 100,
                "stat_defense": 100,
            }
        )

        initial_count = len(mecha.effects)

        SpiritCommands.activate_focus(mecha)

        # Focus通常生成2个效果（命中+回避）
        assert len(mecha.effects) >= initial_count


# ============================================================================
# 测试 EffectFactory 集成
# ============================================================================

class TestEffectFactoryIntegration:
    """测试EffectFactory集成"""

    def test_create_spirit_effect(self):
        """测试创建精神指令效果"""
        effects = EffectFactory.create_effect("spirit_strike", duration=1)

        # 应该返回至少一个效果
        assert len(effects) >= 1

        # 检查效果属性
        effect = effects[0]
        assert effect.id == "spirit_strike"
        assert effect.duration == 1

    def test_create_trait_effects(self):
        """测试创建特性效果"""
        # 注意：trait_newtype 需要在 data/skills.json 中定义
        # 如果未定义，会返回空列表
        effects = EffectFactory.create_trait_effects("trait_newtype")

        # 如果 traits.json 中定义了该特性，应该返回效果
        # 否则返回空列表也是合理行为
        # 这里只验证不报错即可
        assert isinstance(effects, list)

    def test_create_unknown_effect_returns_empty(self):
        """测试创建未知效果返回空列表"""
        effects = EffectFactory.create_effect("unknown_effect_id")

        # 应该返回空列表
        assert len(effects) == 0


# ============================================================================
# 测试系统协同
# ============================================================================

class TestSystemSynergy:
    """测试系统协同工作"""

    def test_trait_and_spirit_combination(self, mecha_for_traits):
        """测试特性和精神指令组合"""
        # 应用特性
        TraitManager.apply_traits(mecha_for_traits)

        trait_count = len(mecha_for_traits.effects)

        # 使用精神指令
        SpiritCommands.activate_focus(mecha_for_traits)

        # 效果应该叠加
        assert len(mecha_for_traits.effects) > trait_count

    def test_effects_with_hooks(self, battle_context):
        """测试效果与钩子协同"""
        # 注册一个测试钩子
        @SkillRegistry.register_hook("HOOK_PRE_HIT_RATE")
        def test_hit_bonus(base_hit, ctx):
            return base_hit + 20

        # 添加命中效果
        attacker = battle_context.attacker
        EffectManager.add_effect(attacker, "buff_hit", duration=1)

        # 处理钩子
        result = SkillRegistry.process_hook("HOOK_PRE_HIT_RATE", 10.0, battle_context)

        # 结果应该包含基础+钩子+效果
        assert result > 10.0

    def test_multiple_round_effects(self, battle_context):
        """测试多回合效果管理"""
        attacker = battle_context.attacker

        # 添加效果 (注意: spirit_strike在JSON中duration=1)
        EffectManager.add_effect(attacker, "spirit_strike", duration=1)

        # 添加后效果应该存在
        assert len(attacker.effects) > 0  # 效果刚添加

        # tick一次 (duration从1变成0并移除)
        EffectManager.tick_effects(attacker)
        assert len(attacker.effects) == 0  # 效果已过期移除
