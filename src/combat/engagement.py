"""
战斗裁判 (Engagement) — Doc 15 §3

把"打一场仗"包装成黑盒：两份冻结快照进 → 引擎与演出只跑一次 →
两件产物（完整战报 TimelineDocument / 裁定 ResultBlock）出自同一次
裁定——裁定 summary 即双方战后残血，PVE 写回同源。装配散落与战果
丢弃的病根都在这里收口。

不变量（Doc 15 §3，评审即打回项）：
- 裁定封闭：开赛后委托不可再变，二次 resolve 抛 RuntimeError；
- 值冻结：EngagementSpec 构造即深拷贝快照，格纳库后续改动不影响已开打的这场仗；
- 两产物同源：timeline.result 与 report.ruling 为同一对象。

随机流（红线 3）：resolve 以 seed_used 建本场随机流并注入引擎与演出，
替换一切影响战报的全局随机——并发会话互不污染，同委托同种子必得同一
战报。seed 缺省随机生成、仅后端侧记录（不入契约，裁决 #2）。
"""

import random
from dataclasses import dataclass
from typing import Any, Optional, get_args

from ..config import Config
from ..models import MechaSnapshot
from ..presentation.contracts import (
    AttackSequenceBlock,
    CombatantState,
    EventContract,
    FirstReason,
    InitBlock,
    ParticipantProfile,
    PilotProfile,
    ResultBlock,
    ResultSummary,
    Route,
    RoundBlock,
    Side,
    SideSummary,
    StateAfter,
    TimelineDocument,
    TimelineMeta,
    WillDelta,
)
from ..presentation.models import PresentationAttackEvent
from .engine import BattleSimulator, derive_verdict


@dataclass(frozen=True)
class EngagementContext:
    """战斗委托上下文（Doc 15 §3 场景标签）。

    source 落到战报 meta.route（debug/training/pve/pvp）；
    environment_id 为规则环境引用（Doc 16 §5.3 环境通道）：编排层只
    透传环境 ID 不解其义，效果在装配期注入参战快照，引擎只见效果
    不见环境。不进战报契约。
    """
    source: Route
    environment_id: Optional[str] = None


@dataclass(frozen=True)
class EngagementSpec:
    """战斗委托：两份冻结的输入快照 + 上下文 + 可选复现种子。

    构造即深拷贝存副本——值冻结不依赖调用方自觉（Doc 15 §3）。
    """
    mecha_a: MechaSnapshot
    mecha_b: MechaSnapshot
    context: EngagementContext
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mecha_a", self.mecha_a.model_copy(deep=True))
        object.__setattr__(self, "mecha_b", self.mecha_b.model_copy(deep=True))


@dataclass
class BattleReport:
    """战报：两件产物出自同一次裁定（Doc 15 §3）。

    - timeline：Doc 14 全结构时间轴（其 result 与 ruling 为同一对象；
      ruling.summary 即双方战后残血，供 PVE 写回——气力是场内资源，随战报走）；
    - seed_used：仅后端侧记录，不入契约（裁决 #2）。
    """
    timeline: TimelineDocument
    ruling: ResultBlock
    seed_used: int


def _build_profile(snapshot: MechaSnapshot) -> ParticipantProfile:
    """从冻结快照装配参战方档案（Doc 14 §4 init 块）。"""
    return ParticipantProfile(
        mecha_id=snapshot.instance_id,
        name=snapshot.mecha_name,
        portrait=snapshot.main_portrait,
        hp=snapshot.current_hp,
        max_hp=snapshot.final_max_hp,
        en=snapshot.current_en,
        max_en=snapshot.final_max_en,
        will=snapshot.current_will,
        will_min=Config.WILL_MIN,
        will_max=Config.WILL_MAX,
        # 快照无机师字段，恒 null（Doc 14 §9.2 待裁决）
        pilot=PilotProfile(),
    )


