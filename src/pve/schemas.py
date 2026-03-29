from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from src.pve.enums import SessionStatus, EventType, CombatOutcome
from src.pve.models import PveSquadState, PveEntityState, PveEvent, EventSequence

# -----------------
# 响应部分
# -----------------
class EventInfo(BaseModel):
    """单个事件信息（返回给前端的脱敏视图）"""
    index: int
    event_type: str          # EventType 字符串 ("COMBAT", "LOOT" 等)
    event_id: Optional[str] = None
    cleared: bool

class PveEventSequenceResponse(BaseModel):
    """事件序列概要（前端用于渲染进度条和当前事件）"""
    total_events: int
    current_index: int
    events: List[EventInfo]  # 全量事件列表（event_id 脱敏，不暴露词条详情）

class PveSessionResponse(BaseModel):
    session_id: int
    user_id: int
    region_id: str
    current_layer: int
    current_event_index: int
    status: str
    sequence: PveEventSequenceResponse
    squad_state: PveSquadState          # 己方的残血信息
    credits_earned: int
    pending_rewards_count: int          # 背包详情脱敏为只告诉玩家数量

# -----------------
# 请求部分
# -----------------
class EnterRegionRequest(BaseModel):
    region_id: str
    mothership_id: Optional[str] = None
    locked_mechas: List[int] = []       # 用户选择要带进副本的 user_mechas.id 列表
    idempotency_key: Optional[str] = None  # 用于防止重复请求创建多个会话

class AdvanceRequest(BaseModel):
    """推进到下一事件的请求（无需额外参数，服务端按序列推进）"""
    pass

class EngageRequest(BaseModel):
    event_index: int  # 触发战斗的事件索引，必须与 current_index 一致

class InteractRequest(BaseModel):
    action: str  # "open_chest" / "skip_event" 等

class ExtractRequest(BaseModel):
    exit_method: str  # "BOSS_CLEAR" / "VOLUNTARY_EXIT" / "EMERGENCY_EXIT"

# -----------------
# 行为返回部分
# -----------------
class AdvanceResponse(BaseModel):
    """推进事件后的返回：描述已进入的新事件"""
    new_event_index: int
    current_event: Optional[EventInfo]   # 如果序列完成则为 None
    sequence_complete: bool

class BattleResultResponse(BaseModel):
    outcome: str
    rounds_fought: int
    player_states: List[PveEntityState]
    enemy_state: Optional[PveEntityState]  # DRAW 的车轮战残局才会返回
    credits_earned: int
    loot_drops: List[Dict[str, Any]]       # 本次战斗刚获得的临时收容掉落

class FinalizeResponse(BaseModel):
    exit_method: str
    original_equips: int
    final_equips: int
    original_items: int
    final_items: int
    received_items_detail: Optional[Dict[str, Any]] = None
