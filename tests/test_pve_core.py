import time
from unittest.mock import Mock

from src.pve.enums import SessionStatus, EventType, CombatOutcome
from src.pve.models import PveEntityState, PveSquadState, EventSequence, PveEvent
from src.pve.session_manager import PveSessionManager
from src.pve.battle_bridge import BattleBridge


def _make_basic_session(user_id: int = 1, region_id: str = "test_region") -> "src.pve.models.PveSessionData":
    """辅助函数：快速创建一个带有固定事件序列的会话（不调用随机生成器）"""
    from src.pve.models import PveSessionData

    # 手动构建事件序列：空地 -> 普通战斗 -> 精英战斗 -> Boss
    events = [
        PveEvent(index=0, event_type=EventType.LOOT, event_id="random_chest"),
        PveEvent(index=1, event_type=EventType.COMBAT, event_id="mob_1"),
        PveEvent(index=2, event_type=EventType.ELITE_COMBAT, event_id="elite_1"),
        PveEvent(index=3, event_type=EventType.BOSS_COMBAT, event_id="station_guardian"),
    ]
    sequence = EventSequence(events=events, current_index=0)

    members = [
        PveEntityState(
            entity_id="rx78",
            current_hp=1000, current_en=100,
            max_hp=1000, max_en=100,
            last_combat_time=time.time(), is_alive=True
        )
    ]
    locked_config = {"mechas": [{"mecha_id": "rx78", "max_hp": 1000, "max_en": 100}]}
    squad_state = PveSquadState(members=members, locked_config=locked_config)

    session = PveSessionData(
        session_id=999,
        user_id=user_id,
        region_id=region_id,
        zone_id="test_zone",
        current_layer=1,
        status=SessionStatus.ACTIVE,
        event_sequence=sequence,
        squad_state=squad_state,
        created_at=time.time(),
        last_heartbeat=time.time()
    )
    PveSessionManager._sessions[session.session_id] = session
    return session


def test_pve_event_sequence_structure():
    """测试事件序列基本结构 P0 级"""
    session = _make_basic_session()
    seq = session.event_sequence

    assert seq.total_events == 4
    assert seq.current_index == 0

    # 当前事件是 LOOT
    current = seq.current_event()
    assert current is not None
    assert current.event_type == EventType.LOOT

    # 末尾事件必须是 BOSS
    last = seq.events[-1]
    assert last.event_type == EventType.BOSS_COMBAT

    # 清理
    PveSessionManager.destroy_session(session.session_id)


def test_pve_event_sequence_advance():
    """测试事件序列线性推进逻辑"""
    session = _make_basic_session()
    seq = session.event_sequence

    # 初始在 0
    assert seq.current_index == 0

    # 推进 1 步 -> 到索引 1 (COMBAT)
    has_more = seq.advance()
    assert has_more is True
    assert seq.current_index == 1
    assert seq.current_event().event_type == EventType.COMBAT

    # 推进到末位 Boss
    seq.advance()
    seq.advance()
    assert seq.current_index == 3
    assert seq.current_event().event_type == EventType.BOSS_COMBAT

    # 推进超出
    has_more = seq.advance()
    assert has_more is False
    assert seq.is_complete() is True

    PveSessionManager.destroy_session(session.session_id)


def test_pve_battle_bridge_engage():
    """测试 BattleBridge 战斗触发（使用 Mock 战斗引擎）"""
    session = _make_basic_session()

    mothership_config = Mock()
    mothership_config.hp_regen_per_min = 10
    mothership_config.en_regen_per_min = 5

    mock_loader = Mock()
    mock_loader.equipments = {}

    mock_factory = Mock()

    class MockSnapshot:
        current_hp = 1000
        current_en = 100
        max_hp = 1000
        max_en = 100
        final_max_hp = 1000
        final_max_en = 100
        name = "MockMecha"
        weapons = []
        pilot_stats_backup = {}
        final_mobility = 100
        final_en_regen_rate = 5
        final_en_regen_fixed = 0
        current_will = 100
        shield_capacity = 0

        def is_alive(self): return self.current_hp > 0
        def get_hp_percentage(self): return self.current_hp / self.final_max_hp * 100
        def can_attack(self, weapon): return True
        def modify_will(self, val): pass
        def consume_en(self, val): pass

    mock_factory.create_mecha_snapshot.return_value = MockSnapshot()

    # 对事件索引 1（COMBAT: mob_1）发起战斗
    with __import__("unittest").mock.patch("src.pve.battle_bridge.BattleSimulator") as MockSimCls:
        mock_sim_inst = Mock()
        mock_sim_inst.get_result.return_value = {
            "outcome": "a_wins",
            "rounds": 2,
            "mecha_a": {"hp": 800, "en": 50, "alive": True},
            "mecha_b": {"hp": 0, "en": 0, "alive": False}
        }
        MockSimCls.return_value = mock_sim_inst

        battle_res = BattleBridge.engage(
            session=session,
            event_index=1,   # 对序列中第 1 个战斗事件发起战斗
            loader=mock_loader,
            mothership_config=mothership_config,
            mecha_factory=mock_factory
        )

    assert battle_res.outcome == CombatOutcome.WIN
    assert battle_res.credits_earned == 100

    # 玩家状态已更新
    p_state = session.squad_state.members[0]
    assert p_state.current_hp == 800
    assert p_state.current_en == 50
    assert p_state.is_alive is True

    # 事件已被标记为已清除
    assert session.event_sequence.events[1].cleared is True

    PveSessionManager.destroy_session(session.session_id)

def test_pve_advance_and_engage_schemas():
    """测试 API 层的基本 Request/Response 结构适应性"""
    from src.pve.schemas import AdvanceRequest, AdvanceResponse, EventInfo
    from src.pve.enums import EventType
    
    # 模拟构建对象以验证 Pydantic Schema
    req = AdvanceRequest(expected_index=0)
    assert req is not None
    
    resp = AdvanceResponse(
        new_event_index=1,
        current_event=EventInfo(
            index=1,
            event_type=EventType.COMBAT.value,
            event_id="enemy_1",
            cleared=False
        ),
        sequence_complete=False
    )
    assert resp.new_event_index == 1
    assert resp.current_event.event_type == "COMBAT"
