"""PVE 结算票据化测试（Doc 17 批2）。

覆盖：通关撤离建 pending 票据且未直接入包（场景 4.1/4.12）、同回执重复
finalize 幂等返回同一票据（场景 4.4/4.12）、战败全空无票据但结算收尾完
成、紧急撤离税率折损反映进票据 manifest、清单不符 rejected 留档且会话保
留（场景 4.10），以及 battle_bridge 掉落闸跳过 deprecated 模板（场景 4.14）。

真实内存 SQLite（conftest db_session）+ 真实 ItemSystem + 数据库预置用户；
模板库用轻量 StubLoader（同 test_item_system 的测试缝隙）。
"""

import pytest
from types import SimpleNamespace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import ItemTicket, PveSession, User, UserEquipment, UserItem
from src.models import EquipmentConfig
from src.pve.battle_bridge import BattleBridge
from src.pve.enums import ExitMethod, EventType
from src.pve.models import (
    EventSequence, PveEntityState, PveEvent, PveSessionData, PveSquadState,
)
from src.pve.reward_controller import RewardController
from src.user.item_system import (
    GrantManifestMismatchError, ItemSystem, TicketStatus, make_receipt_id,
)
from src.user.security import hash_password


class StubLoader:
    """轻量模板库：equipments 供清单校验，affixes 供掉落掷骰（空=无词条）。"""

    affixes = {}

    def __init__(self) -> None:
        self.equipments = {
            "beam_rifle": EquipmentConfig(id="beam_rifle", name="光束步枪", type="WEAPON"),
            "old_scope": EquipmentConfig(
                id="old_scope", name="旧瞄准镜", type="EQUIP", deprecated=True
            ),
        }

    def get_equipment_config(self, equipment_id: str) -> EquipmentConfig:
        return self.equipments[equipment_id]

    def get_region_config(self, region_id: str) -> SimpleNamespace:
        # 无后续解锁节点，mark_zone_cleared 只标记 cleared
        return SimpleNamespace(zones=[])


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    """预置数据库用户（余额 0——票据未放行前不得有任何到账）"""
    u = User(username="pve_tester", password_hash=hash_password("password123"))
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.fixture
def loader() -> StubLoader:
    return StubLoader()


def make_session_data(session_id: int, user_id: int) -> PveSessionData:
    """构造已打完 BOSS 的会话数据（老用例同款形状）"""
    members = [
        PveEntityState(
            entity_id="rx78", current_hp=1000, current_en=100,
            max_hp=1000, max_en=100, last_combat_time=0,
        )
    ]
    return PveSessionData(
        session_id=session_id,
        user_id=user_id,
        region_id="r1",
        zone_id="test_zone",
        event_sequence=EventSequence(
            events=[
                PveEvent(index=0, event_type=EventType.COMBAT),
                PveEvent(index=1, event_type=EventType.BOSS_COMBAT, event_id="boss_1", cleared=True),
            ],
            current_index=2,
        ),
        squad_state=PveSquadState(members=members, locked_config={}),
        created_at=0,
        last_heartbeat=0,
    )


async def seed_pve_session(db_session: AsyncSession, session_id: int, user_id: int) -> None:
    """预置断线保护会话行（finalize 成功路径应删除它）"""
    db_session.add(PveSession(
        id=session_id, user_id=user_id, region_id="r1", zone_id="test_zone"
    ))
    await db_session.flush()


async def run_finalize(
    db_session: AsyncSession,
    user: User,
    session_data: PveSessionData,
    exit_method: ExitMethod,
    loader: StubLoader,
) -> dict:
    system = ItemSystem(db_session, loader=loader)
    return await RewardController.finalize(
        db=db_session,
        session_data=session_data,
        exit_method=exit_method,
        item_system=system,
        mothership_config=SimpleNamespace(emergency_extraction_tax=0.5),
        loader=loader,
    )


async def user_asset_counts(db_session: AsyncSession, user_id: int) -> tuple[int, int]:
    equips = (await db_session.execute(
        select(UserEquipment).where(UserEquipment.user_id == user_id)
    )).scalars().all()
    items = (await db_session.execute(
        select(UserItem).where(UserItem.user_id == user_id)
    )).scalars().all()
    return len(equips), len(items)


async def pve_session_exists(db_session: AsyncSession, session_id: int) -> bool:
    row = (await db_session.execute(
        select(PveSession).where(PveSession.id == session_id)
    )).scalar_one_or_none()
    return row is not None


