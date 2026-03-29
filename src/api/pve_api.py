from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.session import get_async_session
from src.user.dependencies import get_current_user
from src.user.schemas import UserResponse
from src.pve.schemas import (
    EnterRegionRequest, AdvanceRequest, EngageRequest,
    PveSessionResponse, AdvanceResponse, BattleResultResponse,
    FinalizeResponse, ExtractRequest, EventInfo
)

from src.pve.session_manager import PveSessionManager
from src.pve.battle_bridge import BattleBridge
from src.pve.reward_controller import RewardController
from src.pve.services import PveEntryService
from src.api.context import get_loader
from src.pve.enums import SessionStatus, CombatOutcome, ExitMethod
from src.factory import MechaFactory
from src.user.inventory import InventoryService

router = APIRouter(prefix="/pve", tags=["pve-system"])

def get_pve_session_or_404(session_id: int):
    session = PveSessionManager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="PVE Session not found")
    return session

@router.post("/enter-region", response_model=PveSessionResponse)
async def enter_region(
    req: EnterRegionRequest,
    user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    进入 PVE 副本，锁定队伍创建会话
    """
    loader = get_loader()
    session_data = await PveEntryService.enter_region(
        db=db,
        user_id=user.id,
        region_id=req.region_id,
        mothership_id=req.mothership_id,
        locked_mecha_ids=req.locked_mechas,
        loader=loader
    )
    return session_data

@router.post("/sessions/{session_id}/advance", response_model=AdvanceResponse)
async def advance_sequence(
    session_id: int,
    req: AdvanceRequest,
    user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    在当前副本事件序列上推进一格
    """
    session = get_pve_session_or_404(session_id)
    
    if session.event_sequence.is_complete():
        raise HTTPException(status_code=400, detail="Event sequence already complete")
        
    has_more = session.event_sequence.advance()
    current_event = session.event_sequence.current_event()
    
    event_info = None
    if current_event:
        event_info = EventInfo(
            index=current_event.index,
            event_type=current_event.event_type.value,
            event_id=current_event.event_id, # 前端如果需要脱敏该在这里隐掉
            cleared=current_event.cleared
        )
        
    return AdvanceResponse(
        new_event_index=session.event_sequence.current_index,
        current_event=event_info,
        sequence_complete=not has_more
    )

@router.post("/sessions/{session_id}/engage", response_model=BattleResultResponse)
async def engage_battle(
    session_id: int,
    req: EngageRequest,
    user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    在截停点/明雷点触发遭遇战
    """
    session = get_pve_session_or_404(session_id)
    loader = get_loader()
    mothership_config = loader.get_mothership_config("ms_01") # Mock
    
    # TODO factory 需要初始化 loader
    mecha_factory = MechaFactory() 
    
    result = BattleBridge.engage(
        session=session,
        event_index=req.event_index,
        loader=loader,
        mothership_config=mothership_config,
        mecha_factory=mecha_factory,
        player_index=0
    )
    
    # Append loot if win
    if result.outcome == CombatOutcome.WIN:
        RewardController.add_pending_loot(session, result.loot_drops)
        session.credits_earned += result.credits_earned
        
    return BattleResultResponse(
        outcome=result.outcome.name,
        rounds_fought=result.rounds_fought,
        player_states=result.player_states,
        enemy_state=result.enemy_state,
        credits_earned=result.credits_earned,
        loot_drops=result.loot_drops
    )

@router.post("/sessions/{session_id}/extract", response_model=FinalizeResponse)
async def extract_loot(
    session_id: int,
    req: ExtractRequest,
    user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    撤退（通关/半路退出），带出战利品，并销毁 Session
    """
    session = get_pve_session_or_404(session_id)
    loader = get_loader()
    mothership_config = loader.get_mothership_config("ms_01") # Mock
    
    inv_service = InventoryService(session=db, loader=loader)
    exit_method = ExitMethod(req.exit_method)
    
    summary = await RewardController.finalize(
        db=db,
        session_data=session,
        exit_method=exit_method,
        inventory_service=inv_service,
        mothership_config=mothership_config
    )
    
    # 销毁内存中的 session
    PveSessionManager.destroy_session(session_id)
    
    # API 层的 DB commit 交给中间件或主动提交
    await db.commit()
    
    return FinalizeResponse(
        exit_method=summary.get("exit_method", ""),
        original_equips=summary.get("original_equips", 0),
        final_equips=summary.get("final_equips", 0),
        original_items=summary.get("original_items", 0),
        final_items=summary.get("final_items", 0)
    )

@router.post("/sessions/{session_id}/abandon")
async def abandon_session(
    session_id: int,
    user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    中途强退，不撤退直接销毁/超时兜底（血本无归）
    """
    session = get_pve_session_or_404(session_id)
    PveSessionManager.destroy_session(session_id)
    return {"status": "abandoned"}
