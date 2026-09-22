from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.session import get_async_session
from src.user.dependencies import get_current_user
from src.user.schemas import UserResponse
from src.models import MothershipConfig
from src.pve.schemas import (
    EnterRegionRequest, AdvanceRequest, EngageRequest,
    PveSessionResponse, AdvanceResponse, BattleResultResponse,
    FinalizeResponse, ExtractRequest, EventInfo, PveEventSequenceResponse,
    BattleReplayResponse
)

from src.pve.session_manager import PveSessionManager
from src.pve.battle_bridge import BattleBridge
from src.pve.reward_controller import RewardController
from src.pve.services import PveEntryService
from src.pve.progress_service import PveProgressService
from src.api.context import get_loader
from src.pve.enums import SessionStatus, CombatOutcome, ExitMethod
from src.factory import MechaFactory
from src.user.item_system import GrantManifestMismatchError, ItemSystem
from src.user.service import MechasNotOwnedError, OnboardingService

router = APIRouter(prefix="/pve", tags=["pve-system"])

def get_pve_session_or_404(session_id: int, user_id: int):
    """取会话并校验属主（Doc 7 v2.2 §11.3 统一入口）。

    他人会话与不存在同口径 404，不泄露他人会话存在性。
    """
    session = PveSessionManager.get_session(session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(status_code=404, detail="PVE Session not found")
    return session

async def _resolve_player_mothership(db: AsyncSession, user_id: int, loader) -> MothershipConfig:
    """读玩家当前母舰配置（解析机制在服务层，此处只做 404 翻译）。

    记录缺失（ValueError）与 current_id 引用未知配置（KeyError）同属
    数据缺陷 → 同口径 404。
    """
    try:
        return await PveEntryService.resolve_current_mothership_config(db, user_id, loader)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="玩家母舰配置不存在")

