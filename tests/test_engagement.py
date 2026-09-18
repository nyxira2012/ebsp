"""
战斗编排层不变量单测（Doc 15 §8）。

覆盖：裁定封闭、快照值冻结、三产物同源、事件字段全量、
裁定推导（ko/decision/draw）、meta/init/result 结构对齐 Doc 14、
战报体积预算。

确定性策略（结构断言不依赖具体随机结果）：
- ko 场景拦截 random.uniform 把圆桌掷点恒压到 HIT 段；
- decision/draw 场景用超高装甲靶船（任何判定下伤害恒 0），终局与掷点无关；
- 推导函数的分支覆盖直接构造快照终态单测 _derive_ruling。
"""

import random

import pytest

from src.combat.engagement import (
    BattleReport,
    Engagement,
    EngagementContext,
    EngagementSpec,
    _derive_ruling,
)
from src.config import Config
from src.models import MechaSnapshot, WeaponSnapshot, WeaponType
from src.presentation.contracts import TimelineDocument

DEBUG_CONTEXT = EngagementContext(source="debug")


def _resolve(mecha_a, mecha_b, context=DEBUG_CONTEXT):
    """便捷装配：快照 → 委托 → 裁定 → 战报。"""
    spec = EngagementSpec(mecha_a=mecha_a, mecha_b=mecha_b, context=context)
    return Engagement(spec).resolve()


def _fortress(instance_id: str, name: str, max_hp: int, current_hp: int) -> MechaSnapshot:
    """超高装甲靶船：装甲 1e9 使任何判定的伤害恒为 0，制造确定的满回合长局。"""
    return MechaSnapshot(
        instance_id=instance_id,
        mecha_name=name,
        final_max_hp=max_hp,
        current_hp=current_hp,
        final_max_en=100,
        current_en=100,
        final_armor=10**9,
        final_mobility=100,
        final_hit=10.0,
        pilot_stats_backup={},
        weapons=[
            WeaponSnapshot(
                uid=f"{instance_id}_gun",
                definition_id=f"{instance_id}_gun",
                name="要塞炮",
                type=WeaponType.SHOOTING,
                final_power=1000,
                en_cost=10,
                range_min=0,
                range_max=10000,
                will_req=0,
                anim_id="a_fortress",
            )
        ],
    )


def _all_attack_events(report: BattleReport):
    """展平战报中所有攻防序列内的事件。"""
    return [
        event
        for block in report.timeline.rounds
        for seq in block.attack_sequences
        for event in seq.events
    ]


# ============================================================================
# 裁定封闭（Doc 15 §3）
# ============================================================================

class TestEngagementClosed:
    def test_second_resolve_raises(self, gundam_rx78, zaku_ii):
        spec = EngagementSpec(mecha_a=gundam_rx78, mecha_b=zaku_ii, context=DEBUG_CONTEXT)
        engagement = Engagement(spec)
        first = engagement.resolve()
        with pytest.raises(RuntimeError):
            engagement.resolve()
        assert isinstance(first, BattleReport)


# ============================================================================
# 快照值冻结（Doc 15 §3）
# ============================================================================

class TestSnapshotValueFrozen:
    def test_caller_mutation_after_spec_does_not_leak(self, gundam_rx78, zaku_ii):
        spec = EngagementSpec(mecha_a=gundam_rx78, mecha_b=zaku_ii, context=DEBUG_CONTEXT)
        # 委托建立后改原快照（格纳库后续改动）
        gundam_rx78.current_hp = 1
        zaku_ii.current_en = 0
        report = Engagement(spec).resolve()
        # init 块取的是委托时点的冻结值
        assert report.timeline.init.a.hp == 5500
        assert report.timeline.init.b.en == 100
        # resolve 后：调用方原快照与 spec 副本均未被引擎污染
        assert gundam_rx78.current_hp == 1
        assert spec.mecha_a.current_hp == 5500
        assert spec.mecha_b.current_en == 100


# ============================================================================
# 三产物同源（Doc 15 §3）
# ============================================================================

class TestThreeArtifactsSameRuling:
    def test_result_identity_and_final_states_consistency(self, gundam_rx78, zaku_ii):
        report = _resolve(gundam_rx78, zaku_ii)
        assert report.timeline.result is report.ruling
        assert set(report.final_states) == {"a", "b"}
        for side, summary in (("a", report.ruling.summary.a), ("b", report.ruling.summary.b)):
            state = report.final_states[side]
            assert state["hp"] == summary.hp
            assert state["en"] == summary.en
            assert state["will"] == summary.will
            assert state["alive"] == summary.alive


# ============================================================================
# 事件字段全量（Doc 14 §6）
# ============================================================================

