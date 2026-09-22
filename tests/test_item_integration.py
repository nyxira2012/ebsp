"""物品系统主题级集成测试（Doc 17 批4，§5 勾验项服务层版）。

跨层组合验证（直连真实 SQLite + 真实服务栈，不经 HTTP——HTTP 面归属
tests/api 与 tests/user 的单元/接口文件，此处只补主题级集成语义）：

- 新号起步包一步到手与重复领取不重发（场景 4.9 / §5「新号起步包」）
- 模板停用后旧档装备照常显示可用、新发放不再产出（场景 4.14 / §5「旧档不坏」）
- 同票据连点幂等、放行后旧清单丢弃被拒（场景 4.11 / §5「并发排队」）
- 寄存票据掉线重登仍在（场景 4.3 / §5「掉线保护」）
- 所有权交叉（服务层语义；API 层 404 已由 tests/api 覆盖）
- 外部发放台账逐笔对账、玩法内转换不入账（§5「台账可查」）
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.database.models import (
    ExternalGrantLedger,
    ItemTicket,
    User,
    UserEquipment,
    UserItem,
)
from src.models import MothershipConfig
from src.pve.battle_bridge import BattleBridge
from src.user.inventory import InventoryService
from src.user.item_system import ItemSystem, TicketStateError, TicketStatus, make_receipt_id
from src.user.repository import MothershipRepository
from src.user.schemas import EquipmentData, ItemData
from src.user.security import hash_password
from src.user.service import MothershipService, OnboardingService


# ============================================================================
# 基建
# ============================================================================

async def make_user(db_session: AsyncSession, username: str) -> User:
    user = User(username=username, password_hash=hash_password("password123"))
    db_session.add(user)
    await db_session.flush()
    return user


async def all_rows(db_session: AsyncSession, model: type, user_id: int) -> list:
    return list((await db_session.execute(
        select(model).where(model.user_id == user_id)  # type: ignore[attr-defined]
    )).scalars().all())


@pytest.fixture(scope="module")
def real_loader():
    """真实模板库（data/*.json 全量加载一次）：旧档不坏用例按真实配置核对展示字段。"""
    from src import DataLoader

    loader = DataLoader(data_dir="data")
    loader.load_all()
    return loader


@pytest.fixture
def deprecated_template_id(real_loader):
    """把指定装备模板动态标停用，结束还原（测试夹具负责，不改 data/*.json）。"""
    template_id = "e_chobham_armor"
    config = real_loader.equipments[template_id]
    config.deprecated = True
    yield template_id
    config.deprecated = False


# ============================================================================
# 新号起步包（场景 4.9 / §5「新号起步包」）
# ============================================================================

async def test_claim_starter_one_step_all_in(db_session):
    """新号领取：机体 + 编队 + 余额 500 + mat_scrap×5 一次到位，不留 pending。"""
    user = await make_user(db_session, "starter_fresh")
    system = ItemSystem(db_session)

    result = await OnboardingService.claim_starter(db_session, user.id)
    assert result["claimed"] is True
    assert result["mecha"].mech_id == OnboardingService.STARTER_MECHA_ID
    assert result["squad"].mecha_ids == [result["mecha"].id]
    assert result["squad"].is_active is True

    # 三样俱全：机体/编队之外，余额与材料同步到账（场景 4.9 禁止只领到一半）
    assert await system.get_credits(user.id) == OnboardingService.STARTER_CREDITS
    items = await all_rows(db_session, UserItem, user.id)
    assert [(i.item_id, i.quantity) for i in items] == [("mat_scrap", 5)]

    # 台账一行 + 票据 accepted 留档（一步拿到 = 放行完成，不占临时货舱）
    ledgers = await all_rows(db_session, ExternalGrantLedger, user.id)
    assert len(ledgers) == 1
    assert ledgers[0].receipt_id == make_receipt_id("starter", str(user.id))
    assert ledgers[0].source == "starter"
    assert ledgers[0].credits_granted == OnboardingService.STARTER_CREDITS
    tickets = await all_rows(db_session, ItemTicket, user.id)
    assert len(tickets) == 1 and tickets[0].status == TicketStatus.ACCEPTED
    assert await system.count_pending_tickets(user.id) == 0


async def test_claim_starter_repeat_no_double_grant(db_session):
    """同号再点：提示已领取（claimed=False），余额与材料不变、台账/票据不加第二笔。"""
    user = await make_user(db_session, "starter_twice")
    first = await OnboardingService.claim_starter(db_session, user.id)

    second = await OnboardingService.claim_starter(db_session, user.id)
    assert second["claimed"] is False
    assert second["mecha"].id == first["mecha"].id

    assert await ItemSystem(db_session).get_credits(user.id) == OnboardingService.STARTER_CREDITS
    items = await all_rows(db_session, UserItem, user.id)
    assert [(i.item_id, i.quantity) for i in items] == [("mat_scrap", 5)]
    assert len(await all_rows(db_session, ExternalGrantLedger, user.id)) == 1
    assert len(await all_rows(db_session, ItemTicket, user.id)) == 1


# ============================================================================
# 旧档不坏（场景 4.14 / §5「旧档不坏」）
# ============================================================================

async def test_deprecated_template_legacy_assets_intact(
    db_session, real_loader, deprecated_template_id
):
    """模板标停用后：旧档持有的装备行照常可查、按 id 读模板展示字段齐全、
    容量照常计入；新发放（掉落闸）不再产出该模板。"""
    user = await make_user(db_session, "legacy_holder")
    equip = UserEquipment(
        user_id=user.id,
        equipment_id=deprecated_template_id,
        enhancement_level=2,
        random_stats={"final_armor": 5},
    )
    db_session.add(equip)
    await db_session.flush()

    # 装备行仍可查询展示：字段齐全，模板按 id 读取不受停用影响
    row = (await db_session.execute(
        select(UserEquipment).where(UserEquipment.id == equip.id)
    )).scalar_one()
    assert row.equipment_id == deprecated_template_id
    assert row.enhancement_level == 2 and row.random_stats == {"final_armor": 5}
    config = real_loader.get_equipment_config(deprecated_template_id)
    assert config.name and config.type

    # 仍作为既有资产被读到：未装备占 1 格照常计入容量
    status = await InventoryService(db_session, loader=real_loader).get_status(user.id)
    assert status.current == 1

    # 新发放不再产出：掉落闸拦下停用模板
    instance_config = SimpleNamespace(
        loot_tables={
            "z": SimpleNamespace(
                boss_drops=[],
                common_drops=[
                    SimpleNamespace(
                        type="equipment", chance=1.0, equipment_id=deprecated_template_id
                    )
                ],
            )
        },
        zones={"z": SimpleNamespace(drop_rate_mult=1.0)},
    )
    drops = BattleBridge._generate_loot(
        "COMBAT", instance_config, real_loader, "z", base_ilvl=10
    )
    assert drops == []


# ============================================================================
# 并发排队（场景 4.11 / §5「并发排队」，SQLite 语义内可测的版本）
# ============================================================================

async def test_ticket_double_accept_idempotent_and_stale_discard_rejected(db_session):
    """同票据连发两次 accept：第二次幂等「已领取」、台账一行、余额只加一次；
    已放行票据再点丢弃（旧清理画面）→ TicketStateError 提示刷新。"""
    user = await make_user(db_session, "queue_racer")
    system = ItemSystem(db_session)
    t1 = await system.submit_grant(
        user.id, make_receipt_id("pve", "9001"), "pve",
        equipments=[EquipmentData(equipment_id="wpn_a")], items=[], credits=100,
    )
    t2 = await system.submit_grant(
        user.id, make_receipt_id("pve", "9002"), "pve",
        equipments=[EquipmentData(equipment_id="wpn_b")], items=[], credits=200,
    )

    first = await system.accept_ticket(user.id, t1.id)
    second = await system.accept_ticket(user.id, t1.id)
    assert first["already"] is False
    assert second == {"status": "accepted", "already": True}
    assert await system.get_credits(user.id) == 100  # 连点只到账一次
    ledger_receipts = [
        l.receipt_id for l in await all_rows(db_session, ExternalGrantLedger, user.id)
    ]
    assert ledger_receipts == [make_receipt_id("pve", "9001")]  # 台账一行

    # 一端已放行、另一端清理画面还显示旧清单时点丢弃 → 拒绝并提示刷新
    await system.accept_ticket(user.id, t2.id)
    with pytest.raises(TicketStateError):
        await system.discard_ticket_item(user.id, t2.id, "equipment", 0)
    assert await system.get_credits(user.id) == 300


# ============================================================================
# 掉线保护（场景 4.3 / §5「掉线保护」）
# ============================================================================

async def test_pending_ticket_survives_relogin(db_session, async_db_engine):
    """留 pending 票据不处理：全新会话（模拟重登）重查，票据仍在、manifest 原样。"""
    user = await make_user(db_session, "relogin_user")
    system = ItemSystem(db_session)
    ticket = await system.submit_grant(
        user.id, make_receipt_id("pve", "777"), "pve",
        equipments=[EquipmentData(equipment_id="wpn_a")],
        items=[ItemData(item_id="mat_a", quantity=3)],
        credits=77,
    )
    await db_session.commit()  # 掉线 = 会话结束；已提交数据必须落库常驻

    maker = async_sessionmaker(async_db_engine, expire_on_commit=False, autoflush=False)
    async with maker() as fresh_session:
        reloaded = ItemSystem(fresh_session)
        assert await reloaded.count_pending_tickets(user.id) == 1
        view = await reloaded.get_ticket(user.id, ticket.id)
        assert view["status"] == TicketStatus.PENDING
        assert view["credits"] == 77
        assert [e["equipment_id"] for e in view["equipments"]] == ["wpn_a"]
        assert [i["quantity"] for i in view["items"]] == [3]


# ============================================================================
# 所有权把关（§5，服务层版；API 层 404 归 tests/api）
# ============================================================================

async def test_cross_ownership_rejected_service_level(db_session):
    """用 A 的 id 去动 B 的票据/装备：accept/discard/锁定/丢弃全被拒，
    B 的账目逐项不变。"""
    alice = await make_user(db_session, "cross_alice")
    bob = await make_user(db_session, "cross_bob")
    system = ItemSystem(db_session)
    ticket = await system.submit_grant(
        bob.id, make_receipt_id("pve", "bob-1"), "pve",
        equipments=[EquipmentData(equipment_id="wpn_b1")], items=[], credits=50,
    )
    equip = UserEquipment(user_id=bob.id, equipment_id="wpn_b2")
    db_session.add(equip)
    await db_session.flush()

    with pytest.raises(ValueError):
        await system.accept_ticket(alice.id, ticket.id)
    with pytest.raises(ValueError):
        await system.discard_ticket_item(alice.id, ticket.id, "equipment", 0)
    with pytest.raises(ValueError):
        await system.set_lock(alice.id, equip.id, True)
    with pytest.raises(ValueError):
        await system.discard_equipment(alice.id, equip.id)

    # B 的账目逐项不变
    assert await system.get_credits(bob.id) == 0
    assert await system.get_credits(alice.id) == 0
    assert ticket.status == TicketStatus.PENDING
    assert equip.is_locked is False
    assert len(await all_rows(db_session, UserEquipment, bob.id)) == 1
    assert await all_rows(db_session, ExternalGrantLedger, bob.id) == []


# ============================================================================
# 台账可查（§5「台账可查」）
# ============================================================================

@pytest.fixture
def mothership_loader():
    """单艘母舰的模板库（购买环节用；同 tests/user/test_service 的轻量做法）。"""
    from src import DataLoader

    loader = DataLoader()
    loader.motherships = {
        "medium_frigate": MothershipConfig(
            id="medium_frigate", name="中型护卫舰", generation=2, tier="rare",
            engine_level=2, hp_regen_per_min=20, en_regen_per_min=10,
            region_level=2, cargo_capacity=200, emergency_extraction_tax=0.2,
            price=5000,
        )
    }
    return loader


async def test_external_grant_ledger_audit_and_gameplay_conversion_excluded(
    db_session, mothership_loader
):
    """starter + PVE 风格 + debug 风格三笔外部发放：台账品种、数量、时间、
    回执编号逐笔对得上；母舰购买（玩法内转换）不入台账。"""
    user = await make_user(db_session, "ledger_auditor")
    await MothershipRepository.create_default(db_session, user.id)
    system = ItemSystem(db_session)

    # 三笔外部发放：starter（起步包动线）+ pve + debug
    await OnboardingService.claim_starter(db_session, user.id)
    t_pve = await system.submit_grant(
        user.id, make_receipt_id("pve", "9001"), "pve",
        equipments=[EquipmentData(equipment_id="wpn_a")],
        items=[ItemData(item_id="mat_a", quantity=4)],
        credits=120,
    )
    await system.accept_ticket(user.id, t_pve.id)
    t_debug = await system.submit_grant(
        user.id, make_receipt_id("debug", "uuid-1"), "debug",
        equipments=[], items=[ItemData(item_id="mat_b", quantity=2)], credits=0,
    )
    await system.accept_ticket(user.id, t_debug.id)

    ledgers = await all_rows(db_session, ExternalGrantLedger, user.id)
    assert len(ledgers) == 3
    by_receipt = {l.receipt_id: l for l in ledgers}

    starter = by_receipt[make_receipt_id("starter", str(user.id))]
    assert starter.source == "starter"
    assert starter.credits_granted == OnboardingService.STARTER_CREDITS
    assert starter.manifest["items"] == [
        {"item_id": "mat_scrap", "item_type": "material", "quantity": 5}
    ]

    pve = by_receipt[make_receipt_id("pve", "9001")]
    assert pve.source == "pve" and pve.credits_granted == 120
    assert pve.manifest["equipments"][0]["equipment_id"] == "wpn_a"
    assert pve.manifest["items"] == [{"item_id": "mat_a", "item_type": "material", "quantity": 4}]

    debug = by_receipt[make_receipt_id("debug", "uuid-1")]
    assert debug.source == "debug" and debug.credits_granted == 0
    assert debug.manifest["items"][0]["quantity"] == 2

    # 时间逐笔留痕（品种、数量、时间、回执编号缺一不可）
    assert all(l.created_at is not None for l in ledgers)

    # 母舰购买 = 玩法内转换：不入台账（行数不变），余额正常扣减
    user.credits = 20000
    updated = await MothershipService.purchase_mothership(
        db_session, user, "medium_frigate", mothership_loader
    )
    assert "medium_frigate" in updated.data["owned_ids"]
    assert user.credits == 15000
    assert len(await all_rows(db_session, ExternalGrantLedger, user.id)) == 3
