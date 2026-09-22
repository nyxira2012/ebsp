"""物品系统门面单元测试（Doc 17 批1）。

覆盖门面五道检查（容量/归属/锁定/余额/防重复）与票据状态机：发放幂等、
清单不符拒收留档、放行容量与台账、逐件丢弃、锁定、归属、余额。
不接线任何玩法（PVE/购买/API 属批2-4）。

模板校验用 StubLoader（轻量 stub），不起全量 DataLoader；loader=None 时
门面跳过模板校验——与 InventoryService 的 Mock 回退同款测试缝隙。
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import ExternalGrantLedger, ItemTicket, User, UserEquipment, UserItem
from src.user.inventory import MockMothershipProvider
from src.user.item_system import (
    CapacityShortfallError,
    GrantManifestMismatchError,
    InsufficientCreditsError,
    ItemLockedError,
    ItemSystem,
    TicketStateError,
    TicketStatus,
    make_receipt_id,
)
from src.user.schemas import EquipmentData, ItemData
from src.user.security import hash_password


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    user = User(username="item_tester", password_hash=hash_password("password123"))
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def system(db_session: AsyncSession) -> ItemSystem:
    # loader=None：跳过模板校验的测试缝隙，容量走 MockMothershipProvider(100)
    return ItemSystem(db_session)


async def all_rows(db_session: AsyncSession, model: type) -> list:
    return list((await db_session.execute(select(model))).scalars().all())


async def seed_equipment(
    db_session: AsyncSession, user_id: int, *, locked: bool = False, equipped: bool = False
) -> UserEquipment:
    equip = UserEquipment(
        user_id=user_id, equipment_id="wpn_x", is_locked=locked, is_equipped=equipped
    )
    db_session.add(equip)
    await db_session.flush()
    return equip


async def seed_item(
    db_session: AsyncSession, user_id: int, item_id: str = "mat_a", quantity: int = 10
) -> UserItem:
    row = UserItem(user_id=user_id, item_id=item_id, quantity=quantity)
    db_session.add(row)
    await db_session.flush()
    return row


# ============================================================================
# 回执与发放
# ============================================================================

def test_make_receipt_id():
    assert make_receipt_id("pve", "42") == "pve:42"
    assert make_receipt_id("starter", "7") == "starter:7"


async def test_submit_grant_creates_pending_ticket(db_session, user, system):
    receipt = make_receipt_id("debug", "r1")
    ticket = await system.submit_grant(
        user.id, receipt, "debug",
        equipments=[EquipmentData(equipment_id="wpn_a", enhancement_level=2, random_stats={"attack": 5})],
        items=[ItemData(item_id="mat_a", quantity=3)],
        credits=100,
    )
    assert ticket.status == TicketStatus.PENDING
    assert ticket.receipt_id == receipt
    assert ticket.manifest["credits"] == 100
    assert ticket.manifest["equipments"][0]["equipment_id"] == "wpn_a"
    assert ticket.manifest["items"][0]["quantity"] == 3

    # 待处理清单可见（附录 A4：required_slots/shortfall 由系统算好定死）
    pending = await system.list_tickets(user.id)
    assert [t["ticket_id"] for t in pending] == [ticket.id]
    assert pending[0]["required_slots"] == 2  # 1 件装备 + 1 种新材料
    assert pending[0]["shortfall"] == 0
    assert pending[0]["credits"] == 100


async def test_submit_grant_idempotent(db_session, user, system):
    receipt = make_receipt_id("pve", "42")
    payload = dict(equipments=[EquipmentData(equipment_id="wpn_a")], items=[])
    first = await system.submit_grant(user.id, receipt, "pve", **payload)
    second = await system.submit_grant(user.id, receipt, "pve", **payload)
    assert first.id == second.id
    assert len(await all_rows(db_session, ItemTicket)) == 1


async def test_submit_grant_rejects_bad_manifest(db_session, user, system):
    with pytest.raises(GrantManifestMismatchError):
        await system.submit_grant(user.id, "r-bad-credits", "debug", equipments=[], items=[], credits=-1)
    with pytest.raises(GrantManifestMismatchError):
        await system.submit_grant(
            user.id, "r-bad-qty", "debug", equipments=[],
            items=[ItemData(item_id="mat_a", quantity=0)],
        )

    # rejected 留档（manifest 原样存），场景 4.10
    tickets = await all_rows(db_session, ItemTicket)
    assert len(tickets) == 2
    assert {t.status for t in tickets} == {TicketStatus.REJECTED}
    bad_qty = next(t for t in tickets if t.receipt_id == "r-bad-qty")
    assert bad_qty.manifest["items"] == [
        {"item_id": "mat_a", "item_type": "material", "quantity": 0}
    ]

    # 不入包、不占待处理提醒
    assert await all_rows(db_session, UserEquipment) == []
    assert await all_rows(db_session, UserItem) == []
    assert await system.list_tickets(user.id) == []
    assert await system.get_credits(user.id) == 0


async def test_submit_grant_validates_equipment_template(db_session, user):
    class StubLoader:
        equipments = {"wpn_known": object()}

    loader_system = ItemSystem(db_session, loader=StubLoader())
    with pytest.raises(GrantManifestMismatchError):
        await loader_system.submit_grant(
            user.id, "r-unknown", "debug",
            equipments=[EquipmentData(equipment_id="wpn_ghost")], items=[],
        )
    ticket = await loader_system.submit_grant(
        user.id, "r-known", "debug",
        equipments=[EquipmentData(equipment_id="wpn_known")], items=[],
    )
    assert ticket.status == TicketStatus.PENDING


# ============================================================================
# 放行（accept）
# ============================================================================

async def test_accept_ticket_success(db_session, user, system):
    ticket = await system.submit_grant(
        user.id, "r-accept", "pve",
        equipments=[EquipmentData(equipment_id="wpn_a"),
                    EquipmentData(equipment_id="wpn_b", enhancement_level=3)],
        items=[ItemData(item_id="mat_a", quantity=10)],
        credits=500,
    )
    result = await system.accept_ticket(user.id, ticket.id)
    assert result["status"] == "accepted"
    assert result["already"] is False
    assert result["accepted"]["credits"] == 500

    assert await system.get_credits(user.id) == 500
    equips = await all_rows(db_session, UserEquipment)
    assert {e.equipment_id for e in equips} == {"wpn_a", "wpn_b"}
    items = await all_rows(db_session, UserItem)
    assert len(items) == 1 and items[0].quantity == 10

    # 台账一行：品种数量时间回执对得上（场景 4.4）
    ledgers = await all_rows(db_session, ExternalGrantLedger)
    assert len(ledgers) == 1
    ledger = ledgers[0]
    assert ledger.receipt_id == "r-accept"
    assert ledger.source == "pve"
    assert ledger.credits_granted == 500
    assert ledger.result == "accepted"
    assert ledger.manifest["credits"] == 500

    assert ticket.status == TicketStatus.ACCEPTED
    assert await system.list_tickets(user.id) == []


async def test_accept_ticket_capacity_shortfall(db_session, user):
    tight = ItemSystem(db_session, mothership_provider=MockMothershipProvider(capacity=1))
    pre = await tight.submit_grant(
        user.id, "r-pre", "debug", equipments=[EquipmentData(equipment_id="wpn_a")], items=[]
    )
    await tight.accept_ticket(user.id, pre.id)  # 占满唯一的 1 格

    ticket = await tight.submit_grant(
        user.id, "r-overflow", "pve",
        equipments=[EquipmentData(equipment_id="wpn_b")],
        items=[ItemData(item_id="mat_new", quantity=1)],
        credits=100,
    )
    with pytest.raises(CapacityShortfallError) as exc:
        await tight.accept_ticket(user.id, ticket.id)
    assert exc.value.shortfall == 2  # 1 件装备 + 1 种新材料

    # 整批全不进（附录 B2 部分成功永不出现）：分文不动、溢出批无台账、票据仍 pending
    assert await tight.get_credits(user.id) == 0
    assert [e.equipment_id for e in await all_rows(db_session, UserEquipment)] == ["wpn_a"]
    assert await all_rows(db_session, UserItem) == []
    # 前置票据 r-pre 放行合法占一行；溢出批 r-overflow 不得有任何台账
    ledger_receipts = [l.receipt_id for l in await all_rows(db_session, ExternalGrantLedger)]
    assert ledger_receipts == ["r-pre"]
    assert ticket.status == TicketStatus.PENDING
    view = (await tight.list_tickets(user.id))[0]
    assert view["shortfall"] == 2


async def test_accept_ticket_idempotent(db_session, user, system):
    ticket = await system.submit_grant(
        user.id, "r-twice", "pve",
        equipments=[EquipmentData(equipment_id="wpn_a"), EquipmentData(equipment_id="wpn_b")],
        items=[], credits=500,
    )
    first = await system.accept_ticket(user.id, ticket.id)
    second = await system.accept_ticket(user.id, ticket.id)
    assert first["already"] is False
    assert second == {"status": "accepted", "already": True}
    # 连点只到账一次（场景 4.4）：台账仍一行、信用点不双发
    assert await system.get_credits(user.id) == 500
    assert len(await all_rows(db_session, UserEquipment)) == 2
    assert len(await all_rows(db_session, ExternalGrantLedger)) == 1


async def test_ticket_ownership(db_session, user, system):
    other = User(username="other_user", password_hash=hash_password("password123"))
    db_session.add(other)
    await db_session.flush()
    ticket = await system.submit_grant(
        user.id, "r-own", "pve", equipments=[EquipmentData(equipment_id="wpn_a")], items=[]
    )
    with pytest.raises(ValueError):
        await system.accept_ticket(other.id, ticket.id)
    with pytest.raises(ValueError):
        await system.get_ticket(other.id, ticket.id)
    with pytest.raises(ValueError):
        await system.discard_ticket_item(other.id, ticket.id, "equipment", 0)


# ============================================================================
# 逐件丢弃寄存物
# ============================================================================

async def test_discard_ticket_item_then_discarded(db_session, user, system):
    ticket = await system.submit_grant(
        user.id, "r-clean", "pve",
        equipments=[EquipmentData(equipment_id="wpn_a"), EquipmentData(equipment_id="wpn_b")],
        items=[ItemData(item_id="mat_a", quantity=5)],
    )
    r1 = await system.discard_ticket_item(user.id, ticket.id, "equipment", 0)
    assert r1["status"] == TicketStatus.PENDING
    assert [e["equipment_id"] for e in r1["remaining"]["equipments"]] == ["wpn_b"]
    r2 = await system.discard_ticket_item(user.id, ticket.id, "equipment", 0)
    assert r2["remaining"]["equipments"] == []
    r3 = await system.discard_ticket_item(user.id, ticket.id, "item", 0)
    assert r3["status"] == TicketStatus.DISCARDED
    assert r3["remaining"]["items"] == []
    assert await system.list_tickets(user.id) == []


async def test_discard_ticket_item_keeps_pending_while_credits_remain(db_session, user, system):
    ticket = await system.submit_grant(
        user.id, "r-cred", "debug", equipments=[EquipmentData(equipment_id="wpn_a")], items=[], credits=100
    )
    result = await system.discard_ticket_item(user.id, ticket.id, "equipment", 0)
    assert result["status"] == TicketStatus.PENDING
    assert result["remaining"]["credits"] == 100


async def test_discard_ticket_item_rejects_non_pending(db_session, user, system):
    ticket = await system.submit_grant(
        user.id, "r-gone", "pve", equipments=[EquipmentData(equipment_id="wpn_a")], items=[]
    )
    await system.accept_ticket(user.id, ticket.id)
    with pytest.raises(TicketStateError):
        await system.discard_ticket_item(user.id, ticket.id, "equipment", 0)


async def test_discard_ticket_item_rejects_bad_input(db_session, user, system):
    ticket = await system.submit_grant(
        user.id, "r-idx", "debug", equipments=[EquipmentData(equipment_id="wpn_a")], items=[]
    )
    with pytest.raises(ValueError):
        await system.discard_ticket_item(user.id, ticket.id, "weird", 0)
    with pytest.raises(ValueError):
        await system.discard_ticket_item(user.id, ticket.id, "equipment", 5)
    with pytest.raises(ValueError):
        await system.discard_ticket_item(user.id, ticket.id, "equipment", -1)


# ============================================================================
# 背包内丢弃 / 锁定 / 消耗
# ============================================================================

async def test_discard_equipment_success(db_session, user, system):
    equip = await seed_equipment(db_session, user.id)
    await system.discard_equipment(user.id, equip.id)
    assert await all_rows(db_session, UserEquipment) == []


async def test_discard_equipment_locked_rejected(db_session, user, system):
    equip = await seed_equipment(db_session, user.id, locked=True)
    with pytest.raises(ItemLockedError):
        await system.discard_equipment(user.id, equip.id)
    assert len(await all_rows(db_session, UserEquipment)) == 1


async def test_discard_equipment_equipped_rejected(db_session, user, system):
    equip = await seed_equipment(db_session, user.id, equipped=True)
    with pytest.raises(ValueError):
        await system.discard_equipment(user.id, equip.id)
    assert len(await all_rows(db_session, UserEquipment)) == 1


async def test_discard_equipment_ownership_rejected(db_session, user, system):
    other = User(username="other_eq", password_hash=hash_password("password123"))
    db_session.add(other)
    await db_session.flush()
    equip = await seed_equipment(db_session, user.id)
    with pytest.raises(ValueError):
        await system.discard_equipment(other.id, equip.id)
    assert len(await all_rows(db_session, UserEquipment)) == 1


async def test_discard_item_deducts_and_deletes(db_session, user, system):
    row = await seed_item(db_session, user.id, quantity=10)
    await system.discard_item(user.id, "mat_a", 4)
    assert row.quantity == 6
    await system.discard_item(user.id, "mat_a", 6)
    assert await all_rows(db_session, UserItem) == []


async def test_discard_item_insufficient_rejected(db_session, user, system):
    row = await seed_item(db_session, user.id, quantity=10)
    with pytest.raises(ValueError):
        await system.discard_item(user.id, "mat_a", 11)
    with pytest.raises(ValueError):
        await system.discard_item(user.id, "mat_ghost", 1)
    assert row.quantity == 10


async def test_set_lock_toggles(db_session, user, system):
    equip = await seed_equipment(db_session, user.id)
    await system.set_lock(user.id, equip.id, True)
    assert equip.is_locked is True
    await system.set_lock(user.id, equip.id, False)
    assert equip.is_locked is False


async def test_consume_rejects_locked_equipment(db_session, user, system):
    equip = await seed_equipment(db_session, user.id, locked=True)
    with pytest.raises(ItemLockedError):
        await system.consume(user.id, equipments=[equip.id], items=[])
    assert len(await all_rows(db_session, UserEquipment)) == 1


async def test_consume_deducts(db_session, user, system):
    e1 = await seed_equipment(db_session, user.id)
    e2 = await seed_equipment(db_session, user.id)
    await seed_item(db_session, user.id, quantity=5)
    await system.consume(user.id, equipments=[e1.id, e2.id], items=[("mat_a", 5)])
    assert await all_rows(db_session, UserEquipment) == []
    assert await all_rows(db_session, UserItem) == []


async def test_consume_insufficient_items_rejected(db_session, user, system):
    row = await seed_item(db_session, user.id, quantity=2)
    with pytest.raises(ValueError):
        await system.consume(user.id, equipments=[], items=[("mat_a", 3)])
    assert row.quantity == 2


# ============================================================================
# 货币两腿
# ============================================================================

async def test_grant_and_charge_credits(db_session, user, system):
    assert await system.get_credits(user.id) == 0
    await system.grant_credits(user.id, 100)
    assert await system.get_credits(user.id) == 100
    await system.charge_credits(user.id, 60)
    assert await system.get_credits(user.id) == 40


async def test_charge_credits_shortfall(db_session, user, system):
    await system.grant_credits(user.id, 100)
    with pytest.raises(InsufficientCreditsError) as exc:
        await system.charge_credits(user.id, 150)
    assert exc.value.shortfall == 50
    # 分文不动（场景 4.6）
    assert await system.get_credits(user.id) == 100


async def test_credit_amounts_must_be_positive(db_session, user, system):
    with pytest.raises(ValueError):
        await system.charge_credits(user.id, 0)
    with pytest.raises(ValueError):
        await system.charge_credits(user.id, -10)
    with pytest.raises(ValueError):
        await system.grant_credits(user.id, -10)
    assert await system.get_credits(user.id) == 0


async def test_consume_equipped_equipment_rejected(db_session, user, system):
    equip = await seed_equipment(db_session, user.id, equipped=True)
    with pytest.raises(ValueError):
        await system.consume(user.id, equipments=[equip.id], items=[])
    assert len(await all_rows(db_session, UserEquipment)) == 1


async def test_accept_ticket_overflow_rerecheck_fails_closed(db_session, user):
    class ShrinkingMothershipProvider(MockMothershipProvider):
        """复现预检与写入间的并发窗口：首次容量查询（预检 get_status）充足，
        其后（add_assets 内部 can_add 复查）归零——模拟另一事务抢占货舱。"""

        def __init__(self) -> None:
            super().__init__(capacity=100)
            self.calls = 0

        async def get_max_capacity(self, user_id: int) -> int:
            self.calls += 1
            return 100 if self.calls == 1 else 0

    racing = ItemSystem(db_session, mothership_provider=ShrinkingMothershipProvider())
    ticket = await racing.submit_grant(
        user.id, "r-race", "pve", equipments=[EquipmentData(equipment_id="wpn_a")], items=[],
        credits=100,
    )
    with pytest.raises(CapacityShortfallError) as exc:
        await racing.accept_ticket(user.id, ticket.id)
    assert exc.value.shortfall == 1
    # fail-closed：货物没进包，则钱/台账/票据状态一样不动（附录 B2 整批全不进）
    assert await racing.get_credits(user.id) == 0
    assert await all_rows(db_session, UserEquipment) == []
    assert await all_rows(db_session, ExternalGrantLedger) == []
    assert ticket.status == TicketStatus.PENDING
