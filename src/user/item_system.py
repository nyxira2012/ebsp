"""物品系统唯一门面 (Item System Facade)

玩家一切家当——装备、材料、信用点——从这一扇门进出（Doc 17）。六招中
本模块承载发放/消耗/丢弃/锁定四招与货币两腿；交换由调用方在同一事务内
拼装 charge_credits + 玩法入库（母舰购买批2落地）；穿戴/卸下在
equipment_service（容量检查已统一走 InventoryService）。

五道检查在此集中生效，门外的人（商店、强化、副本结算）只能递单子、摸不
到账本：
    容量 —— 放行前按 InventoryService 算整批所需，不够整批寄存不进
    归属 —— 所有资产操作按 (user_id, 资产id) 过滤，别人的家当动不得
    锁定 —— 锁定物对丢弃/消耗一律拒绝，先解锁
    余额 —— 扣款先锁 users 行核对短差，不够分文不动
    防重复 —— 回执编号唯一，同回执再交原样退回已有票据

事务边界归调用方：本模块只 flush 不 commit。
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import ExternalGrantLedger, ItemTicket, User, UserEquipment, UserItem
from src.user.inventory import IMothershipProvider, InventoryService
from src.user.schemas import AddResult, EquipmentData, ItemData

if TYPE_CHECKING:
    from src.loader import DataLoader

logger = logging.getLogger(__name__)


class GrantManifestMismatchError(ValueError):
    """发放清单不符（模板不存在/数量非法/回执归属冲突）。

    Doc 17 场景 4.10 单点收口：门内已建 rejected 留档票据并记一行日志，
    调用方只需把本异常翻译成「本批未发放，已记录」。

    回滚约束：rejected 留档票据已 flush 进当前事务，捕获本异常的一方
    不得整体 rollback——否则留档被一并回滚，违反 4.10 留档要求；API 层
    应让留档随事务提交（必要时先行 commit）再翻译 400。
    """


class InsufficientCreditsError(ValueError):
    """信用点不足（Doc 17 场景 4.6：余额分文不动）。

    Attributes:
        shortfall: 还差的信用点数。
    """

    def __init__(self, message: str, *, shortfall: int) -> None:
        super().__init__(message)
        self.shortfall = shortfall


class CapacityShortfallError(ValueError):
    """货舱容量不足（Doc 17 场景 4.2：整批全进或全不进）。

    Attributes:
        shortfall: 还差的格子数。
    """

    def __init__(self, message: str, *, shortfall: int) -> None:
        super().__init__(message)
        self.shortfall = shortfall


class TicketStateError(ValueError):
    """票据状态不符（已放行/已清空/已拒收，提示调用方刷新清单）。"""


class ItemLockedError(ValueError):
    """锁定物拒动（Doc 17 场景 4.7：丢弃/出售/消耗类一律拒绝，提示先解锁）。"""


class TicketStatus:
    """票据状态单一源（与 ItemTicket.status 的字面量一一对应）。"""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DISCARDED = "discarded"
    REJECTED = "rejected"


def make_receipt_id(source: str, key: str) -> str:
    """构造回执编号（Doc 17 场景 4.12）。

    格式单点维护（pve:{session_id} / starter:{user_id} / debug:{uuid}），
    调用方不手拼，保证 submit_grant 唯一键口径一致。

    Args:
        source: 发放来源标识。
        key: 来源内唯一的业务键。

    Returns:
        str: 全局唯一回执编号。
    """
    return f"{source}:{key}"


def _pack_manifest(
    equipments: List[EquipmentData], items: List[ItemData], credits: int
) -> Dict[str, Any]:
    """把发放清单压成票据/台账的 manifest JSON 结构（Doc 17 技术设计 §3）。"""
    return {
        "credits": credits,
        "equipments": [e.model_dump() for e in equipments],
        "items": [i.model_dump() for i in items],
    }


def _validate_manifest(
    equipments: List[EquipmentData],
    items: List[ItemData],
    credits: int,
    loader: Optional["DataLoader"],
) -> Optional[str]:
    """清单结构校验，返回问题描述（None=通过）。

    只做结构合法性（数量/模板存在），不做容量判定——容量属于放行时点
    （accept_ticket），寄存本身不占格。

    loader 为 None 时跳过模板校验：与 InventoryService 的 Mock 回退同款
    测试缝隙，生产接线必须传 loader。
    """
    if credits < 0:
        return f"信用点数量非法: {credits}"
    if loader is not None:
        for e in equipments:
            if e.equipment_id not in loader.equipments:
                return f"装备模板不存在: {e.equipment_id}"
    for i in items:
        if i.quantity <= 0:
            return f"材料数量非法: {i.item_id} x {i.quantity}"
    return None


class ItemSystem:
    """物品系统门面：玩法侧动资产的唯一入口。

    Attributes:
        session: 数据库异步会话（事务边界归调用方）。
        inventory: 复用的背包容量/写入服务。
        loader: 物品模板库，发放清单校验用；None 跳过模板校验（测试缝隙）。
    """

    def __init__(
        self,
        session: AsyncSession,
        loader: Optional["DataLoader"] = None,
        mothership_provider: Optional[IMothershipProvider] = None,
    ) -> None:
        """初始化门面。

        Args:
            session: 数据库异步会话。
            loader: 物品模板库（DataLoader），传 None 跳过模板校验。
            mothership_provider: 母舰能力提供者；与 loader 皆 None 时
                InventoryService 回退 Mock 容量——既有测试缝隙，保持。
        """
        self.session = session
        self.loader = loader
        self.inventory = InventoryService(
            session, mothership_provider=mothership_provider, loader=loader
        )

    # ==================================================================
    # 发放（外部来源专用，凭票据）
    # ==================================================================

    async def submit_grant(
        self,
        user_id: int,
        receipt_id: str,
        source: str,
        *,
        equipments: List[EquipmentData],
        items: List[ItemData],
        credits: int = 0,
        source_detail: Optional[Dict[str, Any]] = None,
    ) -> ItemTicket:
        """受理一笔外部发放，建票据寄存临时货舱（Doc 17 场景 4.12）。

        清单校验失败：门内建 rejected 留档票据（manifest 原样存）+ 记一行
        日志，再抛 GrantManifestMismatchError——rejected 不占待处理提醒、
        不入包（场景 4.10）。同回执再交原样返回已有票据，不再发一次
        （场景 4.4/4.12）；回执被其他用户占用视作清单不符拒绝（所有权把关）。

        Args:
            user_id: 发放对象用户。
            receipt_id: 全局唯一回执编号（make_receipt_id 构造）。
            source: 发放来源标识。
            equipments: 待发放装备清单（随机掷骰已完成的纯结果）。
            items: 待发放材料清单。
            credits: 待发放信用点。
            source_detail: 溯源信息（session_id 等），可选。

        Returns:
            ItemTicket: 本次新建或既有的票据（幂等）。

        Raises:
            GrantManifestMismatchError: 清单校验失败（票据已留档）。
                回滚约束：捕获后不得整体 rollback，否则 rejected 留档被
                一并回滚（违反 4.10）；API 层应让留档随事务提交再翻译 400。
        """
        existing = (await self.session.execute(
            select(ItemTicket).where(ItemTicket.receipt_id == receipt_id)
        )).scalar_one_or_none()
        if existing is not None:
            if existing.user_id != user_id:
                raise GrantManifestMismatchError(f"回执编号已被其他用户占用: {receipt_id}")
            return existing

        problem = _validate_manifest(equipments, items, credits, self.loader)
        if problem is not None:
            ticket = ItemTicket(
                user_id=user_id,
                receipt_id=receipt_id,
                source=source,
                status=TicketStatus.REJECTED,
                manifest=_pack_manifest(equipments, items, credits),
                source_detail=source_detail,
            )
            self.session.add(ticket)
            await self.session.flush()
            logger.error(
                "发放清单不符，已拒收留档 receipt_id=%s source=%s reason=%s",
                receipt_id, source, problem,
            )
            raise GrantManifestMismatchError(f"发放清单不符: {problem}")

        ticket = ItemTicket(
            user_id=user_id,
            receipt_id=receipt_id,
            source=source,
            status=TicketStatus.PENDING,
            manifest=_pack_manifest(equipments, items, credits),
            source_detail=source_detail,
        )
        self.session.add(ticket)
        await self.session.flush()
        return ticket

    async def accept_ticket(self, user_id: int, ticket_id: int) -> Dict[str, Any]:
        """整批放行票据入包（Doc 17 场景 4.1/4.2）。

        容量以 InventoryService 算的整批所需为准，不够抛 CapacityShortfallError
        且分文不进——部分成功永不出现（附录 B2）。够则 add_assets + 信用点
        入账 + 台账一行 + 票据转 accepted；已 accepted 幂等返回（场景 4.4
        连点只到账一次）。

        Args:
            user_id: 票据归属用户。
            ticket_id: 票据 ID。

        Returns:
            dict: {"status": "accepted", "already": bool, "accepted": 到账摘要}。

        Raises:
            ValueError: 票据不存在或不属于该用户。
            TicketStateError: 票据处于 rejected/discarded。
            CapacityShortfallError: 容量不足（shortfall=还差几格）。含预检
                通过后 add_assets 内部复查 OVERFLOW 的并发窗口（fail-closed）。
        """
        ticket = await self._get_ticket_row(user_id, ticket_id, for_update=True)
        if ticket.status == TicketStatus.ACCEPTED:
            return {"status": "accepted", "already": True}
        if ticket.status != TicketStatus.PENDING:
            raise TicketStateError("清单已变更，请刷新")

        equipments, items, credits = self._unpack_manifest(ticket.manifest)
        required = await self.inventory.calculate_required_slots(user_id, equipments, items)
        inventory_status = await self.inventory.get_status(user_id)
        shortfall = required - inventory_status.available
        if shortfall > 0:
            raise CapacityShortfallError(f"货舱放不下，还差 {shortfall} 格", shortfall=shortfall)

        add_result = await self.inventory.add_assets(user_id, equipments, items)
        if add_result == AddResult.OVERFLOW:
            # 预检与写入之间存在并发窗口：add_assets 内部复查容量失败（OVERFLOW
            # 是返回值不是异常）。fail-closed——货物没进包就不得入账/写台账/转
            # accepted，整体不进（附录 B2）；本次事务内的残留改动由调用方回滚。
            fresh = await self.inventory.get_status(user_id)
            shortfall = max(0, required - fresh.available)
            raise CapacityShortfallError(f"货舱放不下，还差 {shortfall} 格", shortfall=shortfall)
        if credits:
            await self.grant_credits(user_id, credits)

        # 台账只在放行时写一行：丢弃/rejected/玩法内转换都不写（Doc 17 附录 C1）
        self.session.add(ExternalGrantLedger(
            user_id=user_id,
            receipt_id=ticket.receipt_id,
            source=ticket.source,
            manifest=ticket.manifest,
            credits_granted=credits,
        ))
        ticket.status = TicketStatus.ACCEPTED
        await self.session.flush()
        return {
            "status": "accepted",
            "already": False,
            "accepted": {
                "ticket_id": ticket.id,
                "receipt_id": ticket.receipt_id,
                "source": ticket.source,
                "credits": credits,
                "equipments": list(ticket.manifest.get("equipments", [])),
                "items": list(ticket.manifest.get("items", [])),
            },
        }

    async def discard_ticket_item(
        self, user_id: int, ticket_id: int, entry_type: str, index: int
    ) -> Dict[str, Any]:
        """逐件丢弃寄存物（Doc 17 场景 4.2；二次确认在画面层）。

        丢弃是唯一不可逆操作：直接从清单删除该条，不可恢复。装备与材料全
        空且无信用点时票据转 discarded。非 pending 一律拒绝——旧画面对已
        放行票据点丢弃按并发冲突处理，提示刷新（场景 4.11）。

        Args:
            user_id: 票据归属用户。
            ticket_id: 票据 ID。
            entry_type: "equipment" 或 "item"。
            index: manifest 对应列表中的下标。

        Returns:
            dict: {"status": 当前票据状态, "remaining": 剩余清单画面形状}。

        Raises:
            ValueError: entry_type 非法 / 票据不存在 / 下标越界。
            TicketStateError: 票据非 pending（清单已变更，请刷新）。
        """
        if entry_type not in ("equipment", "item"):
            raise ValueError(f"未知清单条目类型: {entry_type}")
        ticket = await self._get_ticket_row(user_id, ticket_id, for_update=True)
        if ticket.status != TicketStatus.PENDING:
            raise TicketStateError("清单已变更，请刷新")

        key = "equipments" if entry_type == "equipment" else "items"
        manifest = dict(ticket.manifest)
        entries = list(manifest.get(key, []))
        if not 0 <= index < len(entries):
            raise ValueError(f"清单条目下标越界: {index}")
        del entries[index]
        manifest[key] = entries
        # JSON 列原地变更不被变更追踪发现，须整体重赋值标记脏
        ticket.manifest = manifest
        if not manifest.get("equipments") and not manifest.get("items") and not manifest.get("credits"):
            ticket.status = TicketStatus.DISCARDED
        await self.session.flush()

        inventory_status = await self.inventory.get_status(user_id)
        return {
            "status": ticket.status,
            "remaining": await self._ticket_view(ticket, inventory_status.available),
        }

    async def list_tickets(self, user_id: int) -> List[Dict[str, Any]]:
        """待处理票据清单（Doc 17 场景 4.3 常驻入口的数据源）。

        rejected 不占待处理提醒（场景 4.10）；按创建时间升序。每条附
        required_slots/shortfall——画面只显示、系统算好定死（附录 A4）。

        Args:
            user_id: 用户 ID。

        Returns:
            list[dict]: _ticket_view 形状的列表。
        """
        stmt = (
            select(ItemTicket)
            .where(ItemTicket.user_id == user_id, ItemTicket.status == TicketStatus.PENDING)
            .order_by(ItemTicket.created_at.asc())
        )
        tickets = (await self.session.execute(stmt)).scalars().all()
        if not tickets:
            return []
        inventory_status = await self.inventory.get_status(user_id)
        return [await self._ticket_view(t, inventory_status.available) for t in tickets]

    async def get_ticket(self, user_id: int, ticket_id: int) -> Dict[str, Any]:
        """单张票据的画面形状（含非 pending，供清理页回看留档清单）。

        Raises:
            ValueError: 票据不存在或不属于该用户。
        """
        ticket = await self._get_ticket_row(user_id, ticket_id)
        inventory_status = await self.inventory.get_status(user_id)
        return await self._ticket_view(ticket, inventory_status.available)

    # ==================================================================
    # 丢弃（背包内）
    # ==================================================================

    async def discard_equipment(self, user_id: int, user_equipment_id: int) -> None:
        """丢弃背包内装备：物理删除，真没了不可恢复（Doc 17 §8 D7）。

        Args:
            user_id: 归属用户。
            user_equipment_id: 装备资产 ID。

        Raises:
            ValueError: 装备不存在 / 不属于该用户 / 穿戴使用中。
            ItemLockedError: 已锁定（先解锁）。
        """
        equip = await self._get_user_equipment(user_id, user_equipment_id)
        if equip.is_locked:
            raise ItemLockedError("装备已锁定，先解锁")
        if equip.is_equipped:
            raise ValueError("装备使用中")
        await self.session.delete(equip)
        await self.session.flush()

    async def discard_item(self, user_id: int, item_id: str, quantity: int) -> None:
        """丢弃背包内材料：扣数量，归零删行腾格（Doc 17 场景 4.2）。

        Raises:
            ValueError: 材料不存在 / 数量不足 / 丢弃数量非法。
        """
        await self._deduct_item(user_id, item_id, quantity)

    # ==================================================================
    # 锁定 / 解锁
    # ==================================================================

    async def set_lock(self, user_id: int, user_equipment_id: int, locked: bool) -> None:
        """锁定/解锁装备（Doc 17 场景 4.7：锁定物拒丢弃/出售/消耗）。

        Raises:
            ValueError: 装备不存在或不属于该用户。
        """
        equip = await self._get_user_equipment(user_id, user_equipment_id)
        equip.is_locked = locked
        await self.session.flush()

    # ==================================================================
    # 消耗（纯扣减）
    # ==================================================================

    async def consume(
        self, user_id: int, *, equipments: List[int], items: List[Tuple[str, int]]
    ) -> None:
        """按清单纯扣减资产（强化/合成等玩法扣料走此招）。

        本期无 HTTP 调用方——招式集合完整性（Doc 17 §2/§8 六招裁决）与
        锁定审查用。装备按 id 物理删除；材料扣数量归零删行。

        Args:
            user_id: 归属用户。
            equipments: 待消耗的装备资产 ID 列表。
            items: 待消耗的 (item_id, quantity) 列表。

        Raises:
            ValueError: 资产不存在 / 数量不足 / 装备穿戴使用中。
            ItemLockedError: 任一装备已锁定。
        """
        for user_equipment_id in equipments:
            equip = await self._get_user_equipment(user_id, user_equipment_id)
            if equip.is_locked:
                raise ItemLockedError("装备已锁定，先解锁")
            if equip.is_equipped:
                # 消耗静默删掉穿戴中装备会让机体槽位悬空——与丢弃同口径拒绝
                raise ValueError("装备使用中")
            await self.session.delete(equip)
        for item_id, quantity in items:
            await self._deduct_item(user_id, item_id, quantity)
        await self.session.flush()

    # ==================================================================
    # 货币两腿（发放与交换共用）
    # ==================================================================

    async def get_credits(self, user_id: int) -> int:
        """查询信用点余额。

        Raises:
            ValueError: 用户不存在。
        """
        user = await self._get_user(user_id)
        return user.credits

    async def charge_credits(self, user_id: int, amount: int) -> None:
        """扣信用点：先锁 users 行再核对，不够分文不动（Doc 17 场景 4.6）。

        交换招的支出腿——与玩法入库同事务拼装，任何一环失败由调用方回滚。

        Args:
            user_id: 用户 ID。
            amount: 扣减数额（须为正）。

        Raises:
            ValueError: 用户不存在 / 金额非法。
            InsufficientCreditsError: 余额不足（shortfall=还差多少）。
        """
        if amount <= 0:
            raise ValueError(f"扣减金额非法: {amount}")
        user = await self._get_user(user_id, for_update=True)
        if user.credits < amount:
            raise InsufficientCreditsError(
                f"信用点不够，还差 {amount - user.credits}",
                shortfall=amount - user.credits,
            )
        user.credits -= amount
        await self.session.flush()

    async def grant_credits(self, user_id: int, amount: int) -> None:
        """入账信用点：票据放行的资金腿（写台账在 accept_ticket）；交换的
        出售/拆解直接调用、不写台账（Doc 17 技术设计 §4）。

        与 charge_credits 对称加 users 行锁——同用户「一处收发放、一处买
        母舰」并发时防止 read-modify-write 丢更新。

        Args:
            user_id: 用户 ID。
            amount: 入账数额（须为正）。

        Raises:
            ValueError: 用户不存在 / 金额非法。
        """
        if amount <= 0:
            raise ValueError(f"入账金额非法: {amount}")
        user = await self._get_user(user_id, for_update=True)
        user.credits += amount
        await self.session.flush()

    # ==================================================================
    # 私有 helper（行获取与形状转换，对内共用）
    # ==================================================================

    async def _get_ticket_row(
        self, user_id: int, ticket_id: int, *, for_update: bool = False
    ) -> ItemTicket:
        """按归属取票据行；for_update 行锁串行化并发放行/清理（并发锚点，
        SQLite 退化无锁可接受，PostgreSQL 生效）。

        Raises:
            ValueError: 票据不存在或不属于该用户。
        """
        stmt = select(ItemTicket).where(
            ItemTicket.id == ticket_id, ItemTicket.user_id == user_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        ticket = (await self.session.execute(stmt)).scalar_one_or_none()
        if ticket is None:
            raise ValueError("票据不存在")
        return ticket

    async def _ticket_view(self, ticket: ItemTicket, available: int) -> Dict[str, Any]:
        """票据 → 画面形状（list/get/discard 响应共用；附录 A4：占用与
        还差几格由系统算好定死，画面只显示不改数）。"""
        equipments, items, credits = self._unpack_manifest(ticket.manifest)
        required = await self.inventory.calculate_required_slots(ticket.user_id, equipments, items)
        return {
            "ticket_id": ticket.id,
            "receipt_id": ticket.receipt_id,
            "source": ticket.source,
            "status": ticket.status,
            "credits": credits,
            "equipments": list(ticket.manifest.get("equipments", [])),
            "items": list(ticket.manifest.get("items", [])),
            "required_slots": required,
            "shortfall": max(0, required - available),
        }

    def _unpack_manifest(
        self, manifest: Dict[str, Any]
    ) -> Tuple[List[EquipmentData], List[ItemData], int]:
        """把票据 manifest 还原为 InventoryService 的入参形态。"""
        equipments = [EquipmentData(**e) for e in manifest.get("equipments", [])]
        items = [ItemData(**i) for i in manifest.get("items", [])]
        return equipments, items, int(manifest.get("credits", 0))

    async def _get_user_equipment(self, user_id: int, user_equipment_id: int) -> UserEquipment:
        """按归属取装备行——归属与存在性一道检查（同 equipment_service 口径）。

        Raises:
            ValueError: 装备不存在或不属于该用户。
        """
        equip = (await self.session.execute(
            select(UserEquipment).where(
                UserEquipment.id == user_equipment_id,
                UserEquipment.user_id == user_id,
            )
        )).scalar_one_or_none()
        if equip is None:
            raise ValueError("装备不存在或无权限")
        return equip

    async def _deduct_item(self, user_id: int, item_id: str, quantity: int) -> None:
        """扣减材料数量并归零删行（丢弃与消耗共用）。

        Raises:
            ValueError: 材料不存在 / 数量不足 / 数量非法。
        """
        if quantity <= 0:
            raise ValueError(f"扣减数量非法: {item_id} x {quantity}")
        row = (await self.session.execute(
            select(UserItem).where(UserItem.user_id == user_id, UserItem.item_id == item_id)
        )).scalar_one_or_none()
        if row is None or row.quantity < quantity:
            raise ValueError(f"材料不存在或数量不足: {item_id}")
        row.quantity -= quantity
        if row.quantity <= 0:
            await self.session.delete(row)
        await self.session.flush()

    async def _get_user(self, user_id: int, *, for_update: bool = False) -> User:
        """按 ID 取用户行；for_update 行锁串行化同用户并发资金变动。

        Raises:
            ValueError: 用户不存在。
        """
        stmt = select(User).where(User.id == user_id)
        if for_update:
            stmt = stmt.with_for_update()
        user = (await self.session.execute(stmt)).scalar_one_or_none()
        if user is None:
            raise ValueError("用户不存在")
        return user
