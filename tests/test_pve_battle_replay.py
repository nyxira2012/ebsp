"""
PVE 接敌并入时间轴 + 战报暂存与重放（Doc 15 §6/§7 P1-b，Doc 14 §9.5）。

覆盖：
- BattleBridge.engage 裁定成功 → 完整战报（Doc 14 四块结构，
  meta.route=="pve"）以单次 dump 暂存到 session.battle_reports
  （战报唯一去向=会话暂存，命令与资源分离）；
- engage 响应瘦身为终局摘要（不含 battle_report 键），战报经
  GET /api/pve/sessions/{id}/battle/{event_index} 取用（战报唯一出口）；
- advance 推进后旧事件点暂存被清理、新事件点接敌不受影响
  （Doc 15 §6"下一次推进即消化完成"）；
- 重放端点：200 与会话暂存逐字一致、未接敌事件点 404、
  他人会话 404、会话不存在 404（前端降级仅终局摘要）；
- 失败原子的 battle_reports 零写入断言并入 tests/test_battle_entry.py。

进程重启丢失（内存态天然失效）不做测试——裁决 #3：内存态即用即弃。
"""

import time
from unittest.mock import Mock

import pytest

from src.database.models import User
from src.pve.battle_bridge import BattleBridge
from src.pve.enums import EventType
from src.pve.models import (
    EventSequence,
    PveEntityState,
    PveEvent,
    PveSessionData,
    PveSquadState,
)
from src.pve.session_manager import PveSessionManager
from src.user.security import hash_password


# ============================================================================
# 测试替身：会话构造 / 母舰
# ============================================================================

def _combat_session(user_id: int = 1, session_id: int = 42,
                    current_index: int = 1) -> PveSessionData:
    """构造接敌测试会话：事件 1 = COMBAT("mob_1")、事件 2 = BOSS。

    locked mecha_id 用真实数据存在的 mech_rx78（entry 回退链直取 loader.mechas）。
    """
    events = [
        PveEvent(index=0, event_type=EventType.LOOT, event_id="random_chest"),
        PveEvent(index=1, event_type=EventType.COMBAT, event_id="mob_1"),
        PveEvent(index=2, event_type=EventType.BOSS_COMBAT, event_id="station_guardian"),
    ]
    members = [PveEntityState(
        entity_id="mech_rx78",
        current_hp=1000, current_en=100,
        max_hp=1000, max_en=100,
        last_combat_time=time.time(), is_alive=True,
    )]
    squad = PveSquadState(
        members=members,
        locked_config={"mechas": [{"mecha_id": "mech_rx78"}]},
    )
    session = PveSessionData(
        session_id=session_id, user_id=user_id,
        region_id="test_region", zone_id="test_zone",
        event_sequence=EventSequence(events=events, current_index=current_index),
        squad_state=squad, created_at=0.0, last_heartbeat=0.0,
    )
    PveSessionManager._sessions[session_id] = session
    return session


def _mothership() -> Mock:
    """母舰配置替身：回能率必须是真的数值（回能公式会做乘法）。"""
    return Mock(hp_regen_per_min=10, en_regen_per_min=5)


@pytest.fixture(scope="module")
def real_loader():
    from src import DataLoader
    loader = DataLoader(data_dir="data")
    loader.load_all()
    return loader


@pytest.fixture
def pve_sessions():
    """登记本测试创建的会话，收尾统一销毁，防止污染会话管理器。"""
    created: list[int] = []

    def _register(session: PveSessionData) -> PveSessionData:
        created.append(session.session_id)
        return session

    yield _register
    for sid in created:
        PveSessionManager.destroy_session(sid)


@pytest.fixture
async def auth_client(async_client, db_session):
    """登录态客户端：建用户 → 登录 → 带 Bearer 头（对齐 test_inventory_api 模式）。"""
    user = User(username="replay_user", password_hash=hash_password("pass123"))
    db_session.add(user)
    await db_session.commit()

    resp = await async_client.post(
        "/api/user/login", json={"username": "replay_user", "password": "pass123"}
    )
    token = resp.json()["access_token"]
    async_client.headers["Authorization"] = f"Bearer {token}"
    return async_client, user


@pytest.fixture
def patched_mothership(monkeypatch):
    """engage 端点硬编码的母舰 ID（ms_01）不在真实数据中——实例级替换
    get_mothership_config 回退到数值替身（预存 Mock，非本批引入）。"""
    from src.api.context import get_loader
    loader = get_loader()
    monkeypatch.setattr(
        loader, "get_mothership_config",
        lambda _mid: Mock(hp_regen_per_min=10, en_regen_per_min=5),
    )


# ============================================================================
# 桥接层：engage 裁定成功 → 战报暂存至会话（唯一去向）
# ============================================================================

def test_engage_stages_full_timeline_in_session(real_loader, pve_sessions):
    """engage 成功 → session.battle_reports[event_index] 为 Doc 14 四块结构
    （meta.route=="pve"）——战报的唯一去向是会话暂存，命令与资源分离。"""
    from src.factory import MechaFactory

    session = pve_sessions(_combat_session())
    session.battle_reports.clear()  # 防御：确保断言只针对本场写入

    result = BattleBridge.engage(
        session=session, event_index=1,
        loader=real_loader, mothership_config=_mothership(),
        mecha_factory=MechaFactory,
    )

    # 战报不在 BattleResult（命令只返回裁定摘要），在会话暂存里
    assert not hasattr(result, "battle_report")
    report = session.battle_reports[1]
    assert isinstance(report, dict)
    assert set(report.keys()) == {"meta", "init", "rounds", "result"}
    assert report["meta"]["route"] == "pve"
    assert report["result"]["rounds_fought"] == result.rounds_fought
    assert isinstance(report["rounds"], list)