# ============================================================================
# 撤离结算 → 票据
# ============================================================================

@pytest.mark.asyncio
async def test_finalize_boss_clear_creates_pending_ticket(db_session, user, loader):
    """通关撤离：建 pending 票据（summary 带 ticket_id），不当场入包（场景 4.1/4.12）"""
    session_data = make_session_data(999, user.id)
    RewardController.add_pending_loot(session_data, [
        {"type": "equipment", "equipment_id": "beam_rifle", "enhancement_level": 2},
        {"type": "item", "item_id": "iron", "quantity": 10},
    ])
    session_data.credits_earned = 300
    await seed_pve_session(db_session, 999, user.id)

    summary = await run_finalize(db_session, user, session_data, ExitMethod.BOSS_CLEAR, loader)

    # 票据已建，等玩家点「收入货舱」而非直接入包
    assert summary["ticket_id"] is not None
    assert summary["ticket_status"] == TicketStatus.PENDING
    assert summary["credits"] == 300
    assert summary["final_equips"] == 1
    assert summary["final_items"] == 1
    equips, items = await user_asset_counts(db_session, user.id)
    assert (equips, items) == (0, 0)
    assert user.credits == 0

    # 票据 manifest 绑定本批清单；断线保护会话行已删（结算收尾完成）
    ticket = (await db_session.execute(
        select(ItemTicket).where(ItemTicket.id == summary["ticket_id"])
    )).scalar_one()
    assert ticket.receipt_id == make_receipt_id("pve", "999")
    assert ticket.manifest["credits"] == 300
    assert len(ticket.manifest["equipments"]) == 1
    assert ticket.manifest["items"][0]["item_id"] == "iron"
    assert not await pve_session_exists(db_session, 999)


@pytest.mark.asyncio
async def test_finalize_replay_returns_same_ticket(db_session, user, loader):
    """同回执重复 finalize：返回同一票据，不重复发放（场景 4.4/4.12）"""
    session_data = make_session_data(888, user.id)
    RewardController.add_pending_loot(session_data, [
        {"type": "equipment", "equipment_id": "beam_rifle"},
    ])
    await seed_pve_session(db_session, 888, user.id)

    first = await run_finalize(db_session, user, session_data, ExitMethod.BOSS_CLEAR, loader)
    second = await run_finalize(db_session, user, session_data, ExitMethod.BOSS_CLEAR, loader)

    assert second["ticket_id"] == first["ticket_id"]
    tickets = (await db_session.execute(
        select(ItemTicket).where(ItemTicket.user_id == user.id)
    )).scalars().all()
    assert len(tickets) == 1
    assert second["final_equips"] == 1  # 从既有票据重建，不是二次折算的结果


@pytest.mark.asyncio
async def test_finalize_defeated_no_ticket_but_settled(db_session, user, loader):
    """战败全空：不建票据（ticket_id=None），但进度收尾与会话删除照常完成"""
    session_data = make_session_data(777, user.id)
    RewardController.add_pending_loot(session_data, [
        {"type": "equipment", "equipment_id": "beam_rifle"},
        {"type": "item", "item_id": "iron", "quantity": 5},
    ])
    session_data.credits_earned = 0
    await seed_pve_session(db_session, 777, user.id)

    summary = await run_finalize(db_session, user, session_data, ExitMethod.DEFEATED, loader)

    assert summary["ticket_id"] is None
    assert summary["ticket_status"] is None
    assert summary["credits"] == 0
    assert summary["original_equips"] == 1
    assert summary["final_equips"] == 0
    tickets = (await db_session.execute(
        select(ItemTicket).where(ItemTicket.user_id == user.id)
    )).scalars().all()
    assert tickets == []
    assert not await pve_session_exists(db_session, 777)


@pytest.mark.asyncio
async def test_finalize_emergency_exit_applies_tax(db_session, user, loader):
    """紧急撤离：税率切分折损反映进票据 manifest（母舰税率 0.5）"""
    session_data = make_session_data(666, user.id)
    RewardController.add_pending_loot(session_data, [
        {"type": "item", "item_id": "a"},
        {"type": "item", "item_id": "b"},
        {"type": "item", "item_id": "c"},
        {"type": "item", "item_id": "d"},
    ])
    session_data.credits_earned = 100
    await seed_pve_session(db_session, 666, user.id)

    summary = await run_finalize(db_session, user, session_data, ExitMethod.EMERGENCY_EXIT, loader)

    assert summary["original_items"] == 4
    assert summary["final_items"] == 2
    assert summary["ticket_status"] == TicketStatus.PENDING
    ticket = (await db_session.execute(
        select(ItemTicket).where(ItemTicket.id == summary["ticket_id"])
    )).scalar_one()
    assert len(ticket.manifest["items"]) == 2
    assert ticket.manifest["credits"] == 100


