import pytest
from unittest.mock import AsyncMock, Mock
from typing import List, Dict, Any

from src.pve.reward_controller import RewardController
from src.pve.models import PveSessionData, PveSquadState, PveEntityState, EventSequence, PveEvent
from src.pve.enums import SessionStatus, ExitMethod, EventType
from src.user.schemas import AddResult

# 造一个包含 async db 的假 mock
class MockAsyncSession:
    def __init__(self):
        self.executed = []
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.flushed = False

    async def execute(self, stmt):
        self.executed.append(stmt)
        m = Mock()
        m.scalar_one_or_none.return_value = None # 模拟没领取过
        return m

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

@pytest.mark.asyncio
async def test_reward_controller_finalize_success():
    """测试完整流程：Boss Clear 全量获取"""

    # 构造虚假 SessionData
    members = [
        PveEntityState(
            entity_id="rx78", current_hp=1000, current_en=100, max_hp=1000, max_en=100, last_combat_time=0
        )
    ]
    squad_state = PveSquadState(members=members, locked_config={})

    # 创建事件序列替代地图
    event_sequence = EventSequence(
        events=[
            PveEvent(index=0, event_type=EventType.COMBAT),
            PveEvent(index=1, event_type=EventType.BOSS_COMBAT, event_id="boss_1", cleared=True)
        ],
        current_index=2
    )

    session_data = PveSessionData(
        session_id=999,
        user_id=1,
        region_id="r1",
        current_layer=1,
        status=SessionStatus.ACTIVE,
        event_sequence=event_sequence,
        squad_state=squad_state,
        created_at=0,
        last_heartbeat=0
    )

    # 模拟给 session 加入 pending loot
    RewardController.add_pending_loot(session_data, [
        {"type": "equipment", "equipment_id": "beam_rifle", "enhancement_level": 2},
        {"type": "item", "item_id": "iron", "quantity": 10}
    ])

    # mock
    db = MockAsyncSession()
    mock_inv_service = AsyncMock()
    v = Mock()
    v.value = AddResult.SUCCESS.value
    mock_inv_service.add_assets.return_value = v
    mock_mothership_config = Mock()
    mock_mothership_config.emergency_extraction_tax = 0.5

    # 执行提现
    summary = await RewardController.finalize(
        db=db,
        session_data=session_data,
        exit_method=ExitMethod.BOSS_CLEAR,
        inventory_service=mock_inv_service,
        mothership_config=mock_mothership_config
    )

    # 验证
    # add_assets 应该被调用（1个装备，1个材料）
    assert mock_inv_service.add_assets.call_count == 1
    args = mock_inv_service.add_assets.call_args[0] # args = (user_id, equip_dtos, item_dtos)
    assert args[0] == 1
    assert len(args[1]) == 1 # equip_dtos
    assert len(args[2]) == 1 # item_dtos

    # 验证 ledger 写入
    assert len(db.added) == 1
    assert db.added[0].session_id == 999
    assert db.added[0].user_id == 1

    # 验证删除
    assert len(db.executed) == 2 # 1个 select, 1个 delete

    assert summary["exit_method"] == "BOSS_CLEAR"
    assert summary["final_equips"] == 1
    assert summary["final_items"] == 1

@pytest.mark.asyncio
async def test_reward_controller_emergency_tax():
    """测试紧急撤离的税率扣除"""

    members = [
        PveEntityState(
            entity_id="rx78", current_hp=1000, current_en=100, max_hp=1000, max_en=100, last_combat_time=0
        )
    ]
    squad_state = PveSquadState(members=members, locked_config={})

    event_sequence = EventSequence(events=[])

    session_data = PveSessionData(
        session_id=888,
        user_id=1,
        region_id="r1",
        event_sequence=event_sequence,
        squad_state=squad_state,
        created_at=0,
        last_heartbeat=0
    )

    # 加 4 个物料，如果税率是 0.5，最后应该只剩下 2 个
    RewardController.add_pending_loot(session_data, [
        {"type": "item", "item_id": "a"},
        {"type": "item", "item_id": "b"},
        {"type": "item", "item_id": "c"},
        {"type": "item", "item_id": "d"}
    ])

    db = MockAsyncSession()
    mock_inv_service = AsyncMock()
    v = Mock()
    v.value = AddResult.SUCCESS.value
    mock_inv_service.add_assets.return_value = v
    mock_mothership_config = Mock()
    mock_mothership_config.emergency_extraction_tax = 0.5

    summary = await RewardController.finalize(
        db=db,
        session_data=session_data,
        exit_method=ExitMethod.EMERGENCY_EXIT,
        inventory_service=mock_inv_service,
        mothership_config=mock_mothership_config
    )

    assert summary["original_items"] == 4
    assert summary["final_items"] == 2 # 4 * (1 - 0.5)

@pytest.mark.asyncio
async def test_reward_controller_defeated():
    """测试战败血本无归"""

    members = [
        PveEntityState(
            entity_id="rx78", current_hp=1000, current_en=100, max_hp=1000, max_en=100, last_combat_time=0
        )
    ]
    squad_state = PveSquadState(members=members, locked_config={})
    event_sequence = EventSequence(events=[])
    session_data = PveSessionData(session_id=777, user_id=1, region_id="r1", event_sequence=event_sequence, squad_state=squad_state, created_at=0, last_heartbeat=0)

    RewardController.add_pending_loot(session_data, [
        {"type": "equipment", "equipment_id": "beam_rifle"}
    ])

    db = MockAsyncSession()
    mock_inv_service = AsyncMock()

    summary = await RewardController.finalize(
        db=db,
        session_data=session_data,
        exit_method=ExitMethod.DEFEATED,
        inventory_service=mock_inv_service,
        mothership_config=None
    )

    assert summary["original_equips"] == 1
    assert summary["final_equips"] == 0
    # 没有获得任何材料，add_assets 不应该被调用
    assert mock_inv_service.add_assets.call_count == 0