@router.get("/regions/{region_id}/zones")
async def get_zones(
    region_id: str,
    user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    获取大区域下的子区域解锁状态与隐藏节点刷新结果
    """
    loader = get_loader()
    try:
        zone_status = await PveProgressService.get_region_status(db, user.id, region_id, loader)
        await db.commit()  # 因为可能会roll隐藏节点并写入
        return {"status": zone_status}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

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

    # 编队不再强制（Doc 7 v2.3 §11.2 开发期放宽）：未锁定机体时由服务层
    # 依次回退出战编队/演示机体；显式锁定则仍校验归属（他人机体不得借道
    # locked_mechas 入队）
    if req.locked_mechas:
        try:
            await OnboardingService.assert_mechas_owned(db, user.id, req.locked_mechas)
        except MechasNotOwnedError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": e.code,
                    "message": "锁定编队包含不属于你的机体",
                    "mecha_ids": e.mecha_ids,
                },
            )

    try:
        session_data = await PveEntryService.enter_region(
            db=db,
            user_id=user.id,
            region_id=req.region_id,
            zone_id=req.zone_id,
            mothership_id=req.mothership_id,
            locked_mecha_ids=req.locked_mechas,
            loader=loader
        )
    except ValueError as e:
        # 母舰/进度等业务校验失败 → 400；编队空缺已由服务层演示回退兜底，
        # 此处 ValueError 仅剩回退兜底也失败的缺陷级场景
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        # 未知区域/母舰配置 ID → 404（对齐 get_zones 的 KeyError 口径）
        raise HTTPException(status_code=404, detail=str(e))
    
    # 构造响应，只暴露 current_index 之前的事件
    visible_events = [
        ev.to_event_info()
        for ev in session_data.event_sequence.events if ev.index <= session_data.event_sequence.current_index
    ]
    
    response_data = PveSessionResponse(
        session_id=session_data.session_id,
        user_id=session_data.user_id,
        region_id=session_data.region_id,
        zone_id=session_data.zone_id,
        current_event_index=session_data.event_sequence.current_index,
        status=session_data.status.value,
        sequence=PveEventSequenceResponse(
            total_events=len(session_data.event_sequence.events),
            current_index=session_data.event_sequence.current_index,
            visible_events=visible_events
        ),
        squad_state=session_data.squad_state,
        credits_earned=session_data.credits_earned,
        pending_rewards_count=len(session_data.pending_rewards.equipments) + len(session_data.pending_rewards.items)
    )
    return response_data

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
    session = get_pve_session_or_404(session_id, user.id)
    
    if req.expected_index != session.event_sequence.current_index:
        # 同步修正
        current_event = session.event_sequence.current_event()
        event_info = None
        if current_event:
            event_info = current_event.to_event_info()
        return AdvanceResponse(
            new_event_index=session.event_sequence.current_index,
            current_event=event_info,
            sequence_complete=session.event_sequence.is_complete(),
            sync_correction=True
        )

    if session.event_sequence.is_complete():
        raise HTTPException(status_code=400, detail="Event sequence already complete")
        
    # 战报暂存至事件点消化完成（Doc 15 §6）：推进即清理旧事件点暂存，
    # 不变量在会话本体（PveSessionData.advance_event）
    has_more = session.advance_event()

    current_event = session.event_sequence.current_event()
    
    event_info = None
    if current_event:
        event_info = current_event.to_event_info()

    return AdvanceResponse(
        new_event_index=session.event_sequence.current_index,
        current_event=event_info,
        sequence_complete=not has_more,
        sync_correction=False
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
    session = get_pve_session_or_404(session_id, user.id)
    
    if req.event_index != session.event_sequence.current_index:
        raise HTTPException(status_code=400, detail="Event index out of sync. Please advance.")
        
    current_event = session.event_sequence.current_event()
    if not current_event:
        raise HTTPException(status_code=400, detail="No current event to engage")
        
    if current_event.cleared:
        raise HTTPException(status_code=400, detail="Event already cleared")
        
    if current_event.event_type.value not in ("COMBAT", "ELITE_COMBAT", "BOSS_COMBAT"):
        raise HTTPException(status_code=400, detail="Event is not a combat event")

    loader = get_loader()
    mothership_config = await _resolve_player_mothership(db, user.id, loader)

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
        
    # 完整战报不经 engage 下发（Doc 15 §5）：已由 BattleBridge 暂存至
    # session.battle_reports，前端经 GET /sessions/{id}/battle/{event_index} 拉取
    return BattleResultResponse(
        outcome=result.outcome.name,
        rounds_fought=result.rounds_fought,
        player_states=result.player_states,
        enemy_state=result.enemy_state,
        credits_earned=result.credits_earned,
        loot_drops=result.loot_drops
    )

@router.get("/sessions/{session_id}/battle/{event_index}", response_model=BattleReplayResponse)
async def replay_battle(
    session_id: int,
    event_index: int,
    user: UserResponse = Depends(get_current_user)
):
    """
    重放已裁定战报（Doc 14 §9.5：PVE 战斗页重入=重放，非新对局）

    暂存不存在（进程重启丢失/已随推进清理/从未接敌）→ 404，
    前端据此降级为仅展示终局摘要（Doc 15 §6）。
    """
    session = get_pve_session_or_404(session_id, user.id)

    battle_report = session.battle_reports.get(event_index)
    if battle_report is None:
        raise HTTPException(status_code=404, detail="No cached battle report for this event")

    return BattleReplayResponse(battle_report=battle_report)

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
    session = get_pve_session_or_404(session_id, user.id)
    loader = get_loader()
    mothership_config = await _resolve_player_mothership(db, user.id, loader)

    exit_method = ExitMethod(req.exit_method)
    item_system = ItemSystem(db, loader=loader)

    try:
        summary = await RewardController.finalize(
            db=db,
            session_data=session,
            exit_method=exit_method,
            item_system=item_system,
            mothership_config=mothership_config,
            loader=loader
        )
    except GrantManifestMismatchError:
        # 清单不符（场景 4.10）：rejected 留档票据已 flush 进当前事务，先提交
        # 让留档落库（回滚约束见 GrantManifestMismatchError docstring），再翻译
        # 400——当场不入包、有提示、日志有痕；会话未删，资产不凭空消失
        await db.commit()
        raise HTTPException(status_code=400, detail="本批未发放，已记录")

    # 销毁内存中的 session
    PveSessionManager.destroy_session(session_id)

    # API 层的 DB commit 交给中间件或主动提交
    await db.commit()

    return FinalizeResponse(
        exit_method=summary.get("exit_method", ""),
        original_equips=summary.get("original_equips", 0),
        final_equips=summary.get("final_equips", 0),
        original_items=summary.get("original_items", 0),
        final_items=summary.get("final_items", 0),
        ticket_id=summary.get("ticket_id"),
        ticket_status=summary.get("ticket_status"),
        credits=summary.get("credits", 0)
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
    session = get_pve_session_or_404(session_id, user.id)
    PveSessionManager.destroy_session(session_id)
    return {"status": "abandoned"}

@router.post("/sessions/{session_id}/heartbeat")
async def heartbeat(
    session_id: int,
    user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
):
    """
    维持 PVE 会话存活（心跳包）。如果超时未发，后台服务会回收该 Session。
    """
    # get_session automatically touches last_heartbeat
    session = get_pve_session_or_404(session_id, user.id)
    return {"status": "alive"}