# ============================================================================
# API 层：engage 响应=终局摘要 + 战报经重放端点 + advance 清理
# ============================================================================

async def test_api_engage_returns_summary_without_battle_report(
    auth_client, pve_sessions, patched_mothership
):
    """engage 响应只含终局摘要（无 battle_report 键）；战报经重放端点
    GET /battle/{event_index} 拿到四块结构（战报唯一出口）。"""
    client, user = auth_client
    session = pve_sessions(_combat_session(user_id=user.id))

    resp = await client.post(
        f"/api/pve/sessions/{session.session_id}/engage", json={"event_index": 1}
    )
    assert resp.status_code == 200
    body = resp.json()
    # 终局摘要字段齐备，且不再内联战报
    assert set(body.keys()) == {
        "outcome", "rounds_fought", "player_states",
        "enemy_state", "credits_earned", "loot_drops",
    }
    assert "battle_report" not in body
    assert 1 in session.battle_reports  # 裁定成功瞬间暂存必在内存

    # 完整战报走重放端点（首渲与重入同路）
    replay_resp = await client.get(
        f"/api/pve/sessions/{session.session_id}/battle/1"
    )
    assert replay_resp.status_code == 200
    report = replay_resp.json()["battle_report"]
    assert set(report.keys()) == {"meta", "init", "rounds", "result"}
    assert report["meta"]["route"] == "pve"
    assert report["result"]["rounds_fought"] == body["rounds_fought"]


async def test_api_advance_clears_stale_battle_reports(
    auth_client, pve_sessions, patched_mothership
):
    """advance 推进到新事件 → 旧事件点暂存被清（下一次推进即消化完成），
    新事件点接敌不受影响。"""
    client, user = auth_client
    session = pve_sessions(_combat_session(user_id=user.id))

    resp = await client.post(
        f"/api/pve/sessions/{session.session_id}/engage", json={"event_index": 1}
    )
    assert resp.status_code == 200
    assert set(session.battle_reports.keys()) == {1}

    resp = await client.post(
        f"/api/pve/sessions/{session.session_id}/advance", json={"expected_index": 1}
    )
    assert resp.status_code == 200
    assert resp.json()["new_event_index"] == 2
    assert 1 not in session.battle_reports  # 旧事件点已消化

    # 新事件点（BOSS）接敌：暂存落在新 key，不复活旧 key
    resp = await client.post(
        f"/api/pve/sessions/{session.session_id}/engage", json={"event_index": 2}
    )
    assert resp.status_code == 200
    assert set(session.battle_reports.keys()) == {2}


async def test_api_sync_correction_keeps_battle_reports(
    auth_client, pve_sessions, patched_mothership
):
    """同步修正分支（expected_index 错位）不推进即不消化——暂存原样保留。"""
    client, user = auth_client
    session = pve_sessions(_combat_session(user_id=user.id))

    resp = await client.post(
        f"/api/pve/sessions/{session.session_id}/engage", json={"event_index": 1}
    )
    assert resp.status_code == 200
    assert set(session.battle_reports.keys()) == {1}

    resp = await client.post(
        f"/api/pve/sessions/{session.session_id}/advance", json={"expected_index": 99}
    )
    assert resp.status_code == 200
    assert resp.json()["sync_correction"] is True
    assert set(session.battle_reports.keys()) == {1}  # 未推进：战报保留供重放


async def test_api_replay_returns_staged_report_verbatim(
    auth_client, pve_sessions, patched_mothership
):
    """engage 后 GET 重放 → 200 且 battle_report 与会话暂存逐字一致
    （重放端点=战报唯一出口，首渲与重入拿到的是同一份）。"""
    client, user = auth_client
    session = pve_sessions(_combat_session(user_id=user.id))

    engage_resp = await client.post(
        f"/api/pve/sessions/{session.session_id}/engage", json={"event_index": 1}
    )
    assert engage_resp.status_code == 200
    assert "battle_report" not in engage_resp.json()

    replay_resp = await client.get(
        f"/api/pve/sessions/{session.session_id}/battle/1"
    )
    assert replay_resp.status_code == 200
    assert replay_resp.json()["battle_report"] == session.battle_reports[1]


async def test_api_replay_uncached_event_returns_404(
    auth_client, pve_sessions, patched_mothership
):
    """未接敌事件点 → 404 说明无暂存战报（前端降级仅终局摘要）。"""
    client, user = auth_client
    session = pve_sessions(_combat_session(user_id=user.id))

    resp = await client.get(f"/api/pve/sessions/{session.session_id}/battle/0")
    assert resp.status_code == 404
    assert "battle report" in resp.json()["detail"]


async def test_api_replay_foreign_session_returns_404(auth_client, pve_sessions):
    """他人会话 → 404（与不存在同口径，不泄露他人会话存在性）。"""
    client, _user = auth_client
    session = pve_sessions(_combat_session(user_id=987654))  # 他人会话
    session.battle_reports[1] = {"meta": {"route": "pve"}}  # 有暂存也不给看

    resp = await client.get(f"/api/pve/sessions/{session.session_id}/battle/1")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "PVE Session not found"


async def test_api_replay_unknown_session_returns_404(auth_client):
    """会话不存在 → 404。"""
    client, _user = auth_client
    resp = await client.get("/api/pve/sessions/999999/battle/0")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "PVE Session not found"
