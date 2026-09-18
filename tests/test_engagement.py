"""
战斗编排层不变量单测（Doc 15 §8）。

覆盖：裁定封闭、快照值冻结、三产物同源、事件字段全量、
回合字段与开场/终局播报（P1-a：距离/先手/先手原因/首攻标记/
CONTEXT 与 SUMMARY 事件）、裁定推导（ko/decision/draw）、
meta/init/result 结构对齐 Doc 14、战报体积预算。

确定性策略（结构断言不依赖具体随机结果）：
- ko 场景拦截 random.Random.uniform（类级——裁判持有本场随机流，模块级
  patch 够不到注入流）把圆桌掷点恒压到 HIT 段；
- decision/draw 场景用超高装甲靶船（任何判定下伤害恒 0），终局与掷点无关；
- 推导函数的分支覆盖直接构造快照终态单测 _derive_ruling。
"""

import random
from typing import get_args

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
from src.presentation.contracts import FirstReason, TimelineDocument

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
        # （类级 patch：连裁判注入的本场随机流一并压住，模块级 patch 够不到它）
        monkeypatch.setattr(random.Random, "uniform", lambda self, low, high: 99.9)
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

    def test_ko_battle_b_side_lethal(self, gundam_rx78, zaku_ii, monkeypatch):
        """b 攻致死的镜像面：锁定 b 出招时攻/防属性到 a/b 键的映射。"""
        monkeypatch.setattr(random.Random, "uniform", lambda self, low, high: 99.9)
        gundam_rx78.current_hp = 1
        report = _resolve(gundam_rx78, zaku_ii)
        assert report.ruling.finish == "ko"
        assert report.ruling.winner == "b"
        assert report.final_states["a"]["alive"] is False
        assert report.final_states["b"]["alive"] is True
        lethal = [event for event in _all_attack_events(report) if event.is_lethal]
        assert lethal
        for event in lethal:
            assert event.defender == "a"
            assert event.state_after.a.hp == 0

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

    def test_route_reflects_context_source(self, gundam_rx78, zaku_ii):
        report = _resolve(gundam_rx78, zaku_ii, context=EngagementContext(source="pve"))
        assert report.timeline.meta.route == "pve"


# ============================================================================
# 回合字段与开场/终局播报（Doc 14 §5/§5.1/§6.1，P1-a 引擎生产）
# ============================================================================

# 单一事实源：随 contracts.FirstReason 枚举扩展自动跟进（装配侧手抄元组漏改时由此兜底）
FIRST_REASON_ENUM = set(get_args(FirstReason))