class TestEventContractFields:
    def test_action_reaction_events_carry_full_ruling_layers(self, gundam_rx78, zaku_ii):
        report = _resolve(gundam_rx78, zaku_ii)
        events = _all_attack_events(report)
        assert events, "正常对局应产出演出事件"
        for event in events:
            assert event.type in ("ACTION", "REACTION")
            # 演出层（Doc 14 §6.1）
            assert event.text
            assert event.timestamp >= 0.0
            assert event.tier
            assert event.anim_id
            assert event.camera
            assert isinstance(event.vfx, list)
            assert isinstance(event.sfx, list)
            # 裁定层（Doc 14 §6.2）
            assert event.attack_result in {"HIT", "CRIT", "BLOCK", "PARRY", "DODGE", "MISS"}
            assert event.attacker in {"a", "b"}
            assert event.defender in {"a", "b"}
            assert event.attacker != event.defender
            assert event.weapon_name
            assert event.motion_style
            assert event.damage_material
            assert event.hit_location
            assert isinstance(event.damage, int) and event.damage >= 0
            assert isinstance(event.en_cost, int) and event.en_cost >= 0
            assert event.will_delta is not None
            # 快照层（Doc 14 §6.3）
            assert event.state_after is not None
            for state in (event.state_after.a, event.state_after.b):
                assert state.hp >= 0
                assert state.en >= 0
                assert Config.WILL_MIN <= state.will <= Config.WILL_MAX
            # 高光与触发层（Doc 14 §6.4）
            assert isinstance(event.is_lethal, bool)
            assert event.triggered_skills is not None
            assert event.spirit_commands is not None

    def test_sequence_pair_shares_single_ruling(self, gundam_rx78, zaku_ii):
        """同一序列的 ACTION/REACTION 出自同一次裁定（Doc 14 §1 同源逐字）。"""
        report = _resolve(gundam_rx78, zaku_ii)
        for block in report.timeline.rounds:
            for seq in block.attack_sequences:
                assert len({event.attack_result for event in seq.events}) == 1
                assert len({event.attacker for event in seq.events}) == 1


# ============================================================================
# 裁定推导（Doc 14 §7.1：finish + winner 正交）
# ============================================================================

class TestRulingDerivation:
    def test_derive_ruling_branches(self, gundam_rx78, zaku_ii):
        dead = zaku_ii.model_copy(deep=True)
        dead.current_hp = 0
        # ko：一方死一方活
        ruling = _derive_ruling(gundam_rx78, dead, rounds_fought=3)
        assert (ruling.finish, ruling.winner) == ("ko", "a")
        assert ruling.summary.a.alive is True
        assert ruling.summary.b.alive is False
        assert ruling.summary.b.hp_pct == 0.0
        assert ruling.rounds_fought == 3

        # decision：双活 HP 百分比不等，高者胜
        wounded = gundam_rx78.model_copy(deep=True)
        wounded.current_hp = 2750  # 50% vs 扎古 100%
        ruling = _derive_ruling(wounded, zaku_ii, rounds_fought=100)
        assert (ruling.finish, ruling.winner) == ("decision", "b")
        assert ruling.summary.a.alive is True
        assert ruling.summary.b.alive is True
        assert ruling.summary.a.hp_pct == pytest.approx(50.0)

        # draw：百分比相等（绝对值不同）
        scaled = gundam_rx78.model_copy(deep=True)
        scaled.final_max_hp = 11000
        scaled.current_hp = 5500  # 50%
        ruling = _derive_ruling(scaled, wounded, rounds_fought=100)
        assert (ruling.finish, ruling.winner) == ("draw", None)

    def test_ko_battle(self, gundam_rx78, zaku_ii, monkeypatch):
        # 圆桌掷点恒压到最高段 → 每次攻击必命中，残血 1 的扎古必被击破
        monkeypatch.setattr(random, "uniform", lambda low, high: 99.9)
        zaku_ii.current_hp = 1
        report = _resolve(gundam_rx78, zaku_ii)
        assert report.ruling.finish == "ko"
        assert report.ruling.winner == "a"
        assert report.final_states["b"]["alive"] is False
        assert report.final_states["a"]["alive"] is True
        # 致死事件存在，且其快照层标出受击方 HP 清零（侧位映射正确性）
        lethal = [event for event in _all_attack_events(report) if event.is_lethal]
        assert lethal
        for event in lethal:
            defender_state = getattr(event.state_after, event.defender)
            assert defender_state.hp == 0

    def test_decision_and_draw_battles(self):
        # 超高装甲 → 伤害恒 0 → 打满回合上限进入判定
        stronger = _fortress("f_a", "FortressA", max_hp=1000, current_hp=1000)
        weaker = _fortress("f_b", "FortressB", max_hp=1000, current_hp=500)
        report = _resolve(stronger, weaker)
        assert report.ruling.finish == "decision"
        assert report.ruling.winner == "a"
        assert report.ruling.rounds_fought == Config.MAX_ROUNDS
        assert report.final_states["a"]["hp"] == 1000
        assert report.final_states["b"]["hp"] == 500
        assert report.final_states["a"]["alive"] is True

        twin_a = _fortress("f_x", "Twin", max_hp=800, current_hp=800)
        twin_b = _fortress("f_y", "Twin", max_hp=800, current_hp=800)
        draw_report = _resolve(twin_a, twin_b)
        assert draw_report.ruling.finish == "draw"
        assert draw_report.ruling.winner is None
        assert draw_report.ruling.rounds_fought == Config.MAX_ROUNDS


