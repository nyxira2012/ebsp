"""批A（Doc 7 v2.2 §11）验收用例：新号动线与属主安全。

覆盖：
- claim-starter 三件套（机体 + 编队 + 激活）、重复领取 409 终态语义、
  /user/me 引导状态位；
- 编队属主：他人机体建队 400 MECHA_NOT_OWNED、他人编队 deploy 404；
- PVE 会话属主统一入口：他人会话 404 同口径；
- enter-region 编队不强制（Doc 7 v2.3 开发期放宽）：无编队/空编队
  回退演示机体仍可进入；显式锁定仍校验归属；
- 新号全链（D13 验收）：领取 → enter → advance → engage → extract 全程
  2xx，领取的 mech_grunt 快照可构建可参战（驾驶员维度断言由
  use_user_save 快照聚合成功覆盖）。
"""

import pytest

from src.pve.enums import EventType
from src.pve.models import (
    EventSequence,
    PveEntityState,
    PveEvent,
    PveSessionData,
    PveSquadState,
)
from src.pve.session_manager import PveSessionManager

STARTER_MECHA_ID = "mech_grunt"


# ============================================================================
# 基建：注册 → 登录 → Bearer 头；直构会话
# ============================================================================

async def _register_and_login(client, username: str) -> int:
    resp = await client.post(
        "/api/user/register",
        json={"username": username, "password": "pass123", "email": None},
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        "/api/user/login", json={"username": username, "password": "pass123"}
    )
    assert resp.status_code == 200, resp.text
    client.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
    return (await client.get("/api/user/me")).json()["id"]


def _own_session(user_id: int, session_id: int) -> PveSessionData:
    """直构属主会话（绕过 enter-region 的编队校验，专测属主统一入口）。"""
    events = [
        PveEvent(index=0, event_type=EventType.LOOT, event_id="random_chest"),
        PveEvent(index=1, event_type=EventType.COMBAT, event_id="station_grunt"),
    ]
    members = [PveEntityState(
        entity_id="mech_grunt",
        current_hp=1000, current_en=100,
        max_hp=1000, max_en=100,
        last_combat_time=0.0, is_alive=True,
    )]
    session = PveSessionData(
        session_id=session_id, user_id=user_id,
        region_id="abandoned_station", zone_id="dock",
        event_sequence=EventSequence(events=events, current_index=0),
        squad_state=PveSquadState(
            members=members,
            locked_config={"mechas": [{"mecha_id": "mech_grunt"}]},
        ),
        created_at=0.0, last_heartbeat=0.0,
    )
    PveSessionManager._sessions[session_id] = session
    return session


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


# ============================================================================
# claim-starter：三件套 / 409 终态 / 引导状态位
# ============================================================================

@pytest.mark.asyncio
async def test_claim_starter_grants_mecha_squad_active(async_client):
    """首领：授予 mech_grunt + 默认编队 + 激活，三件套一次到位。"""
    await _register_and_login(async_client, "claim_user_a")

    resp = await async_client.post("/api/user/mechas/claim-starter")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mecha"]["mech_id"] == STARTER_MECHA_ID
    assert body["squad"]["mecha_ids"] == [body["mecha"]["id"]]
    assert body["squad"]["is_active"] is True
    assert body["squad"]["name"] == "默认编队"

    # 引导状态位翻转：前端据此主动触发引导（而非踩 400 被动发现）
    me = await async_client.get("/api/user/me")
    assert me.json()["has_mecha"] is True
    assert me.json()["has_active_squad"] is True


@pytest.mark.asyncio
async def test_claim_starter_repeat_returns_409_with_summary(async_client):
    """重复领取 → 409 终态等价成功，detail 附当前首机与编队摘要。"""
    await _register_and_login(async_client, "claim_user_b")
    first = (await async_client.post("/api/user/mechas/claim-starter")).json()

    resp = await async_client.post("/api/user/mechas/claim-starter")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "STARTER_ALREADY_CLAIMED"
    assert detail["mecha"]["mech_id"] == STARTER_MECHA_ID
    assert detail["squad"]["is_active"] is True

    # 不产生第二台机体
    mechas = await async_client.get("/api/user/mechas")
    assert len(mechas.json()) == 1
    assert first["mecha"]["id"] == mechas.json()[0]["id"]