class TestRoundFieldsAndBroadcastEvents:
    def test_round_fields_and_opening_context_every_round(self, gundam_rx78, zaku_ii):
        """每回合：距离>0、先手侧位与五枚举原因、开场播报含距离与先手方名。"""
        report = _resolve(gundam_rx78, zaku_ii)
        assert report.timeline.rounds, "正常对局应产出回合块"
        for block in report.timeline.rounds:
            # 距离边界：收敛窗可至 DISTANCE_FINAL_MIN=0，不保证恒正（Doc 14 §5）
            assert Config.DISTANCE_FINAL_MIN <= block.distance <= Config.DISTANCE_INITIAL_MAX
            assert block.first in ("a", "b")
            assert block.first_reason in FIRST_REASON_ENUM
            assert block.context_events, "回合开场播报由引擎生产（含无攻击的空回合）"
            opening = block.context_events[0]
            assert opening.type == "CONTEXT"
            assert f"{block.distance}m" in opening.text
            assert "先手" in opening.text
            first_name = (
                report.timeline.init.a.name if block.first == "a" else report.timeline.init.b.name
            )
            assert first_name in opening.text

    def test_distance_converges_over_rounds(self):
        """距离随回合收敛（Doc 14 §5 生成规则）：首回合不低于初始下限，
        收敛窗（第 5 回合起上界=最终上限）内不再反弹，末回合必小于首回合。"""
        report = _resolve(
            _fortress("f_conv_a", "ConvA", max_hp=1000, current_hp=1000),
            _fortress("f_conv_b", "ConvB", max_hp=1000, current_hp=999),
        )
        rounds = report.timeline.rounds
        assert len(rounds) == Config.MAX_ROUNDS  # 超高装甲 → 打满回合上限
        assert rounds[0].distance >= Config.DISTANCE_INITIAL_MIN
        for block in rounds[4:]:  # 7000-1500*4 < 2000 → 第 5 回合起窗收敛
            assert block.distance <= Config.DISTANCE_FINAL_MAX
        assert rounds[-1].distance < rounds[0].distance

    def test_first_attack_marker_matches_sequence_order(self):
        """is_first_attack 与序列顺序一致：先手段 true、后手段 false；
        先手方与首序列攻方一致（回合先手裁定的交叉验证）。
        用装甲靶船对局保证确定性（伤害恒 0 → 双方每回合完整互攻，无随机死局）。"""
        report = _resolve(
            _fortress("f_mark_a", "MarkA", max_hp=1000, current_hp=1000),
            _fortress("f_mark_b", "MarkB", max_hp=1000, current_hp=1000),
        )
        saw_pair = False
        for block in report.timeline.rounds:
            if len(block.attack_sequences) >= 2:
                saw_pair = True
                assert block.attack_sequences[0].is_first_attack is True
                assert block.attack_sequences[1].is_first_attack is False
            if block.attack_sequences:
                first_seq_attackers = {event.attacker for event in block.attack_sequences[0].events}
                assert first_seq_attackers == {block.first}
        assert saw_pair, "正常对局应存在先攻+反击的完整回合"

    def test_empty_round_still_presented(self, gundam_rx78, zaku_ii, monkeypatch):
        """空回合仍进 timeline（Doc 14 §5 rounds=回合序列）：出招段被
        HOOK_PRE_EN_COST_MULT 抬价挡下时，回合块有开场播报、无攻防序列。"""
        from src.skills import SkillRegistry

        def pricey_en_hook(hook, value, ctx):
            if hook == "HOOK_PRE_EN_COST_MULT":
                return 10**9  # 抬价到双方都出不起 → 每段攻击早退
            return value

        monkeypatch.setattr(
            SkillRegistry, "process_hook", classmethod(lambda cls, h, v, c: pricey_en_hook(h, v, c))
        )
        report = _resolve(gundam_rx78, zaku_ii)
        assert report.timeline.rounds, "空回合对局仍应有回合块"
        empty = [b for b in report.timeline.rounds if not b.attack_sequences]
        assert empty, "抬价对局应存在无攻防序列的空回合"
        for block in empty:
            assert block.context_events, "空回合也必须播报开场（含距离与先手）"
            assert block.context_events[0].type == "CONTEXT"

    def test_ko_battle_summary_events(self, gundam_rx78, zaku_ii, monkeypatch):
        """击破局：击破播报与终局宣告同在最后一回合 summary_events，先破后宣告。"""
        monkeypatch.setattr(random.Random, "uniform", lambda self, low, high: 99.9)
        zaku_ii.current_hp = 1
        report = _resolve(gundam_rx78, zaku_ii)
        assert report.ruling.finish == "ko"
        texts = [event.text for event in report.timeline.rounds[-1].summary_events]
        assert any("被击破" in text for text in texts)
        assert any("战斗结束" in text and "击破" in text for text in texts)
        assert next(i for i, t in enumerate(texts) if "被击破" in t) < next(
            i for i, t in enumerate(texts) if "战斗结束" in t
        )

    def test_decision_and_draw_announcements_match_finish(self):
        """终局宣告文案与 result.finish 一致：decision 含"判定"与胜者名，draw 含"平局"。"""
        stronger = _fortress("f_da", "FortressDA", max_hp=1000, current_hp=1000)
        weaker = _fortress("f_db", "FortressDB", max_hp=1000, current_hp=500)
        report = _resolve(stronger, weaker)
        assert report.ruling.finish == "decision"
        announce = report.timeline.rounds[-1].summary_events[-1]
        assert announce.type == "SUMMARY"
        assert "判定" in announce.text
        assert "FortressDA" in announce.text

        twin_a = _fortress("f_dx", "Twin", max_hp=800, current_hp=800)
        twin_b = _fortress("f_dy", "Twin", max_hp=800, current_hp=800)
        draw_report = _resolve(twin_a, twin_b)
        assert draw_report.ruling.finish == "draw"
        assert "平局" in draw_report.timeline.rounds[-1].summary_events[-1].text

    def test_context_summary_events_have_no_ruling_layers(self, gundam_rx78, zaku_ii):
        """CONTEXT/SUMMARY 无引擎裁定：裁定层/快照层/高光层字段恒 null（Doc 14 §6）。"""
        report = _resolve(gundam_rx78, zaku_ii)
        broadcast_events = [
            event
            for block in report.timeline.rounds
            for event in list(block.context_events) + list(block.summary_events)
        ]
        assert broadcast_events, "引擎应生产开场/终局播报事件"
        for event in broadcast_events:
            assert event.type in ("CONTEXT", "SUMMARY")
            assert event.attack_result is None
            assert event.attacker is None
            assert event.defender is None
            assert event.weapon_name is None
            assert event.damage is None
            assert event.en_cost is None
            assert event.will_delta is None
            assert event.state_after is None
            assert event.is_lethal is None
            assert event.triggered_skills is None
            assert event.spirit_commands is None


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