def _build_event(event: PresentationAttackEvent, attacker_side: Optional[str]) -> EventContract:
    """单个演出事件 → 契约事件（Doc 14 §6）。

    attacker_side 为 None（CONTEXT/SUMMARY，无引擎裁定）时裁定层保持 null。
    ACTION/REACTION 出自同一次引擎裁定（同一 RawAttackEvent），
    attacker/defender 均标记该次攻击的出招/受击方位（Doc 14 §6 示例：
    REACTION 的 attacker 仍是出招方）——镜像战不依赖 ID 唯一性。
    """
    raw = event.raw_event
    fields: dict[str, Any] = {
        "type": event.event_type,
        "text": event.text,
        "timestamp": event.timestamp,
        "tier": event.tier.value,
        "anim_id": event.anim_id,
        "camera": event.camera_cam,
        "vfx": list(event.vfx_ids),
        "sfx": list(event.sfx_ids),
    }
    if raw is not None and attacker_side is not None:
        defender_side = "b" if attacker_side == "a" else "a"
        # 攻/防状态与气力增量先按角色组一次，再按出招方位落 a/b 键
        # （Doc 14 §6.2/§6.3 的方位口径；攻防两分支同构，避免镜像重复装配）
        states = {
            attacker_side: CombatantState(
                hp=raw.attacker_hp_after, en=raw.attacker_en_after, will=raw.attacker_will_after
            ),
            defender_side: CombatantState(
                hp=raw.defender_hp_after, en=raw.defender_en_after, will=raw.defender_will_after
            ),
        }
        deltas = {
            attacker_side: raw.attacker_will_delta,
            defender_side: raw.defender_will_delta,
        }
        will_delta = WillDelta(a=deltas["a"], b=deltas["b"])
        state_after = StateAfter(a=states["a"], b=states["b"])
        fields.update(
            attack_result=raw.attack_result.value,
            attacker=attacker_side,
            defender=defender_side,
            weapon_name=raw.weapon_name,
            motion_style=raw.motion_style.value,
            damage_material=raw.damage_material.value,
            hit_location=event.hit_location,
            damage=raw.damage,
            en_cost=raw.en_cost,
            will_delta=will_delta,
            state_after=state_after,
            is_lethal=raw.is_lethal,
            triggered_skills=list(raw.triggered_skills),
            spirit_commands=list(raw.spirit_commands),
        )
    return EventContract(**fields)


def _derive_ruling(a: MechaSnapshot, b: MechaSnapshot, rounds_fought: int) -> ResultBlock:
    """从战后快照推导终局（Doc 14 §7.1：finish + winner 正交表达）。

    一方死一方活 → ko + 活方；双活比 HP 百分比，高者 → decision；
    相等 → draw（winner 为 None）。不用引擎旧的 a_wins/b_wins 口径——
    那无法区分击破与判定。

    判定本体出自 engine.derive_verdict（全仓库唯一的终局判定实现，
    与引擎终局播报同源），此处只做契约装配；双死→draw 的统一口径
    与不可达声明见该函数 docstring。
    """
    finish, winner = derive_verdict(a, b)
    # winner 收窄：engine 侧 Optional[Literal["a","b"]] 与契约 Side 同构
    contract_winner: Optional[Side] = winner
    return ResultBlock(
        finish=finish,
        winner=contract_winner,
        rounds_fought=rounds_fought,
        summary=ResultSummary(
            a=_build_side_summary(a),
            b=_build_side_summary(b),
        ),
    )


def _build_side_summary(snapshot: MechaSnapshot) -> SideSummary:
    """终局单方小结（Doc 14 §7.1 summary 成员）。"""
    return SideSummary(
        hp=snapshot.current_hp,
        max_hp=snapshot.final_max_hp,
        hp_pct=snapshot.get_hp_percentage(),
        en=snapshot.current_en,
        will=snapshot.current_will,
        alive=snapshot.is_alive(),
    )


