"""训练力场环境效果单测（Doc 16 v1.2 批次 1）

覆盖两条环境授予效果的语义与装配通道：
- cb_no_death_clamp 免死钳制（致死钳 HP-1 / 非致死穿透 / 攻方持有效果不误钳 /
  HP=1 钳 0 / 镜像同配快照按 is 身份判定）；
- cb_regen_hp_full 回合回满；
- env_* 效果定义（data/skills.json 契约：钩子/回调/priority=100）；
- _apply_environment 装配期注入（幂等 / side=all / EngagementSpec 冻结隔离）；
- loader 环境容器与未知环境引用剔除。

注册表事实（conftest autouse 每测试后清空 SkillRegistry._callbacks，且只清
conftest 持有的旧类引用）：回调用 import 函数本体温测（不受清空影响）；
EffectProcessor 全链路用 importlib.reload(src.skills) 重注册——processor 在
调用期经模块属性懒加载拿到新类。重注册夹具在测试结束把模块属性还原回旧类，
避免新类注册态泄漏到后续测试。
"""

import importlib

import pytest

from src.models import (
    BattleContext, Effect, EnvironmentConfig, EnvironmentEffectGrant,
    MechaSnapshot, Terrain, WeaponSnapshot, WeaponType,
)
from src.skill_system.effect_factory import EffectFactory
from src.skill_system.processor import EffectProcessor
from src.combat.entry import _apply_environment

HP = 5000


def _make_mecha(instance_id: str, hp: int = HP, max_hp: int = HP) -> MechaSnapshot:
    """同配快照工厂（仅 HP 可调）；自带一把武器供武器归属推导"""
    mecha = MechaSnapshot(
        instance_id=instance_id, mecha_name=f"Name_{instance_id}",
        final_max_hp=max_hp, current_hp=hp,
        final_max_en=100, current_en=100,
        final_armor=1000, final_mobility=100,
        pilot_stats_backup={"stat_defense": 0},
    )
    mecha.weapons = [_make_weapon(f"{instance_id}_w1")]
    return mecha


def _make_weapon(uid: str) -> WeaponSnapshot:
    return WeaponSnapshot(
        uid=uid, definition_id="w_test", name="TestGun",
        type=WeaponType.SHOOTING,
        final_power=1000, en_cost=10, range_min=0, range_max=6000,
        will_req=0, anim_id="a_test",
    )


def _attack_context(attacker: MechaSnapshot, defender: MechaSnapshot) -> BattleContext:
    """攻击期上下文：武器归属攻方 → get_defender 按 ctx.weapon 推导出防守方"""
    return BattleContext(
        round_number=1, distance=1000, terrain=Terrain.SPACE,
        mecha_a=attacker, mecha_b=defender, weapon=attacker.weapons[0],
    )


def _env(side: str = "a", effect_ids: list[str] | None = None) -> EnvironmentConfig:
    return EnvironmentConfig(
        id="env_test", name="测试力场", kind="defense_test",
        grants=[EnvironmentEffectGrant(
            side=side,
            effect_ids=effect_ids if effect_ids is not None else ["env_regen_full", "env_no_death"],
        )],
    )


# ============================================================================
# 回调函数本体温测（不受 conftest 注册表清空影响）
# ============================================================================

from src.skills import cb_no_death_clamp, cb_regen_hp_full


class TestNoDeathClamp:
    """免死钳制语义（Doc 16 §5.3：致死伤保留、测试不中断）"""

    def test_lethal_damage_clamped_to_hp_minus_one(self):
        owner = _make_mecha("m_def", hp=1000)
        ctx = _attack_context(_make_mecha("m_atk"), owner)

        damage = cb_no_death_clamp(1500, ctx, owner)

        assert damage == 999
        assert owner.current_hp == 1000  # 钳制只改落血值，不自行扣血

    def test_nonlethal_damage_passes_through(self):
        owner = _make_mecha("m_def", hp=1000)
        ctx = _attack_context(_make_mecha("m_atk"), owner)

        assert cb_no_death_clamp(500, ctx, owner) == 500

    def test_clamps_to_zero_when_hp_is_one(self):
        owner = _make_mecha("m_def", hp=1)
        ctx = _attack_context(_make_mecha("m_atk"), owner)

        assert cb_no_death_clamp(50, ctx, owner) == 0

    def test_no_clamp_when_effect_held_by_attacker(self):
        """效果处理器对双方效果都跑：持有效果的一方在攻击，钳不得防守方挨的刀"""
        attacker = _make_mecha("m_atk", hp=1000)
        defender = _make_mecha("m_def", hp=1000)
        ctx = _attack_context(attacker, defender)

        assert cb_no_death_clamp(1500, ctx, attacker) == 1500

    def test_identity_not_value_equality_for_twin_snapshots(self):
        """身份判定必须用 is：镜像同配快照 == 为真，误用会把攻方当成防守方"""
        a = _make_mecha("m_twin", hp=1000)
        b = _make_mecha("m_twin", hp=1000)
        assert a == b and a is not b
        ctx = _attack_context(a, b)  # 防守方是 b

        assert cb_no_death_clamp(1500, ctx, a) == 1500  # owner=攻方 a，不得误钳


