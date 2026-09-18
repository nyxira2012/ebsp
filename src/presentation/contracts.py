"""
战斗时间轴契约模型 (Battle Timeline Contract) — Doc 14 §3-§7

对外契约的唯一实现点：前端消费的时间轴 JSON 只经由本模块的
``TimelineDocument`` 装配（装配逻辑在 ``src/combat/engagement.py``），
结构上不可能漏字段（架构红线 1：战报格式唯一拼装点）。
现状：simulate 已切换为 response_model=TimelineDocument，
API 响应链路上无第二拼装点；PVE 接敌随 B5 并入。

同步规则（三处同步，Doc 15 §8）：改字段必须先改 Doc 14 → 再改本模块 → 重录金样张
（tests/test_battle_golden.py，重录方法见其 docstring）。
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# Doc 14 §1 侧位命名：a=请求方视角己方（画面左侧），b=敌方（画面右侧）
Side = Literal["a", "b"]
# Doc 14 §3 meta.route：战报入口标记（debug/training/pve/pvp，v1.3 增补）
Route = Literal["debug", "training", "pve", "pvp"]
# Doc 14 §5 first_reason 枚举（与引擎 InitiativeReason 对应，对外输出英文键）
FirstReason = Literal["forced_switch", "performance", "pilot", "advantage", "counter"]


class TimelineMeta(BaseModel):
    """时间轴元信息（Doc 14 §3 meta 块）：契约与演出系统版本号 + 战报入口标记。"""
    contract_version: str = "1.0"
    cps_version: str = "5.1"
    route: Route = "debug"


class PilotProfile(BaseModel):
    """机师档案（Doc 14 §4 pilot）。

    快照无机师姓名/头像字段，恒为 null（Doc 14 §9.2 待裁决，本层不做发明）。
    """
    name: Optional[str] = None
    portrait: Optional[str] = None


class ParticipantProfile(BaseModel):
    """参战方档案与数值初值（Doc 14 §4 init 块），供前端作战板初始化。"""
    mecha_id: str
    name: str
    portrait: str
    hp: int
    max_hp: int
    en: int
    max_en: int
    will: int
    will_min: int
    will_max: int
    pilot: PilotProfile = Field(default_factory=PilotProfile)


class InitBlock(BaseModel):
    """双方档案（Doc 14 §3 init 块）。"""
    a: ParticipantProfile
    b: ParticipantProfile


class WillDelta(BaseModel):
    """双方气力变动量（Doc 14 §6.2 will_delta）。"""
    a: int
    b: int


class CombatantState(BaseModel):
    """事件落地后单方状态（Doc 14 §6.3 state_after 成员）。"""
    hp: int
    en: int
    will: int


class StateAfter(BaseModel):
    """事件落地后双方状态快照（Doc 14 §6.3）——作战板计量条的唯一数据源。"""
    a: CombatantState
    b: CombatantState


class EventContract(BaseModel):
    """演出事件（Doc 14 §6）——时间轴的核心数据单元。

    字段分四层：演出层必填；裁定层/快照层/高光层仅在 ACTION/REACTION
    （有引擎裁定）时填充，CONTEXT/SUMMARY 事件显式 null 下发。
    """
    # ── 演出层：前端播放控制（Doc 14 §6.1）──
    type: Literal["ACTION", "REACTION", "CONTEXT", "SUMMARY"]
    text: str
    timestamp: float
    tier: str
    anim_id: str
    camera: str
    vfx: List[str]
    sfx: List[str]

    # ── 裁定层：演出分发依据，取自 RawAttackEvent（Doc 14 §6.2）──
    attack_result: Optional[Literal["HIT", "CRIT", "BLOCK", "PARRY", "DODGE", "MISS"]] = None
    attacker: Optional[Side] = None
    defender: Optional[Side] = None
    weapon_name: Optional[str] = None
    motion_style: Optional[str] = None
    damage_material: Optional[str] = None
    hit_location: Optional[str] = None
    damage: Optional[int] = None
    en_cost: Optional[int] = None
    will_delta: Optional[WillDelta] = None

    # ── 快照层：作战板计量条数据源（Doc 14 §6.3）──
    state_after: Optional[StateAfter] = None

    # ── 高光与触发层：Cut-In 与终局链触发依据（Doc 14 §6.4）──
    is_lethal: Optional[bool] = None
    triggered_skills: Optional[List[str]] = None
    spirit_commands: Optional[List[str]] = None


class AttackSequenceBlock(BaseModel):
    """攻防序列（Doc 14 §5.1）——通常为 [ACTION, REACTION] 事件对。

    ``is_first_attack`` 取序列首个事件的 RawAttackEvent.is_first_attack
    （引擎先攻/反击标记，P1-a 填实）。
    """
    attacker_id: str
    defender_id: str
    is_first_attack: bool = True
    events: List[EventContract] = Field(default_factory=list)


class RoundBlock(BaseModel):
    """回合块（Doc 14 §5）。

    ``distance`` / ``first`` / ``first_reason`` 与 CONTEXT/SUMMARY 事件
    由引擎每回合开场与终局生产（P1-a 填实）。
    """
    round_number: int
    distance: int = 0
    first: Optional[Side] = None
    first_reason: Optional[FirstReason] = None
    context_events: List[EventContract] = Field(default_factory=list)
    attack_sequences: List[AttackSequenceBlock] = Field(default_factory=list)
    summary_events: List[EventContract] = Field(default_factory=list)


class SideSummary(BaseModel):
    """终局单方小结（Doc 14 §7.1 summary 成员）。"""
    hp: int
    max_hp: int
    hp_pct: float
    en: int
    will: int
    alive: bool


class ResultSummary(BaseModel):
    """终局双方小结（Doc 14 §7.1）。"""
    a: SideSummary
    b: SideSummary


class ResultBlock(BaseModel):
    """终局结果（Doc 14 §7.1）：finish + winner 正交表达。

    不用引擎 get_result() 的 a_wins/b_wins 口径——那无法区分击破与判定。
    """
    finish: Literal["ko", "decision", "draw"]
    winner: Optional[Side] = None
    rounds_fought: int
    summary: ResultSummary


class TimelineDocument(BaseModel):
    """战斗时间轴顶层文档（Doc 14 §3）：meta / init / rounds / result 四块。"""
    meta: TimelineMeta
    init: InitBlock
    rounds: List[RoundBlock] = Field(default_factory=list)
    result: ResultBlock
