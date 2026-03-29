"""PVE Repository 层测试

测试 PVE 仓储层的数据库操作：
1. PveRepository.get_by_user() - 查询用户会话
2. PveRepository.save_or_update() - 保存会话数据
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.pve.repository import PveRepository
from src.pve.models import PveSessionData, PveSquadState, PveEntityState, PvePendingRewards, EventSequence, PveEvent
from src.pve.enums import SessionStatus, EventType
from src.database.models import PveSession
import time


@pytest.fixture
async def sample_session_data():
    """创建示例会话数据"""
    # 使用事件序列替代地图
    event_sequence = EventSequence(
        events=[
            PveEvent(index=0, event_type=EventType.COMBAT, cleared=True),
            PveEvent(index=1, event_type=EventType.LOOT, cleared=True),
            PveEvent(index=2, event_type=EventType.BOSS_COMBAT, event_id="boss_1")
        ],
        current_index=2
    )

    members = [
        PveEntityState(
            entity_id="rx78",
            current_hp=5000,
            current_en=100,
            max_hp=5000,
            max_en=100,
            last_combat_time=time.time(),
            is_alive=True
        )
    ]
    squad_state = PveSquadState(members=members, locked_config={})

    return PveSessionData(
        session_id=1,
        user_id=1,
        region_id="test_region",
        zone_id="test_zone",
        status=SessionStatus.ACTIVE,
        event_sequence=event_sequence,
        squad_state=squad_state,
        pending_rewards=PvePendingRewards(equipments=[], items=[]),
        credits_earned=0,
        created_at=time.time(),
        last_heartbeat=time.time()
    )


# ============================================================================
# PveRepository.get_by_user() 测试
# ============================================================================

@pytest.mark.asyncio
async def test_get_by_user_with_active_session(db_session: AsyncSession, sample_session_data):
    """测试查询有活跃会话的用户"""
    # 先创建一个会话记录
    rec = PveSession(
        user_id=1,
        status="active",
        region_id="test_region",
        zone_id="test_zone",
        session_data=sample_session_data.model_dump(),
        idempotency_key="pve_1_1"
    )
    db_session.add(rec)
    await db_session.flush()

    # 查询
    stmt = PveRepository.get_by_user(db_session, user_id=1)
    result = await db_session.execute(stmt)
    sessions = result.scalars().all()

    assert len(sessions) == 1
    assert sessions[0].user_id == 1
    assert sessions[0].status == "active"


@pytest.mark.asyncio
async def test_get_by_user_with_paused_session(db_session: AsyncSession, sample_session_data):
    """测试查询有暂停会话的用户"""
    rec = PveSession(
        user_id=1,
        status="paused",
        region_id="test_region",
        zone_id="test_zone",
        session_data=sample_session_data.model_dump(),
        idempotency_key="pve_1_2"
    )
    db_session.add(rec)
    await db_session.flush()

    stmt = PveRepository.get_by_user(db_session, user_id=1)
    result = await db_session.execute(stmt)
    sessions = result.scalars().all()

    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_get_by_user_no_session(db_session: AsyncSession):
    """测试查询无会话的用户"""
    stmt = PveRepository.get_by_user(db_session, user_id=999)
    result = await db_session.execute(stmt)
    sessions = result.scalars().all()

    assert len(sessions) == 0


@pytest.mark.asyncio
async def test_get_by_user_ignores_completed_status(db_session: AsyncSession, sample_session_data):
    """测试查询时忽略已完成的会话"""
    # 创建一个已完成的会话
    rec = PveSession(
        user_id=1,
        status="completed",  # 不在 active/paused 中
        region_id="test_region",
        zone_id="test_zone",
        session_data=sample_session_data.model_dump(),
        idempotency_key="pve_1_3"
    )
    db_session.add(rec)
    await db_session.flush()

    stmt = PveRepository.get_by_user(db_session, user_id=1)
    result = await db_session.execute(stmt)
    sessions = result.scalars().all()

    # 应该返回空，因为 completed 状态被过滤
    assert len(sessions) == 0


@pytest.mark.asyncio
async def test_get_by_user_multiple_sessions(db_session: AsyncSession, sample_session_data):
    """测试用户有多个会话的情况"""
    # 创建多个会话
    for i in range(3):
        rec = PveSession(
            user_id=1,
            status="active" if i < 2 else "paused",
            region_id=f"region_{i}",
            zone_id="test_zone",
            session_data=sample_session_data.model_dump(),
            idempotency_key=f"pve_1_{i+10}"
        )
        db_session.add(rec)
    await db_session.flush()

    stmt = PveRepository.get_by_user(db_session, user_id=1)
    result = await db_session.execute(stmt)
    sessions = result.scalars().all()

    # 应该返回所有 active 和 paused 的会话
    assert len(sessions) == 3


# ============================================================================
# PveRepository.save_or_update() 测试
# ============================================================================

@pytest.mark.asyncio
async def test_save_or_update_creates_record(db_session: AsyncSession, sample_session_data):
    """测试创建新会话记录"""
    PveRepository.save_or_update(db_session, sample_session_data)
    await db_session.flush()

    # 验证记录已创建
    stmt = select(PveSession).where(PveSession.user_id == 1)
    result = await db_session.execute(stmt)
    rec = result.scalar_one()

    assert rec is not None
    assert rec.user_id == 1
    assert rec.region_id == "test_region"
    assert rec.status == "active"
    assert rec.idempotency_key == "pve_1_1"
    assert rec.session_data is not None


@pytest.mark.asyncio
async def test_save_or_update_serializes_data(db_session: AsyncSession, sample_session_data):
    """测试数据正确序列化"""
    PveRepository.save_or_update(db_session, sample_session_data)
    await db_session.flush()

    stmt = select(PveSession).where(PveSession.user_id == 1)
    result = await db_session.execute(stmt)
    rec = result.scalar_one()

    # 验证序列化后的数据
    assert rec.session_data["user_id"] == 1
    assert rec.session_data["region_id"] == "test_region"
    assert rec.session_data["session_id"] == 1
    assert "squad_state" in rec.session_data


@pytest.mark.asyncio
async def test_save_or_update_with_different_status(db_session: AsyncSession):
    """测试保存不同状态的会话"""
    event_sequence = EventSequence(events=[])

    members = [PveEntityState(
        entity_id="test", current_hp=100, current_en=50,
        max_hp=100, max_en=50, last_combat_time=time.time(), is_alive=True
    )]
    squad = PveSquadState(members=members, locked_config={})

    # 使用不同的 session_id 避免幂等键冲突
    for idx, status in enumerate([SessionStatus.ACTIVE, SessionStatus.PAUSED]):
        session_data = PveSessionData(
            session_id=100 + idx,  # 不同的 session_id
            user_id=2,
            region_id="test",
            zone_id=f"test_zone_{idx}",
            status=status,
            event_sequence=event_sequence,
            squad_state=squad,
            pending_rewards=PvePendingRewards(equipments=[], items=[]),
            credits_earned=0,
            created_at=time.time(),
            last_heartbeat=time.time()
        )

        PveRepository.save_or_update(db_session, session_data)

    await db_session.flush()

    # 验证两条记录都保存成功
    stmt = select(PveSession).where(PveSession.user_id == 2)
    result = await db_session.execute(stmt)
    recs = result.scalars().all()

    assert len(recs) == 2
    statuses = {r.status for r in recs}
    assert statuses == {"active", "paused"}


@pytest.mark.asyncio
async def test_save_or_update_generates_idempotency_key(db_session: AsyncSession, sample_session_data):
    """测试正确生成幂等键"""
    PveRepository.save_or_update(db_session, sample_session_data)
    await db_session.flush()

    stmt = select(PveSession).where(PveSession.user_id == 1)
    result = await db_session.execute(stmt)
    rec = result.scalar_one()

    assert rec.idempotency_key == "pve_1_1"


@pytest.mark.asyncio
async def test_save_or_update_multiple_users(db_session: AsyncSession):
    """测试保存多个用户的会话"""
    for user_id in [1, 2, 3]:
        event_sequence = EventSequence(events=[])

        members = [PveEntityState(
            entity_id=f"mecha_{user_id}", current_hp=100, current_en=50,
            max_hp=100, max_en=50, last_combat_time=time.time(), is_alive=True
        )]
        squad = PveSquadState(members=members, locked_config={})

        session_data = PveSessionData(
            session_id=user_id * 100,
            user_id=user_id,
            region_id=f"region_{user_id}",
            zone_id=f"zone_{user_id}",
            status=SessionStatus.ACTIVE,
            event_sequence=event_sequence,
            squad_state=squad,
            pending_rewards=PvePendingRewards(equipments=[], items=[]),
            credits_earned=0,
            created_at=time.time(),
            last_heartbeat=time.time()
        )

        PveRepository.save_or_update(db_session, session_data)

    await db_session.flush()

    # 验证所有用户的会话都保存成功
    stmt = select(PveSession)
    result = await db_session.execute(stmt)
    recs = result.scalars().all()

    assert len(recs) == 3
    user_ids = {r.user_id for r in recs}
    assert user_ids == {1, 2, 3}