# ============================================================================
# 文档结构对齐 Doc 14 §3/§4/§7
# ============================================================================

class TestDocumentStructure:
    def test_top_level_meta_init_result(self, gundam_rx78, zaku_ii):
        report = _resolve(gundam_rx78, zaku_ii)
        doc = report.timeline
        assert isinstance(doc, TimelineDocument)
        assert set(doc.model_dump().keys()) == {"meta", "init", "rounds", "result"}
        # meta（Doc 14 §3）
        assert doc.meta.contract_version == "1.0"
        assert doc.meta.cps_version == "5.1"
        assert doc.meta.route == "debug"
        # init（Doc 14 §4）
        profile_a = doc.init.a
        assert profile_a.mecha_id == "m_rx78"
        assert profile_a.name == "RX-78高达"
        assert profile_a.portrait == "m_gundam"
        assert profile_a.hp == 5500 and profile_a.max_hp == 5500
        assert profile_a.en == 120 and profile_a.max_en == 120
        assert profile_a.will == 100
        assert profile_a.will_min == Config.WILL_MIN == 50
        assert profile_a.will_max == Config.WILL_MAX == 150
        assert profile_a.pilot.name is None and profile_a.pilot.portrait is None
        assert doc.init.b.mecha_id == "m_zaku"
        assert doc.init.b.pilot.name is None
        # result（Doc 14 §7.1）
        result = doc.result
        assert result.finish in ("ko", "decision", "draw")
        if result.finish == "draw":
            assert result.winner is None
        else:
            assert result.winner in ("a", "b")
        assert result.rounds_fought >= 1
        assert 0.0 <= result.summary.a.hp_pct <= 100.0
        assert result.summary.a.max_hp == 5500
        assert result.summary.b.max_hp == 4500

    def test_round_fields_are_neutral_defaults_this_phase(self, gundam_rx78, zaku_ii):
        """distance/first/first_reason/is_first_attack 为 P1 字段，本批中性默认。"""
        report = _resolve(gundam_rx78, zaku_ii)
        assert report.timeline.rounds, "正常对局应产出回合块"
        for block in report.timeline.rounds:
            assert block.distance == 0
            assert block.first is None
            assert block.first_reason is None
            assert block.context_events == []
            assert block.summary_events == []
            assert block.attack_sequences
            for seq in block.attack_sequences:
                assert seq.is_first_attack is True

    def test_route_reflects_context_source(self, gundam_rx78, zaku_ii):
        report = _resolve(gundam_rx78, zaku_ii, context=EngagementContext(source="pve"))
        assert report.timeline.meta.route == "pve"


# ============================================================================
# 镜像战：方位按侧位推导，不依赖 ID 唯一性（Doc 14 §5.1）
# ============================================================================

class TestMirrorBattle:
    def test_sides_derived_by_position(self, gundam_rx78):
        twin = gundam_rx78.model_copy(deep=True)
        report = _resolve(gundam_rx78, twin)
        doc = report.timeline
        assert doc.init.a.mecha_id == doc.init.b.mecha_id  # 同配置镜像，ID 无差异
        for block in doc.rounds:
            seq_attacker_sides = []
            for seq in block.attack_sequences:
                sides = {event.attacker for event in seq.events}
                assert len(sides) == 1
                seq_attacker_sides.append(sides.pop())
            assert set(seq_attacker_sides) <= {"a", "b"}
            if len(seq_attacker_sides) >= 2:
                assert seq_attacker_sides[0] != seq_attacker_sides[1]  # 先攻段/反击段互补


# ============================================================================
# 战报体积预算（Doc 15 §3：单场数百 KB 量级）
# ============================================================================

class TestSizeBudget:
    def test_timeline_json_under_512kb(self, gundam_rx78, zaku_ii):
        short_doc = _resolve(gundam_rx78, zaku_ii).timeline
        assert len(short_doc.model_dump_json()) < 512 * 1024
        # 100 回合满编长局是体积上界场景
        long_doc = _resolve(
            _fortress("f_big_a", "FortressBigA", max_hp=1000, current_hp=1000),
            _fortress("f_big_b", "FortressBigB", max_hp=1000, current_hp=999),
        ).timeline
        assert len(long_doc.model_dump_json()) < 512 * 1024