class TestRegenFull:
    def test_restores_hp_to_max(self):
        owner = _make_mecha("m_low", hp=1234)
        ctx = BattleContext(round_number=1, distance=1000, mecha_a=owner,
                            mecha_b=_make_mecha("m_foe"))

        val = cb_regen_hp_full(None, ctx, owner)

        assert owner.current_hp == owner.final_max_hp == HP
        assert val is None  # 返回原值，不污染钩子链


# ============================================================================
# 效果定义（data/skills.json 契约）
# ============================================================================

def test_env_effect_definitions_from_json():
    no_death = EffectFactory.create_trait_effects("env_no_death")
    assert len(no_death) == 1
    assert no_death[0].hook == "HOOK_ON_DAMAGE_TAKEN"
    assert no_death[0].value == "cb_no_death_clamp"
    # priority=100：同钩子按 priority 升序执行，钳制最后执行拿最终落血决定权
    assert no_death[0].priority == 100
    assert no_death[0].duration == -1

    regen = EffectFactory.create_trait_effects("env_regen_full")
    assert len(regen) == 1
    assert regen[0].hook == "HOOK_ON_TURN_END"
    assert regen[0].value == "cb_regen_hp_full"
    assert regen[0].duration == -1


# ============================================================================
# EffectProcessor 全链路（reload 重注册回调；夹具结束清空新类注册表）
# ============================================================================

@pytest.fixture
def reloaded_skills():
    import src.skills
    original_registry = src.skills.SkillRegistry
    importlib.reload(src.skills)
    yield src.skills
    # 还原模块属性指向旧类：processor 在调用期按模块属性懒加载，既有测试
    # （conftest/引擎/其他用例）持旧类引用并往旧类注册回调——不还原会让
    # 它们的注册与查找落在不同类上。还原后 conftest 照常清空旧类注册表。
    src.skills.SkillRegistry = original_registry


def test_processor_clamps_lethal_damage_full_chain(reloaded_skills):
    owner = _make_mecha("m_def", hp=1000)
    ctx = _attack_context(_make_mecha("m_atk"), owner)
    owner.effects.extend(EffectFactory.create_trait_effects("env_no_death"))

    assert EffectProcessor.process("HOOK_ON_DAMAGE_TAKEN", 1500, ctx) == 999


def test_processor_no_clamp_when_effect_held_by_attacker_full_chain(reloaded_skills):
    attacker = _make_mecha("m_atk", hp=1000)
    defender = _make_mecha("m_def", hp=1000)
    ctx = _attack_context(attacker, defender)
    attacker.effects.extend(EffectFactory.create_trait_effects("env_no_death"))

    assert EffectProcessor.process("HOOK_ON_DAMAGE_TAKEN", 1500, ctx) == 1500


def test_clamp_runs_after_other_damage_modifiers(reloaded_skills):
    """priority=100 的排序语义：钳制吃在其他伤害修正之后（低优先级先跑）"""
    owner = _make_mecha("m_def", hp=1000)
    ctx = _attack_context(_make_mecha("m_atk"), owner)
    boost = Effect(id="test_boost", name="boost", hook="HOOK_ON_DAMAGE_TAKEN",
                   operation="add", value=50, duration=-1, priority=50)
    owner.effects.extend([boost, *EffectFactory.create_trait_effects("env_no_death")])

    # 1500 +50 = 1550 → 钳到 999；顺序颠倒会得到 999 +50 = 1049
    assert EffectProcessor.process("HOOK_ON_DAMAGE_TAKEN", 1500, ctx) == 999