@pytest.mark.asyncio
async def test_finalize_manifest_mismatch_rejects_and_keeps_session(db_session, user, loader):
    """清单不符（未知模板）：rejected 留档 + 异常上抛 + 会话未删（场景 4.10）"""
    session_data = make_session_data(555, user.id)
    RewardController.add_pending_loot(session_data, [
        {"type": "equipment", "equipment_id": "wpn_ghost"},
    ])
    await seed_pve_session(db_session, 555, user.id)

    with pytest.raises(GrantManifestMismatchError):
        await run_finalize(db_session, user, session_data, ExitMethod.BOSS_CLEAR, loader)

    # rejected 票据留档（不占 pending、不占回执幂等位、不入包），没入包的
    # 东西不会凭空消失
    tickets = (await db_session.execute(
        select(ItemTicket).where(ItemTicket.receipt_id == make_receipt_id("pve", "555"))
    )).scalars().all()
    assert len(tickets) == 1
    assert tickets[0].status == TicketStatus.REJECTED
    assert tickets[0].manifest["equipments"][0]["equipment_id"] == "wpn_ghost"

    # finalize 中止：断线保护会话行未被删除，本批可待数据修复后重新结算
    assert await pve_session_exists(db_session, 555)
    equips, items = await user_asset_counts(db_session, user.id)
    assert (equips, items) == (0, 0)


@pytest.mark.asyncio
async def test_finalize_rejected_ticket_does_not_block_resubmission(db_session, user, loader):
    """rejected 不占回执幂等位：数据修复后同回执重结算重新成票（场景 4.10）

    若幂等短路不判 status，mismatch 400 后的重结算会拿 rejected 票据当
    "已发过" 直接 200+删会话——批次永久丢失，与「可待数据修复后重新
    结算」承诺相反。
    """
    session_data = make_session_data(444, user.id)
    RewardController.add_pending_loot(session_data, [
        {"type": "equipment", "equipment_id": "wpn_ghost"},
    ])
    await seed_pve_session(db_session, 444, user.id)

    with pytest.raises(GrantManifestMismatchError):
        await run_finalize(db_session, user, session_data, ExitMethod.BOSS_CLEAR, loader)

    # 修复数据源：掉落物换成存在的模板，同回执重结算
    session_data.pending_rewards.equipments.clear()
    RewardController.add_pending_loot(session_data, [
        {"type": "equipment", "equipment_id": "beam_rifle"},
    ])
    summary = await run_finalize(db_session, user, session_data, ExitMethod.BOSS_CLEAR, loader)

    # rejected 留档被原地置换为 pending，不另开新回执
    assert summary["ticket_status"] == TicketStatus.PENDING
    tickets = (await db_session.execute(
        select(ItemTicket).where(ItemTicket.receipt_id == make_receipt_id("pve", "444"))
    )).scalars().all()
    assert len(tickets) == 1
    assert tickets[0].status == TicketStatus.PENDING
    assert tickets[0].manifest["equipments"][0]["equipment_id"] == "beam_rifle"
    assert not await pve_session_exists(db_session, 444)  # 重结算走完收尾


# ============================================================================
# 掉落闸：deprecated 模板不再产出（场景 4.14）
# ============================================================================

def test_generate_loot_skips_deprecated_template(loader):
    """停用模板不产出：新掉落被闸拦下，活跃模板照常掉落"""
    instance_config = SimpleNamespace(
        loot_tables={
            "z1": SimpleNamespace(
                boss_drops=[],
                common_drops=[
                    SimpleNamespace(type="equipment", chance=1.0, equipment_id="beam_rifle"),
                    SimpleNamespace(type="equipment", chance=1.0, equipment_id="old_scope"),
                ],
            )
        },
        zones={"z1": SimpleNamespace(drop_rate_mult=1.0)},
    )

    drops = BattleBridge._generate_loot("COMBAT", instance_config, loader, "z1", base_ilvl=10)

    dropped_ids = [d["equipment_id"] for d in drops]
    assert "beam_rifle" in dropped_ids
    assert "old_scope" not in dropped_ids