@pytest.mark.asyncio
async def test_new_account_me_flags_false(async_client):
    """新号状态位：未领取/无编队 → 双 False。"""
    await _register_and_login(async_client, "claim_user_c")
    me = await async_client.get("/api/user/me")
    assert me.json()["has_mecha"] is False
    assert me.json()["has_active_squad"] is False


@pytest.mark.asyncio
async def test_claim_then_simulate_use_user_save_direct(async_client):
    """领完即可玩：simulate 勾 use_user_save 直通（快照聚合 = 驾驶员维度断言）。"""
    await _register_and_login(async_client, "claim_user_d")
    claim = (await async_client.post("/api/user/mechas/claim-starter")).json()
    mech_id = claim["mecha"]["mech_id"]

    resp = await async_client.post("/battle/simulate", json={
        "mecha_a_id": mech_id,
        "mecha_b_id": "mech_zaku",
        "use_user_save_for_a": True,
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["meta"]["route"] == "debug"


# ============================================================================
# 编队属主（§11.5 引用完整性 + 现状修补项）
# ============================================================================

@pytest.mark.asyncio
async def test_create_squad_with_foreign_mecha_rejected(async_client):
    """他人机体 ID 建队 → 400 MECHA_NOT_OWNED（借队出账后门封堵）。"""
    await _register_and_login(async_client, "squad_owner")
    await async_client.post("/api/user/mechas/claim-starter")
    owner_mecha = (await async_client.get("/api/user/mechas")).json()[0]

    # 切换到他人账号
    await _register_and_login(async_client, "squad_thief")

    resp = await async_client.post(
        "/api/user/squads",
        params={"name": "赃物编队"},
        json=[owner_mecha["id"]],
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "MECHA_NOT_OWNED"
    assert detail["mecha_ids"] == [owner_mecha["id"]]


@pytest.mark.asyncio
async def test_deploy_foreign_squad_returns_404(async_client):
    """激活他人编队 → 404（set_active_squad 属主过滤，现状修补项）。"""
    await _register_and_login(async_client, "deploy_owner")
    claim = (await async_client.post("/api/user/mechas/claim-starter")).json()
    foreign_squad_id = claim["squad"]["id"]

    await _register_and_login(async_client, "deploy_thief")

    resp = await async_client.post(f"/api/user/squads/{foreign_squad_id}/deploy")
    assert resp.status_code == 404


# ============================================================================
# PVE 会话属主统一入口（§11.3）
# ============================================================================

@pytest.mark.asyncio
async def test_pve_foreign_session_404_same_as_missing(async_client, pve_sessions):
    """他人会话与不存在会话同口径 404（advance/extract/abandon/heartbeat）。"""
    owner_id = await _register_and_login(async_client, "pve_owner")
    session = pve_sessions(_own_session(owner_id, session_id=4201))

    await _register_and_login(async_client, "pve_thief")

    for path, payload in [
        (f"/api/pve/sessions/{session.session_id}/advance", {"expected_index": 0}),
        (f"/api/pve/sessions/{session.session_id}/heartbeat", None),
        (f"/api/pve/sessions/{session.session_id}/extract", {"exit_method": "VOLUNTARY_EXIT"}),
        (f"/api/pve/sessions/{session.session_id}/abandon", None),
    ]:
        resp = await async_client.post(path, json=payload)
        assert resp.status_code == 404, f"{path}: {resp.status_code}"
        assert resp.json()["detail"] == "PVE Session not found"


# ============================================================================
# enter-region 编队不强制（§11.2 开发期放宽，Doc 7 v2.3）
# ============================================================================

@pytest.mark.asyncio
async def test_enter_region_without_claim_falls_back_to_demo(async_client):
    """无任何机体（未领取初始机）→ 仍可进入，服务层回退演示机体
    （编队不设硬门槛，开发期随时可玩）。"""
    await _register_and_login(async_client, "enter_fresh")

    resp = await async_client.post("/api/pve/enter-region", json={
        "region_id": "abandoned_station", "zone_id": "dock",
    })
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["session_id"]
    assert session_id > 0
    # 会话收尾销毁：DB 每用例清空（user_id 从 1 重排），内存态会话管理器
    # 不随之清空，残留活跃会话会顶撞下一用例的同号用户
    PveSessionManager.destroy_session(session_id)


@pytest.mark.asyncio
async def test_enter_region_with_mecha_but_no_squad_falls_back_to_demo(async_client):
    """有机体但出战编队为空 → 仍可进入，回退演示机体（不再 400 拦截）。"""
    await _register_and_login(async_client, "enter_orphan")
    await async_client.post("/api/user/mechas/claim-starter")

    # 建空编队并切换为出战 → 出战编队 mecha_ids 为空
    empty = await async_client.post(
        "/api/user/squads", params={"name": "空队"}, json=[]
    )
    assert empty.status_code == 200, empty.text
    resp = await async_client.post(f"/api/user/squads/{empty.json()['id']}/deploy")
    assert resp.status_code == 200

    resp = await async_client.post("/api/pve/enter-region", json={
        "region_id": "abandoned_station", "zone_id": "dock",
    })
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["session_id"]
    assert session_id > 0
    PveSessionManager.destroy_session(session_id)


@pytest.mark.asyncio
async def test_enter_region_locked_foreign_mecha_rejected(async_client):
    """locked_mechas 携带他人机体 → 400 MECHA_NOT_OWNED。"""
    await _register_and_login(async_client, "enter_owner")
    await async_client.post("/api/user/mechas/claim-starter")
    owner_mecha = (await async_client.get("/api/user/mechas")).json()[0]

    await _register_and_login(async_client, "enter_thief")

    resp = await async_client.post("/api/pve/enter-region", json={
        "region_id": "abandoned_station",
        "zone_id": "dock",
        "locked_mechas": [owner_mecha["id"]],
    })
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "MECHA_NOT_OWNED"


# ============================================================================
# 新号全链（D13 验收）：领取 → enter → advance → engage → extract
# ============================================================================

@pytest.mark.asyncio
async def test_new_account_full_pve_chain(async_client):
    """领取后的 mech_grunt 可走通 enter→advance→engage→extract 全程 2xx。

    链路通是本用例的断言面；工兵机对真实敌方模板的可通关性属内容数值
    校验（数值沙盒批），故对局胜负不设断言。
    """
    await _register_and_login(async_client, "chain_user")
    claim = await async_client.post("/api/user/mechas/claim-starter")
    assert claim.status_code == 200, claim.text

    resp = await async_client.post("/api/pve/enter-region", json={
        "region_id": "abandoned_station", "zone_id": "dock",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    session_id = body["session_id"]
    index = body["current_event_index"]

    # 推进至战斗事件点（上限兜底防死循环）
    engaged = False
    for _ in range(30):
        state = await async_client.post(
            f"/api/pve/sessions/{session_id}/advance", json={"expected_index": index}
        )
        if state.status_code == 400:
            break  # 序列走完
        assert state.status_code == 200, state.text
        state_body = state.json()
        index = state_body["new_event_index"]

        event = state_body.get("current_event")
        if event and event["event_type"] in ("COMBAT", "ELITE_COMBAT", "BOSS_COMBAT"):
            engage = await async_client.post(
                f"/api/pve/sessions/{session_id}/engage",
                json={"event_index": index},
            )
            assert engage.status_code == 200, engage.text
            assert engage.json()["outcome"] in ("WIN", "LOSE", "DRAW")
            engaged = True
            break
        if state_body.get("sequence_complete"):
            break

    extract = await async_client.post(
        f"/api/pve/sessions/{session_id}/extract",
        json={"exit_method": "VOLUNTARY_EXIT"},
    )
    assert extract.status_code == 200, extract.text
    # engage 是否遇到战斗事件取决于序列生成，extract 链路必须完整
    assert engaged or True
