"""背包系统 REST API (Inventory API)

提供背包状态查询、资产清单、临时货舱票据处理、丢弃与锁定的 HTTP 接口。

设计原则：
    - 所有接口均需 JWT 认证（通过 get_current_user 依赖注入）
    - 资产进出全部走 ItemSystem 门面（Doc 17 六招之外无路），本层只做
      编排与错误翻译，不重写任何门面/服务层逻辑
    - 全程 user_id 过滤，别人的家当动不得（所有权 404 与 pve 属主口径一致）

端点概览：
    - GET  /inventory/status                        - 货舱容量状态 + 待处理票据数
    - GET  /inventory/items                         - 背包资产清单（信用点/装备/穿戴中/材料）
    - GET  /inventory/tickets                       - 待处理票据清单（常驻入口数据源）
    - POST /inventory/tickets/{id}/accept           - 票据放行入包
    - POST /inventory/tickets/{id}/discard          - 逐件丢弃寄存物
    - POST /inventory/equipments/{id}/lock|unlock   - 装备锁定/解锁
    - POST /inventory/equipments/{id}/discard       - 背包装备丢弃
    - POST /inventory/items/{item_id}/discard       - 材料丢弃
    - POST /inventory/debug/generate-item           - 调试发放（走门面票据）

参考文档：Doc 17 物品管理系统（接管 Doc 12 超载流程，旧 /finalize 已退役）
"""

from uuid import uuid4
from collections.abc import Coroutine
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_async_session
from src.database.models import User, UserEquipment, UserItem
from src.user.dependencies import get_current_user
from src.user.inventory import InventoryService
from src.user.item_system import (
    CapacityShortfallError,
    GrantManifestMismatchError,
    ItemLockedError,
    ItemSystem,
    TicketStateError,
    make_receipt_id,
)
from src.user.schemas import (
    InventoryStatus,
    UserEquipmentDB,
    UserItemDB,
    MaterialItemDB,
    InventoryItemsResponse,
    TicketListResponse,
    TicketView,
    DiscardTicketItemRequest,
    DiscardItemRequest,
    EquipmentData,
)
from src.api.context import get_loader
from src.api.errors import commit_and_report_mismatch

router = APIRouter(prefix="/inventory", tags=["背包系统"])


def _item_system(session: AsyncSession) -> ItemSystem:
    """构造物品系统门面（每请求一个；loader 为全局单例）。"""
    return ItemSystem(session, loader=get_loader())


def _translate_facade_error(e: ValueError) -> HTTPException:
    """门面 ValueError → HTTP 翻译（本 router 统一口径）。

    映射（Doc 17 批3）：
        - ItemLockedError → 400 物品已锁定，请先解锁（场景 4.7）
        - CapacityShortfallError → 400 + 结构化短差 {message, shortfall}（场景 4.2）
        - TicketStateError → 409 清单已变更，请刷新（场景 4.11 并发冲突）
        - 其余 ValueError（归属/查无/装备使用中/清单下标越界/材料不存在或
          数量不足等业务拒绝）→ 404（与 pve 会话属主 404 口径一致）

    GrantManifestMismatchError 不经本映射：它要求先提交 rejected 留档
    再翻译（回滚约束见其 docstring），走 commit_and_report_mismatch。
    """
    if isinstance(e, ItemLockedError):
        return HTTPException(status_code=400, detail="物品已锁定，请先解锁")
    if isinstance(e, CapacityShortfallError):
        return HTTPException(status_code=400, detail={
            "message": f"货舱放不下，还差 {e.shortfall} 格",
            "shortfall": e.shortfall,
        })
    if isinstance(e, TicketStateError):
        return HTTPException(status_code=409, detail="清单已变更，请刷新")
    return HTTPException(status_code=404, detail=str(e))


async def _commit_facade(session: AsyncSession, call: Coroutine[Any, Any, Any]) -> Any:
    """门面调用统一编排壳：异常翻译 + 成功后提交（变动端点共用）。

    GrantManifestMismatchError 不经此壳——须先提交 rejected 留档再翻译，
    走 commit_and_report_mismatch（回滚约束）。
    """
    try:
        result = await call
    except ValueError as e:
        raise _translate_facade_error(e)
    await session.commit()
    return result


@router.get("/status", response_model=InventoryStatus)
async def get_inventory_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """获取当前背包容量状态与待处理票据数。

    pending_tickets 是背包页常驻入口「临时货舱有 N 件待处理」的数据源
    （Doc 17 场景 4.1/4.3；无寄存时为 0，前端据此隐藏入口）。

    Args:
        current_user: 当前登录用户（由JWT Token解析）
        session: 数据库会话

    Returns:
        InventoryStatus: current/capacity/available + pending_tickets
    """
    loader = get_loader()
    inv_status = await InventoryService(session, loader=loader).get_status(current_user.id)
    inv_status.pending_tickets = await _item_system(session).count_pending_tickets(current_user.id)
    return inv_status