def test_processor_regen_full_on_turn_end(reloaded_skills):
    """回合结束钩子以 (None, ctx) 触发（engine 同址），持有方回满"""
    owner = _make_mecha("m_low", hp=1234)
    ctx = BattleContext(round_number=1, distance=1000, mecha_a=owner,
                        mecha_b=_make_mecha("m_foe"))
    owner.effects.extend(EffectFactory.create_trait_effects("env_regen_full"))

    EffectProcessor.process("HOOK_ON_TURN_END", None, ctx)

    assert owner.current_hp == owner.final_max_hp


# ============================================================================
# 装配期注入（_apply_environment）
# ============================================================================

class TestApplyEnvironment:
    def test_injects_to_declared_side_only(self):
        a, b = _make_mecha("m_a"), _make_mecha("m_b")

        _apply_environment(_env(side="a"), a, b)

        assert len(a.effects) == 2
        assert {e.id for e in a.effects} == {"env_regen_full", "env_no_death"}
        assert b.effects == []

    def test_side_all_injects_both_sides(self):
        a, b = _make_mecha("m_a"), _make_mecha("m_b")

        _apply_environment(_env(side="all"), a, b)

        assert {e.id for e in a.effects} == {"env_regen_full", "env_no_death"}
        assert {e.id for e in b.effects} == {"env_regen_full", "env_no_death"}

    def test_injection_is_idempotent(self):
        a, b = _make_mecha("m_a"), _make_mecha("m_b")
        env = _env(side="a")

        _apply_environment(env, a, b)
        _apply_environment(env, a, b)

        assert len(a.effects) == 2


class TestSpecFreezeIsolation:
    """快照注入 → EngagementSpec 构造即深拷贝：效果只活在委托副本里（Doc 16 §5.3）"""

    def test_spec_freeze_isolates_original_snapshot(self):
        from src.combat.engagement import EngagementContext, EngagementSpec

        a, b = _make_mecha("m_a"), _make_mecha("m_b")
        _apply_environment(_env(side="a"), a, b)

        spec = EngagementSpec(mecha_a=a, mecha_b=b,
                              context=EngagementContext(source="debug"))

        assert len(spec.mecha_a.effects) == 2
        assert spec.mecha_a.effects is not a.effects
        spec.mecha_a.effects.clear()  # 战斗侧 mutate 冻结副本不回传装配原件
        assert len(a.effects) == 2

    def test_assembly_without_environment_has_no_effects(self):
        """未声明环境的装配（调试老路径/第二场）零效果——注入是逐场显式的"""
        from src.combat.engagement import EngagementContext, EngagementSpec

        spec = EngagementSpec(mecha_a=_make_mecha("m_a"), mecha_b=_make_mecha("m_b"),
                              context=EngagementContext(source="debug"))

        assert spec.mecha_a.effects == []
        assert spec.mecha_b.effects == []


# ============================================================================
# loader：环境容器与练习场交叉校验
# ============================================================================

def test_environments_loaded_from_data():
    from src import DataLoader

    loader = DataLoader(data_dir="data")
    loader.load_all()

    training_field = loader.get_environment_config("env_training_field")
    assert training_field.kind == "defense_test"
    assert training_field.grants[0].side == "a"
    assert training_field.grants[0].effect_ids == ["env_regen_full", "env_no_death"]
    # 零效果标签环境
    assert loader.environments["env_target_range"].grants == []
    assert loader.environments["env_field"].kind == "standard"

    with pytest.raises(KeyError, match="环境配置不存在"):
        loader.get_environment_config("no_such_env")


def test_loader_drops_scenario_referencing_unknown_environment():
    from src import DataLoader
    from src.models import PracticeScenarioConfig

    loader = DataLoader(data_dir="data")
    loader.load_all()
    before = set(loader.practice_scenarios)

    loader.practice_scenarios["broken_env"] = PracticeScenarioConfig(
        id="broken_env", name="坏环境条目", description="",
        environment_id="no_such_env",
        mecha_a_id="mech_rx78", mecha_b_id="mech_zaku",
    )
    loader._validate_practice_scenarios()

    assert "broken_env" not in loader.practice_scenarios
    assert set(loader.practice_scenarios) == before
