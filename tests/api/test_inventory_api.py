"""背包系统 API 测试（Doc 17 批3）。

覆盖票据三端点全流程、常驻入口、锁定、材料丢弃、所有权交叉与空态，
全部经 HTTP 打 /inventory/*；测试内用 ItemSystem.submit_grant 直接造
pending 票据（loader=None 跳过模板校验的既有测试缝隙）。

旧 /finalize 超载通道已随 Doc 17 退役：其用例改造为票据流等价断言
（test_accept_ticket_moves_assets_and_credits / test_finalize_endpoint_retired）。
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from src.api.context import get_loader
from src.database.models import User, UserEquipment, UserItem, UserMothership
from src.models import EquipmentConfig
from src.user.item_system import ItemSystem, make_receipt_id
from src.user.schemas import EquipmentData, ItemData
from src.user.security import hash_password


@pytest.fixture
async def authenticated_client(async_client: AsyncClient, db_session):
    """建用户+默认母舰（容量 50）并登录，返回 (client, user)。"""
    user = User(username="inv_user", password_hash=hash_password("pass123"))
    db_session.add(user)
    await db_session.flush()

    mothership = UserMothership(
        user_id=user.id,
        data={"owned_ids": ["light_corvette"], "current_id": "light_corvette"}
    )
    db_session.add(mothership)
    await db_session.commit()

    resp = await async_client.post(
        "/api/user/login", json={"username": "inv_user", "password": "pass123"}
    )
    token = resp.json()["access_token"]
    async_client.headers["Authorization"] = f"Bearer {token}"
    return async_client, user


async def _grant(db_session, user_id: int, receipt_key: str, **manifest) -> object:
    """用门面直造一张 pending 票据并提交（等价旧 finalize 的 add_* 入口）。"""
    system = ItemSystem(db_session)  # loader=None：跳过模板校验的测试缝隙
    ticket = await system.submit_grant(
        user_id,
        make_receipt_id("debug", receipt_key),
        "debug",
        equipments=manifest.get("equipments", []),
        items=manifest.get("items", []),
        credits=manifest.get("credits", 0),
    )
    await db_session.commit()
    return ticket


async def _fill_bag(db_session, user_id: int, count: int) -> None:
    """塞满背包装备（每件 1 格），用于构造容量短差。"""
    db_session.add_all([
        UserEquipment(user_id=user_id, equipment_id=f"filler_{i}")
        for i in range(count)
    ])
    await db_session.commit()


# ============================================================================
# 状态与空态（spec §5：空状态/常驻入口无寄存不显示）
# ============================================================================

@pytest.mark.asyncio
async def test_api_inventory_status(authenticated_client):
    client, user = authenticated_client

    resp = await client.get("/api/inventory/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["capacity"] == 50
    assert data["current"] == 0
    assert data["pending_tickets"] == 0


@pytest.mark.asyncio
async def test_items_and_tickets_empty_state(authenticated_client):
    """空态验收：新号背包空、余额零、无寄存（spec §5 空状态/常驻入口）。"""
    client, user = authenticated_client

    bag = (await client.get("/api/inventory/items")).json()
    assert bag["credits"] == 0
    assert bag["equipments"] == []
    assert bag["equipped"] == []
    assert bag["items"] == []

    tickets = (await client.get("/api/inventory/tickets")).json()
    assert tickets["tickets"] == []


# ============================================================================
# 票据三端点（场景 4.1/4.2/4.11）
# ============================================================================

@pytest.mark.asyncio
async def test_accept_ticket_moves_assets_and_credits(authenticated_client, db_session):
    """放行入包：装备/材料进包、余额动（旧 finalize 用例的票据流等价断言）。"""
    client, user = authenticated_client
    ticket = await _grant(
        db_session, user.id, "acc1",
        equipments=[EquipmentData(equipment_id="wpn_new")],
        items=[ItemData(item_id="mat_scrap", quantity=3)],
        credits=250,
    )

    resp = await client.post(f"/api/inventory/tickets/{ticket.id}/accept")
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert resp.json()["already"] is False

    bag = (await client.get("/api/inventory/items")).json()
    assert bag["credits"] == 250
    assert any(e["equipment_id"] == "wpn_new" for e in bag["equipments"])
    assert any(i["item_id"] == "mat_scrap" and i["quantity"] == 3 for i in bag["items"])


@pytest.mark.asyncio
async def test_accept_ticket_idempotent(authenticated_client, db_session):
    """连点只到账一次：第二次 accept 幂等返回，余额不再增加（场景 4.4）。"""
    client, user = authenticated_client
    ticket = await _grant(db_session, user.id, "acc2", credits=100)

    first = await client.post(f"/api/inventory/tickets/{ticket.id}/accept")
    assert first.status_code == 200
    second = await client.post(f"/api/inventory/tickets/{ticket.id}/accept")
    assert second.status_code == 200
    assert second.json()["already"] is True

    assert (await client.get("/api/inventory/items")).json()["credits"] == 100


@pytest.mark.asyncio
async def test_accept_ticket_capacity_shortfall(authenticated_client, db_session):
    """容量满：400 + 结构化短差，整批寄存不动（场景 4.2）。"""
    client, user = authenticated_client
    await _fill_bag(db_session, user.id, 50)
    ticket = await _grant(
        db_session, user.id, "over1",
        equipments=[EquipmentData(equipment_id="wpn_a"), EquipmentData(equipment_id="wpn_b")],
    )

    resp = await client.post(f"/api/inventory/tickets/{ticket.id}/accept")
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["message"] == "货舱放不下，还差 2 格"
    assert detail["shortfall"] == 2

    # 寄存不动：票据仍 pending，背包未混入
    tickets = (await client.get("/api/inventory/tickets")).json()["tickets"]
    assert len(tickets) == 1 and tickets[0]["shortfall"] == 2
    bag = (await client.get("/api/inventory/items")).json()
    assert not any(e["equipment_id"] == "wpn_a" for e in bag["equipments"])


@pytest.mark.asyncio
async def test_discard_ticket_item_then_accept(authenticated_client, db_session):
    """逐件丢弃寄存物后放行：只入剩余件（场景 4.2 清理引导）。"""
    client, user = authenticated_client
    ticket = await _grant(
        db_session, user.id, "d1",
        equipments=[EquipmentData(equipment_id="wpn_keep"), EquipmentData(equipment_id="wpn_drop")],
    )

    resp = await client.get("/api/inventory/tickets")
    view = resp.json()["tickets"][0]
    assert view["source"] == "debug"
    assert view["required_slots"] == 2
    assert len(view["equipments"]) == 2

    resp = await client.post(
        f"/api/inventory/tickets/{ticket.id}/discard",
        json={"entry_type": "equipment", "index": 1},
    )
    assert resp.status_code == 200
    remaining = resp.json()["remaining"]
    assert [e["equipment_id"] for e in remaining["equipments"]] == ["wpn_keep"]

    resp = await client.post(f"/api/inventory/tickets/{ticket.id}/accept")
    assert resp.status_code == 200

    bag = (await client.get("/api/inventory/items")).json()
    ids = [e["equipment_id"] for e in bag["equipments"]]
    assert "wpn_keep" in ids and "wpn_drop" not in ids


@pytest.mark.asyncio
async def test_discard_all_ticket_entries_rejects_stale_accept(authenticated_client, db_session):
    """清空寄存后票据转 discarded；对旧票据放行/再丢弃 → 409 提示刷新（场景 4.11）。"""
    client, user = authenticated_client
    ticket = await _grant(
        db_session, user.id, "d2",
        equipments=[EquipmentData(equipment_id="wpn_x")],
        items=[ItemData(item_id="mat_a", quantity=5)],
    )

    r1 = await client.post(
        f"/api/inventory/tickets/{ticket.id}/discard", json={"entry_type": "equipment", "index": 0}
    )
    assert r1.status_code == 200
    r2 = await client.post(
        f"/api/inventory/tickets/{ticket.id}/discard", json={"entry_type": "item", "index": 0}
    )
    assert r2.status_code == 200
    assert r2.json()["remaining"]["status"] == "discarded"

    stale_accept = await client.post(f"/api/inventory/tickets/{ticket.id}/accept")
    assert stale_accept.status_code == 409
    assert stale_accept.json()["detail"] == "清单已变更，请刷新"

    stale_discard = await client.post(
        f"/api/inventory/tickets/{ticket.id}/discard", json={"entry_type": "item", "index": 0}
    )
    assert stale_discard.status_code == 409


@pytest.mark.asyncio
async def test_accept_unknown_ticket_404(authenticated_client):
    client, user = authenticated_client
    resp = await client.post("/api/inventory/tickets/99999/accept")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_finalize_endpoint_retired(authenticated_client):
    """旧超载通道 /finalize 已退役（Doc 17 六招之外无路：旁路必须消失）。"""
    client, user = authenticated_client
    resp = await client.post(
        "/api/inventory/finalize",
        json={"add_equipments": [], "add_items": [], "discard_ids": []},
    )
    assert resp.status_code == 404


# ============================================================================
# 常驻入口（spec §5：不点收入也能找到寄存，处理后归零）
# ============================================================================

@pytest.mark.asyncio
async def test_pending_tickets_constant_entry(authenticated_client, db_session):
    client, user = authenticated_client

    ticket = await _grant(
        db_session, user.id, "entry1", equipments=[EquipmentData(equipment_id="wpn_x")]
    )
    status = (await client.get("/api/inventory/status")).json()
    assert status["pending_tickets"] == 1

    resp = await client.post(f"/api/inventory/tickets/{ticket.id}/accept")
    assert resp.status_code == 200
    status = (await client.get("/api/inventory/status")).json()
    assert status["pending_tickets"] == 0


# ============================================================================
# 锁定/解锁（场景 4.7）
# ============================================================================

@pytest.mark.asyncio
async def test_lock_blocks_discard_until_unlock(authenticated_client, db_session):
    client, user = authenticated_client
    equip = UserEquipment(user_id=user.id, equipment_id="wpn_rare")
    db_session.add(equip)
    await db_session.commit()

    resp = await client.post(f"/api/inventory/equipments/{equip.id}/lock")
    assert resp.status_code == 200

    resp = await client.post(f"/api/inventory/equipments/{equip.id}/discard")
    assert resp.status_code == 400
    assert resp.json()["detail"] == "物品已锁定，请先解锁"

    # 锁标随资产清单可见
    bag = (await client.get("/api/inventory/items")).json()
    locked = [e for e in bag["equipments"] if e["id"] == equip.id]
    assert len(locked) == 1 and locked[0]["is_locked"] is True

    resp = await client.post(f"/api/inventory/equipments/{equip.id}/unlock")
    assert resp.status_code == 200

    resp = await client.post(f"/api/inventory/equipments/{equip.id}/discard")
    assert resp.status_code == 200
    bag = (await client.get("/api/inventory/items")).json()
    assert not any(e["id"] == equip.id for e in bag["equipments"])


# ============================================================================
# 材料丢弃与展示名（场景 4.2 / 4.8 / 4.14）
# ============================================================================

@pytest.mark.asyncio
async def test_discard_item_quantity_deduction(authenticated_client, db_session):
    """按数量扣减、归零删行；模板名随条目返回（items.json 有 mat_scrap）。"""
    client, user = authenticated_client
    db_session.add(UserItem(user_id=user.id, item_id="mat_scrap", quantity=10))
    await db_session.commit()

    resp = await client.post("/api/inventory/items/mat_scrap/discard", json={"quantity": 4})
    assert resp.status_code == 200

    bag = (await client.get("/api/inventory/items")).json()
    entry = [i for i in bag["items"] if i["item_id"] == "mat_scrap"][0]
    assert entry["quantity"] == 6
    assert entry["name"] == "废料碎片"

    resp = await client.post("/api/inventory/items/mat_scrap/discard", json={"quantity": 6})
    assert resp.status_code == 200
    bag = (await client.get("/api/inventory/items")).json()
    assert bag["items"] == []


@pytest.mark.asyncio
async def test_material_name_falls_back_to_item_id(authenticated_client, db_session):
    """loot 掉的 item_id 不在 items.json：name 回退 item_id，展示不断链。"""
    client, user = authenticated_client
    db_session.add(UserItem(user_id=user.id, item_id="loot_unknown_id", quantity=1))
    await db_session.commit()

    bag = (await client.get("/api/inventory/items")).json()
    assert bag["items"][0]["name"] == "loot_unknown_id"


# ============================================================================
# 所有权把关（spec §5：别人的家当动不得）
# ============================================================================

@pytest.mark.asyncio
async def test_ownership_cross_user_404(authenticated_client, db_session):
    """A 的 token 动 B 的票据/装备/材料一律 404，B 账目分文不动。"""
    client, user = authenticated_client

    user_b = User(username="inv_other", password_hash=hash_password("pass123"))
    db_session.add(user_b)
    await db_session.flush()

    system = ItemSystem(db_session)
    ticket_b = await system.submit_grant(
        user_b.id, make_receipt_id("debug", "cross1"), "debug",
        equipments=[EquipmentData(equipment_id="wpn_b1")], items=[], credits=77,
    )
    equip_b = UserEquipment(user_id=user_b.id, equipment_id="wpn_b2")
    item_b = UserItem(user_id=user_b.id, item_id="mat_b", quantity=5)
    db_session.add_all([equip_b, item_b])
    await db_session.commit()

    assert (await client.post(f"/api/inventory/tickets/{ticket_b.id}/accept")).status_code == 404
    assert (await client.post(
        f"/api/inventory/tickets/{ticket_b.id}/discard",
        json={"entry_type": "equipment", "index": 0},
    )).status_code == 404
    assert (await client.post(f"/api/inventory/equipments/{equip_b.id}/discard")).status_code == 404
    assert (await client.post(f"/api/inventory/equipments/{equip_b.id}/lock")).status_code == 404
    assert (await client.post(
        "/api/inventory/items/mat_b/discard", json={"quantity": 1}
    )).status_code == 404

    # B 账目不变（列查询直读 DB，绕开本会话 identity map）
    credits_b = (await db_session.execute(
        select(User.credits).where(User.id == user_b.id)
    )).scalar_one()
    assert credits_b == 0
    equip_count_b = (await db_session.execute(
        select(func.count()).select_from(UserEquipment).where(UserEquipment.user_id == user_b.id)
    )).scalar_one()
    assert equip_count_b == 1
    quantity_b = (await db_session.execute(
        select(UserItem.quantity).where(UserItem.user_id == user_b.id)
    )).scalar_one()
    assert quantity_b == 5


# ============================================================================
# debug 发放（走门面票据，Doc 17 §5.5）
# ============================================================================

@pytest.mark.asyncio
async def test_debug_generate_item_success(authenticated_client):
    client, user = authenticated_client
    resp = await client.post(
        "/api/inventory/debug/generate-item", params={"equipment_id": "e_booster"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
    assert "ilvl" in resp.json()["generated_stats"]

    bag = (await client.get("/api/inventory/items")).json()
    assert any(e["equipment_id"] == "e_booster" for e in bag["equipments"])


@pytest.mark.asyncio
async def test_debug_generate_item_deprecated_400(authenticated_client, monkeypatch):
    """deprecated 模板 → 400，发放不再产出停用模板（场景 4.14）。"""
    client, user = authenticated_client
    loader = get_loader()
    monkeypatch.setitem(
        loader.equipments,
        "dep_wpn",
        EquipmentConfig(id="dep_wpn", name="停用件", type="EQUIP", deprecated=True),
    )

    resp = await client.post(
        "/api/inventory/debug/generate-item", params={"equipment_id": "dep_wpn"}
    )
    assert resp.status_code == 400
    assert "停用" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_debug_generate_item_overflow_pends(authenticated_client, db_session):
    """容量满：debug 不再 400，票据留 pending 寄存（常驻入口兜底）。"""
    client, user = authenticated_client
    await _fill_bag(db_session, user.id, 50)

    resp = await client.post(
        "/api/inventory/debug/generate-item", params={"equipment_id": "e_booster"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"

    tickets = (await client.get("/api/inventory/tickets")).json()["tickets"]
    assert len(tickets) == 1 and tickets[0]["source"] == "debug"
