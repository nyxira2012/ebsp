from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from src.pve.enums import SessionStatus, NodeType, CombatOutcome
from src.pve.models import MapGraph, MapNode, PveSquadState, PveEntityState

# -----------------
# 响应部分
# -----------------
class NodeInfo(BaseModel):
    """单独的地块信息(返回给前端的剥离版)"""
    id: int
    x: int
    y: int
    type: str # string literal
    event_id: Optional[str] = None
    cleared: bool
    revealed: bool
    neighbors: List[int]

class PveMapResponse(BaseModel):
    width: int
    height: int
    nodes: Dict[int, NodeInfo] # 只返回 revealed=True的 或 特定的节点
    start_node_id: int
    boss_node_id: int # 如果还没走到boss可能返回-1 (Phase 1 简化先全返回)

class PveSessionResponse(BaseModel):
    session_id: int
    user_id: int
    region_id: str
    current_layer: int
    current_node_id: int
    status: str
    map_data: PveMapResponse
    squad_state: PveSquadState # 己方的残血信息
    credits_earned: int
    pending_rewards_count: int # 把背包详情脱敏成只告诉玩家"10件"

# -----------------
# 请求部分
# -----------------
class EnterRegionRequest(BaseModel):
    region_id: str
    mothership_id: Optional[str] = None
    locked_mechas: List[int] = [] # 用户选择要带进副本的 user_mechas.id 列表
    idempotency_key: Optional[str] = None # 用于防止重复请求创建多个会话

class MoveRequest(BaseModel):
    target_node_id: int
    
class EngageRequest(BaseModel):
    node_id: int # 虽然战斗通常在 current_node 触发，显式传递增加校验

class InteractRequest(BaseModel):
    action: str # "open_chest" / "clear_debris" 等

class ExtractRequest(BaseModel):
    exit_method: str # "BOSS_CLEAR" (通关) 或者是 "VOLUNTARY_EXIT" (半途撤离) 或 "EMERGENCY_EXIT"
    
# -----------------
# 行为返回部分
# -----------------
class MoveResponse(BaseModel):
    reached_node_id: int
    path_taken: List[int]
    truncated: bool
    truncation_reason: Optional[str]
    triggered_event: Optional[str] # NodeType.name
    revealed_nodes: List[int] # 本次揭示了哪些节点的ID，让前端播放云雾散去动画

class BattleResultResponse(BaseModel):
    outcome: str
    rounds_fought: int
    player_states: List[PveEntityState]
    enemy_state: Optional[PveEntityState] # DRAW的车轮战残局才会返回
    credits_earned: int
    loot_drops: List[Dict[str, Any]] # 本次战斗刚获得的临时收容掉落

class FinalizeResponse(BaseModel):
    exit_method: str
    original_equips: int
    final_equips: int
    original_items: int
    final_items: int
    received_items_detail: Optional[Dict[str, Any]] = None # (如果有必要，可以返回带回去的明细)