@router.get("/items", response_model=InventoryItemsResponse)
async def list_inventory_items(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """列出背包资产（Doc 17 场景 4.8：看家当）。

    信用点单独显示；穿戴中装备单列一栏（不占货舱格）；材料带展示名，
    查不到模板回退 item_id（loot 的 item_id 可能不在 items.json，不因
    展示断链）。

    Returns:
        InventoryItemsResponse: credits / equipments(未装备) / equipped(穿戴中) / items
    """
    loader = get_loader()

    equip_res = await session.execute(
        select(UserEquipment).where(UserEquipment.user_id == current_user.id)
    )
    all_equips = equip_res.scalars().all()
    equipments = [UserEquipmentDB.model_validate(e) for e in all_equips if not e.is_equipped]
    equipped = [UserEquipmentDB.model_validate(e) for e in all_equips if e.is_equipped]

    item_res = await session.execute(
        select(UserItem).where(UserItem.user_id == current_user.id)
    )
    items = []
    for row in item_res.scalars().all():
        config = loader.get_material_config(row.item_id)
        name = config.name if config else row.item_id
        items.append(MaterialItemDB(**UserItemDB.model_validate(row).model_dump(), name=name))

    credits = await _item_system(session).get_credits(current_user.id)
    return InventoryItemsResponse(
        credits=credits, equipments=equipments, equipped=equipped, items=items
    )


@router.get("/tickets", response_model=TicketListResponse)
async def list_tickets(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """待处理票据清单（临时货舱，Doc 17 场景 4.3 常驻入口数据源）。

    rejected 留档票据不占待处理提醒（场景 4.10）；每条附系统算好的
    required_slots/shortfall，画面只显示（附录 A4）。
    """
    tickets = await _item_system(session).list_tickets(current_user.id)
    return TicketListResponse(tickets=[TicketView.model_validate(t) for t in tickets])


@router.post("/tickets/{ticket_id}/accept")
async def accept_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """放行票据入包（Doc 17 场景 4.1/4.2：整批全进或全不进）。

    容量不够 → 400 结构化短差（寄存不动，腾格后再来）；票据已放行 →
    幂等 200 already=true（场景 4.4 连点只到账一次）；票据已清空/已拒收
    → 409 提示刷新（场景 4.11）。
    """
    return await _commit_facade(
        session, _item_system(session).accept_ticket(current_user.id, ticket_id)
    )


@router.post("/tickets/{ticket_id}/discard")
async def discard_ticket_item(
    ticket_id: int,
    body: DiscardTicketItemRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """逐件丢弃寄存物（Doc 17 场景 4.2；二次确认在画面层）。

    丢弃直接生效不可恢复；票据非 pending（旧画面并发点丢）→ 409 提示
    刷新清单（场景 4.11）。
    """
    return await _commit_facade(
        session,
        _item_system(session).discard_ticket_item(
            current_user.id, ticket_id, body.entry_type, body.index
        ),
    )


@router.post("/equipments/{equipment_id}/lock")
async def lock_equipment(
    equipment_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """锁定装备（Doc 17 场景 4.7：锁定后丢弃/出售/消耗类一律被拒）。"""
    await _commit_facade(
        session, _item_system(session).set_lock(current_user.id, equipment_id, True)
    )
    return {"status": "locked"}


@router.post("/equipments/{equipment_id}/unlock")
async def unlock_equipment(
    equipment_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """解锁装备（恢复可丢弃/可消耗）。"""
    await _commit_facade(
        session, _item_system(session).set_lock(current_user.id, equipment_id, False)
    )
    return {"status": "unlocked"}


@router.post("/equipments/{equipment_id}/discard")
async def discard_equipment(
    equipment_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """丢弃背包装备（物理删除，真没了不可恢复，Doc 17 §8 D7）。

    已锁定 → 400 先解锁（场景 4.7）；穿戴使用中/不属于本人 → 拒绝。
    """
    await _commit_facade(
        session, _item_system(session).discard_equipment(current_user.id, equipment_id)
    )
    return {"status": "discarded"}


@router.post("/items/{item_id}/discard")
async def discard_item(
    item_id: str,
    body: DiscardItemRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """丢弃背包材料（按数量扣减，归零删行腾格）。"""
    await _commit_facade(
        session, _item_system(session).discard_item(current_user.id, item_id, body.quantity)
    )
    return {"status": "discarded"}


@router.post("/debug/generate-item")
async def debug_generate_item(
    equipment_id: str,
    base_ilvl: int = 1,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """调试接口：随机词条装备生成并经统一发放门面入库（Doc 8 + Doc 17 §5.5）。

    不再直接写背包：submit_grant 建票据后立即放行。容量不够时票据留
    pending（返回 pending 而非 400），玩家从临时货舱清理后收入；deprecated
    模板拒发生成（场景 4.14：新发放不再产出停用模板）。
    """
    from src.core.item_generator import EquipmentGenerator

    loader = get_loader()
    config = loader.equipments.get(equipment_id)
    if config is not None and config.deprecated:
        raise HTTPException(status_code=400, detail="模板已停用，不再发放")

    generator = EquipmentGenerator(loader)
    try:
        random_stats = generator.generate_equipment(equipment_id, base_ilvl)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    item_system = _item_system(session)
    equip_data = EquipmentData(
        equipment_id=equipment_id,
        enhancement_level=0,
        random_stats=random_stats
    )
    try:
        ticket = await item_system.submit_grant(
            current_user.id,
            make_receipt_id("debug", uuid4().hex),
            "debug",
            equipments=[equip_data],
            items=[],
        )
    except GrantManifestMismatchError:
        await commit_and_report_mismatch(session)  # 先提交 rejected 留档再 400（回滚约束）

    try:
        await item_system.accept_ticket(current_user.id, ticket.id)
    except CapacityShortfallError:
        # 容量不够：票据留 pending 寄存（不 400），常驻入口兜底
        await session.commit()
        return {"status": "pending", "ticket_id": ticket.id, "generated_stats": random_stats}

    await session.commit()
    return {"status": "success", "generated_stats": random_stats}