class Engagement:
    """裁判本体：快照进 → 跑一次引擎与演出 → 战报出（Doc 15 §2）。

    深模块：外界只面向 EngagementSpec 与 resolve()，
    引擎运行、演出装配、裁定推导全部挡在内部。
    """

    def __init__(self, spec: EngagementSpec) -> None:
        self._spec = spec
        self._report: Optional[BattleReport] = None

    def resolve(self) -> BattleReport:
        """执行裁定并返回战报；引擎与演出只在此运行且只运行一次。

        Returns:
            BattleReport: 完整战报 + 裁定 + 残血 + 种子记录。

        Raises:
            RuntimeError: 二次 resolve（裁定封闭不变量，Doc 15 §3）。
        """
        if self._report is not None:
            raise RuntimeError("裁定封闭：同一委托已裁定，不可二次 resolve（Doc 15 §3）")

        # 种子缺省随机生成、仅后端侧记录（裁决 #2）——先生成再建流，
        # 缺省路径同样落在可复现的本场随机流上
        seed_used = self._spec.seed if self._spec.seed is not None else random.randrange(2**32)
        # 本场随机流（红线 3）：裁判持有，圆桌/技能/演出竞标统一经此取随机
        rng = random.Random(seed_used)

        # 引擎会原地 mutate 快照：再深拷贝一份喂引擎，spec 原值专供 init 块
        sim = BattleSimulator(
            self._spec.mecha_a.model_copy(deep=True),
            self._spec.mecha_b.model_copy(deep=True),
            enable_presentation=True,
            quiet=True,
            rng=rng,
        )
        sim.run_battle()

        ruling = _derive_ruling(sim.mecha_a, sim.mecha_b, sim.round_number)
        timeline = TimelineDocument(
            meta=TimelineMeta(route=self._spec.context.source),
            init=InitBlock(
                a=_build_profile(self._spec.mecha_a),
                b=_build_profile(self._spec.mecha_b),
            ),
            rounds=self._build_rounds(sim),
            result=ruling,  # 与 report.ruling 同一对象：三产物同源不变量
        )
        report = BattleReport(
            timeline=timeline,
            ruling=ruling,
            seed_used=seed_used,
        )
        self._report = report
        return report

    def _build_rounds(self, sim: BattleSimulator) -> list[RoundBlock]:
        """presentation_timeline → 契约回合块。

        回合字段（distance/first/first_reason）与 CONTEXT/SUMMARY 事件
        由引擎生产（P1-a），此处直传。initiative_holder 回填（红线 4：
        悬空字段有主）用回合先手值 round_evt.first_side（引擎权威裁定），
        空则回退"首序列攻方"——first_side 仅在绕过 _execute_round 的守卫
        裸回合（_execute_attack 直调场景）为空，回退即服务该场景。
        """
        round_blocks: list[RoundBlock] = []
        for round_evt in sim.presentation_timeline:
            first_side: Optional[str] = round_evt.first_side or None
            if first_side is None and round_evt.attack_sequences:
                first_side = round_evt.attack_sequences[0].attacker_side or None
            if first_side is not None:
                for seq in round_evt.attack_sequences:
                    for evt in seq.events:
                        if evt.raw_event is not None:
                            evt.raw_event.initiative_holder = first_side

            seq_blocks = [
                AttackSequenceBlock(
                    attacker_id=seq.attacker_id,
                    defender_id=seq.defender_id,
                    # 先攻标记取序列首个事件的引擎裁定；raw_event 缺失保底 true
                    is_first_attack=(
                        seq.events[0].raw_event.is_first_attack
                        if seq.events and seq.events[0].raw_event is not None
                        else True
                    ),
                    events=[_build_event(evt, seq.attacker_side or None) for evt in seq.events],
                )
                for seq in round_evt.attack_sequences
            ]
            round_blocks.append(
                RoundBlock(
                    round_number=round_evt.round_number,
                    distance=round_evt.distance,
                    # 演出层字段是裸 str，契约是字面值类型——此处做运行时收窄，
                    # 引擎外的旧时间轴（空串/未知值）降级为 None 而非带病入契约
                    first=(
                        round_evt.first_side
                        if round_evt.first_side in ("a", "b")
                        else None
                    ),
                    # 五键与 contracts.FirstReason 同源；此处字面值元组换来
                    # pyright 严格收窄，漏改由测试侧 get_args 枚举校验兜底
                    first_reason=(
                        round_evt.first_reason
                        if round_evt.first_reason
                        in ("forced_switch", "performance", "pilot", "advantage", "counter")
                        else None
                    ),
                    context_events=[_build_event(evt, None) for evt in round_evt.context_events],
                    attack_sequences=seq_blocks,
                    summary_events=[_build_event(evt, None) for evt in round_evt.summary_events],
                )
            )
        return round_blocks
