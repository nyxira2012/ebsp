"""
装配单点测试（Doc 15 §8 入口回归）。

覆盖收发室 BattleEntryService（E1 收编）：
- build_debug：静态配置装配与 MechaFactory 直构等价、值冻结、未知 ID → KeyError；
- build_pve：locked_config 回退链（snapshot_dict → mecha_id → 默认）、
  残血与时间回能算进快照且 session 零触碰（失败原子前提）、
  敌方模板 + 缩放、敌方残血、事件越界 ValueError、spec 值冻结；
- 失败原子：裁判 resolve 抛异常 → engage 传播且 session 零变更；
- 入口契约：simulate 未知 ID → 404（Doc 14 §2）、正常 ID → 200 四块结构。
"""

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.combat.entry import BattleEntryService
from src.factory import MechaFactory
from src.models import MechaSnapshot, WeaponSnapshot, WeaponType
from src.pve.battle_bridge import BattleBridge
from src.pve.enums import CombatOutcome, EventType
from src.pve.models import PveEntityState, PveEnemyState, PveEvent, PveSessionData, PveSquadState, EventSequence


# ============================================================================
# 测试替身：假加载器 / 假工厂 / 会话构造
# ============================================================================

@dataclass
class _MechaCfg:
    """假机体配置：id 即快照 instance_id，max_hp/power 驱动缩放断言。"""
    id: str
    name: str = "FakeMecha"
    max_hp: int = 1000
    power: int = 50


class _FakeLoader:
    """形迹对齐 DataLoader：mechas/equipments 字典 + KeyError 语义。"""

    def __init__(self, mechas=None, instance_config=None):
        self.mechas = {cfg.id: cfg for cfg in (mechas or [])}
        self.equipments = {}
        self._instance_config = instance_config

    def get_mecha_config(self, mecha_id):
        if mecha_id not in self.mechas:
            raise KeyError(f"机体配置不存在: {mecha_id}")
        return self.mechas[mecha_id]

    def get_instance_config(self, instance_id):
        if self._instance_config is None:
            raise KeyError(f"副本配置不存在: {instance_id}")
        return self._instance_config


class _FakeFactory:
    """假快照工厂：按配置产出可辨识快照，不依赖静态数据。"""

    def create_mecha_snapshot(self, mecha_conf, weapon_configs=None):
        return MechaSnapshot(
            instance_id=mecha_conf.id,
            mecha_name=mecha_conf.name,
            final_max_hp=mecha_conf.max_hp,
            current_hp=mecha_conf.max_hp,
            final_max_en=100,
            current_en=100,
            weapons=[_weapon(f"{mecha_conf.id}_gun", mecha_conf.power)],
        )


def _weapon(uid: str, power: int = 50) -> WeaponSnapshot:
    return WeaponSnapshot(
        uid=uid,
        definition_id=uid,
        name="测试武器",
        type=WeaponType.SHOOTING,
        final_power=power,
        en_cost=10,
        range_min=0,
        range_max=100,
        will_req=0,
        anim_id="a_test",
    )


def _mothership(hp_per_min: int = 10, en_per_min: int = 5) -> Mock:
    return Mock(hp_regen_per_min=hp_per_min, en_regen_per_min=en_per_min)


def _std_loader() -> _FakeLoader:
    """标准假加载器：覆盖我方回退链与敌方默认模板。"""
    return _FakeLoader(mechas=[
        _MechaCfg("m_alpha", max_hp=800),
        _MechaCfg("rx78"),
        _MechaCfg("mech_grunt", max_hp=100),
    ])


def _combat_session(locked_mechas=None, player_hp=1000, player_en=100,
                    player_max_hp=1000, player_max_en=100,
                    last_combat_time=1000.0) -> PveSessionData:
    """构造接敌测试会话：事件 1 = COMBAT("mob_1")。"""
    events = [
        PveEvent(index=0, event_type=EventType.LOOT, event_id="random_chest"),
        PveEvent(index=1, event_type=EventType.COMBAT, event_id="mob_1"),
        PveEvent(index=2, event_type=EventType.BOSS_COMBAT, event_id="station_guardian"),
    ]
    members = [PveEntityState(
        entity_id="rx78",
        current_hp=player_hp, current_en=player_en,
        max_hp=player_max_hp, max_en=player_max_en,
        last_combat_time=last_combat_time, is_alive=True,
    )]
    squad = PveSquadState(
        members=members,
        locked_config={"mechas": locked_mechas if locked_mechas is not None else [{"mecha_id": "m_alpha"}]},
    )
    return PveSessionData(
        session_id=42, user_id=1, region_id="test_region", zone_id="test_zone",
        event_sequence=EventSequence(events=events, current_index=1),
        squad_state=squad, created_at=0.0, last_heartbeat=0.0,
    )


def _build_pve(session, loader=None, mothership=None, now=1000.0, event_index=1,
               instance_config=None):
    """build_pve 便捷入口（默认参数与残血断言解耦：now == last_combat_time → 回能为 0）。"""
    return BattleEntryService.build_pve(
        session=session,
        event_index=event_index,
        loader=loader if loader is not None else _std_loader(),
        mothership_config=mothership if mothership is not None else _mothership(),
        mecha_factory=_FakeFactory(),
        now=now,
        instance_config=instance_config,
    )


# ============================================================================
# build_debug（调试来源装配）
# ============================================================================

@pytest.fixture(scope="module")
def real_loader():
    from src import DataLoader
    loader = DataLoader(data_dir="data")
    loader.load_all()
    return loader


async def test_build_debug_static_config_equivalence(real_loader):
    """静态配置装配：spec 快照与 MechaFactory 直构等价（E1 收编不改语义）。"""
    from src.api.presentation_api import BattleRequest

    req = BattleRequest(mecha_a_id="mech_rx78", mecha_b_id="mech_zaku")
    spec = await BattleEntryService.build_debug(real_loader, req, None, None)

    expected_a = MechaFactory.create_mecha_snapshot(
        real_loader.get_mecha_config("mech_rx78"), weapon_configs=real_loader.equipments)
    expected_b = MechaFactory.create_mecha_snapshot(
        real_loader.get_mecha_config("mech_zaku"), weapon_configs=real_loader.equipments)

    assert spec.mecha_a == expected_a
    assert spec.mecha_b == expected_b
    assert spec.context.source == "debug"


async def test_build_debug_value_frozen(real_loader, monkeypatch):
    """值冻结：装配产物持有深拷贝，原快照事后被改不影响 spec。"""
    from src.api.presentation_api import BattleRequest

    held_a = MechaFactory.create_mecha_snapshot(
        real_loader.get_mecha_config("mech_rx78"), weapon_configs=real_loader.equipments)
    held_b = MechaFactory.create_mecha_snapshot(
        real_loader.get_mecha_config("mech_zaku"), weapon_configs=real_loader.equipments)
    orig_a_hp = held_a.current_hp
    orig_b_max = held_b.final_max_hp

    stock = [held_a, held_b]
    monkeypatch.setattr(
        MechaFactory, "create_mecha_snapshot",
        staticmethod(lambda *args, **kwargs: stock.pop(0)),
    )

    req = BattleRequest(mecha_a_id="mech_rx78", mecha_b_id="mech_zaku")
    spec = await BattleEntryService.build_debug(real_loader, req, None, None)

    held_a.current_hp = 1
    held_b.final_max_hp = 7
    assert spec.mecha_a.current_hp == orig_a_hp
    assert spec.mecha_b.final_max_hp == orig_b_max


async def test_build_debug_unknown_id_raises_key_error(real_loader):
    """未知机体 ID → KeyError（handler 翻译为 404，Doc 14 §2 契约）。"""
    from src.api.presentation_api import BattleRequest

    req = BattleRequest(mecha_a_id="mech_rx78", mecha_b_id="no_such_mecha")
    with pytest.raises(KeyError):
        await BattleEntryService.build_debug(real_loader, req, None, None)


async def test_build_debug_user_save_degrades_on_unknown_mecha(real_loader, monkeypatch, capsys):
    """404 边界：存档覆盖段引用未知机体 → 降级默认配置，不向 handler 抛 KeyError。

    请求 ID 校验在存档段罩外——404 爆炸半径只覆盖请求字段失败（Doc 14 §2）。
    """
    from src.api.presentation_api import BattleRequest
    from src.core.factory import SnapshotFactory
    from src.user.repository import UserAssetRepository

    async def _fake_get_active_squad(session, user_id):
        return SimpleNamespace(mecha_ids=[999])

    async def _raise_key_error(self, session, user_id, mecha_id):
        raise KeyError(f"机体配置不存在: {mecha_id}")

    monkeypatch.setattr(UserAssetRepository, "get_active_squad", staticmethod(_fake_get_active_squad))
    monkeypatch.setattr(SnapshotFactory, "create_combat_snapshot", _raise_key_error)

    req = BattleRequest(mecha_a_id="mech_rx78", mecha_b_id="mech_zaku", use_user_save_for_a=True)
    spec = await BattleEntryService.build_debug(real_loader, req, SimpleNamespace(id=1), None)

    expected_a = MechaFactory.create_mecha_snapshot(
        real_loader.get_mecha_config("mech_rx78"), weapon_configs=real_loader.equipments)
    assert spec.mecha_a == expected_a  # 降级回静态默认配置
    assert "使用默认配置" in capsys.readouterr().out


# ============================================================================
# build_pve（PVE 会话还原装配）
# ============================================================================

def test_build_pve_restores_locked_snapshot_dict():
    """locked_config 回退链第一优先：snapshot_dict 还原（mecha_id 被忽略）。"""
    locked_snapshot = MechaSnapshot(
        instance_id="locked_snap", mecha_name="LockedSnap",
        final_max_hp=2222, current_hp=2222,
    )
    session = _combat_session(
        locked_mechas=[{"mecha_id": "m_alpha", "snapshot_dict": locked_snapshot.model_dump()}])

    spec, _ = _build_pve(session)

    assert spec.mecha_a.instance_id == "locked_snap"
    assert spec.mecha_a.mecha_name == "LockedSnap"


def test_build_pve_fallback_mecha_id_then_default():
    """回退链：无 snapshot_dict → mecha_id；mecha_id 缺失 → 默认 rx78。"""
    loader = _std_loader()

    # 第二优先：mecha_id 在 loader.mechas 中
    session = _combat_session(locked_mechas=[{"mecha_id": "m_alpha"}])
    spec, _ = _build_pve(session, loader)
    assert spec.mecha_a.instance_id == "m_alpha"

    # 第三优先：mecha_id 不在 mechas → 默认 rx78
    session = _combat_session(locked_mechas=[{"mecha_id": "ghost"}])
    spec, _ = _build_pve(session, loader)
    assert spec.mecha_a.instance_id == "rx78"

    # 第三优先：locked_config 无对应成员 → 默认 rx78
    session = _combat_session(locked_mechas=[])
    spec, _ = _build_pve(session, loader)
    assert spec.mecha_a.instance_id == "rx78"


def test_build_pve_regen_into_snapshot_only():
    """时间回能算进快照拷贝，PveEntityState 原值不动（失败原子的前提）。"""
    now = 5000.0
    session = _combat_session(
        player_hp=400, player_en=20,
        last_combat_time=now - 120,  # 2 分钟 → +20 HP / +10 EN
    )

    spec, _ = _build_pve(session, mothership=_mothership(hp_per_min=10, en_per_min=5), now=now)

    assert spec.mecha_a.current_hp == 420
    assert spec.mecha_a.current_en == 30
    assert spec.mecha_a.final_max_hp == 1000
    assert spec.mecha_a.final_max_en == 100

    # 回能封顶：残血接近满值时不越界
    session_cap = _combat_session(
        player_hp=999, player_en=99,
        last_combat_time=now - 120,
    )
    spec_cap, _ = _build_pve(session_cap, mothership=_mothership(10, 5), now=now)
    assert spec_cap.mecha_a.current_hp == 1000
    assert spec_cap.mecha_a.current_en == 100

    # 会话成员未被触碰（旧实现此处已就地 +20/+10——新实现零变更）
    member = session.squad_state.members[0]
    assert member.current_hp == 400
    assert member.current_en == 20
    assert member.last_combat_time == now - 120


def test_build_pve_enemy_template_and_scaling():
    """敌方事件点实例化：模板命中 → 指定机体 + 缩放档应用（配置由调用方传入）。"""
    scaling = SimpleNamespace(hp_mult=2.0, damage_mult=3.0, armor_mult=1.5, mobility_mult=1.2)
    template = SimpleNamespace(mecha_id="m_grunt", scaling=scaling)
    instance = SimpleNamespace(enemy_templates={"mob_1": template}, loot_tables={}, zones={})
    loader = _FakeLoader(
        mechas=[_MechaCfg("m_alpha"), _MechaCfg("m_grunt", max_hp=100, power=50)],
    )
    session = _combat_session()
    now = 7777.0

    spec, assembly = _build_pve(session, loader, now=now, instance_config=instance)

    assert spec.mecha_b.instance_id == "m_grunt"
    assert spec.mecha_b.final_max_hp == 200       # 100 * 2.0
    assert spec.mecha_b.current_hp == 200         # 缩放后满血
    assert spec.mecha_b.final_armor == 1500       # 1000 * 1.5
    assert spec.mecha_b.final_mobility == 120     # 100 * 1.2
    assert spec.mecha_b.weapons[0].final_power == 150  # 50 * 3.0
    assert spec.context.source == "pve"

    # 新建敌方：模板数据已备好但未落 session（裁定成功才插入）
    assert assembly.enemy_is_new is True
    assert assembly.enemy_state.enemy_template_id == "mob_1"
    assert assembly.enemy_state.entity_state.max_hp == 200
    assert assembly.enemy_state.entity_state.last_combat_time == now
    assert session.enemy_states == {}


def test_build_pve_enemy_default_template_fallback():
    """敌方回退：无副本配置/模板未命中 → mech_grunt，事件缺 event_id → zaku2。"""
    loader = _FakeLoader(mechas=[_MechaCfg("m_alpha"), _MechaCfg("mech_grunt", max_hp=100)])

    session = _combat_session()
    spec, assembly = _build_pve(session, loader)
    assert spec.mecha_b.instance_id == "mech_grunt"

    # 事件无 event_id → 敌方模板 ID 回退 zaku2（不在 mechas → 仍回退 mech_grunt 快照）
    session_no_id = _combat_session()
    session_no_id.event_sequence.events[1].event_id = None
    _, assembly_no_id = _build_pve(session_no_id, loader)
    assert assembly_no_id.enemy_state.enemy_template_id == "zaku2"


def test_build_pve_enemy_residual_injection():
    """敌方残血：已接敌过的事件点沿用 enemy_states 残血并共享引用。"""
    session = _combat_session()
    enemy = PveEnemyState(
        event_index=1,
        enemy_template_id="mob_1",
        entity_state=PveEntityState(
            entity_id="enemy_1", current_hp=123, current_en=45,
            max_hp=300, max_en=150, last_combat_time=1.0,
        ),
    )
    session.enemy_states[1] = enemy

    spec, assembly = _build_pve(session)

    assert spec.mecha_b.current_hp == 123
    assert spec.mecha_b.current_en == 45
    assert spec.mecha_b.final_max_hp == 300
    assert spec.mecha_b.final_max_en == 150
    assert assembly.enemy_is_new is False
    assert assembly.enemy_state is enemy  # 写回定位到 session 内既有对象


def test_build_pve_event_index_out_of_range():
    """事件索引越界 → ValueError（既有语义保留）。"""
    session = _combat_session()
    for bad_index in (99, -1, len(session.event_sequence.events)):
        with pytest.raises(ValueError):
            _build_pve(session, _std_loader(), event_index=bad_index)


def test_build_pve_spec_value_frozen():
    """值冻结：build 后改 session 字段不影响已冻结的 spec。"""
    session = _combat_session()
    spec, _ = _build_pve(session)

    session.squad_state.members[0].current_hp = 1
    session.squad_state.members[0].current_en = 1
    session.squad_state.locked_config["mechas"][0]["mecha_id"] = "ghost"

    assert spec.mecha_a.current_hp == 1000  # build 时点残血（回能 0）
    assert spec.mecha_a.current_en == 100
    assert spec.mecha_a.instance_id == "m_alpha"


# ============================================================================
# 失败原子（Doc 15 §3）
# ============================================================================

def test_engage_failure_atomic():
    """裁判 resolve 抛异常 → engage 传播且 session 零变更（失败原子不变量）。"""
    session = _combat_session()
    original_member = session.squad_state.members[0].model_copy(deep=True)

    with patch("src.pve.battle_bridge.Engagement") as mock_engagement:
        mock_engagement.return_value.resolve.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            BattleBridge.engage(
                session=session,
                event_index=1,
                loader=_std_loader(),
                mothership_config=_mothership(),
                mecha_factory=_FakeFactory(),
            )

    assert session.enemy_states == {}                       # 敌方未新建
    assert session.squad_state.members[0] == original_member  # 己方未被回能/写回
    assert session.event_sequence.events[1].cleared is False  # 事件未消耗
    assert session.battle_reports == {}                     # 战报暂存零写入（P1-b）


def test_engage_draw_keeps_enemy_residual_state():
    """DRAW 路径：敌方残血写回并随 BattleResult 返回（再接敌=新委托）。"""
    session = _combat_session()
    enemy = PveEnemyState(
        event_index=1,
        enemy_template_id="mob_1",
        entity_state=PveEntityState(
            entity_id="enemy_1", current_hp=250, current_en=80,
            max_hp=300, max_en=150, last_combat_time=1.0,
        ),
    )
    session.enemy_states[1] = enemy

    mock_ruling = Mock()
    mock_ruling.winner = None  # 平局
    mock_ruling.rounds_fought = 9
    # 残血写回走裁定 summary（Doc 15 §3）
    mock_ruling.summary.a = SimpleNamespace(hp=500, en=40, alive=True)
    mock_ruling.summary.b = SimpleNamespace(hp=200, en=60, alive=True)
    mock_report = Mock()
    mock_report.ruling = mock_ruling

    with patch("src.pve.battle_bridge.Engagement") as mock_engagement:
        mock_engagement.return_value.resolve.return_value = mock_report
        result = BattleBridge.engage(
            session=session, event_index=1, loader=_std_loader(),
            mothership_config=_mothership(), mecha_factory=_FakeFactory(),
        )

    assert result.outcome == CombatOutcome.DRAW
    assert result.rounds_fought == 9
    assert result.enemy_state is enemy.entity_state
    assert enemy.entity_state.current_hp == 200
    assert enemy.entity_state.current_en == 60
    assert session.squad_state.members[0].current_hp == 500
    assert session.squad_state.members[0].current_en == 40
    assert session.event_sequence.events[1].cleared is False
    assert 1 in session.enemy_states


# ============================================================================
# 入口契约（Doc 14 §2：simulate 语义不变 + 404 修复）
# ============================================================================

async def test_simulate_unknown_mecha_returns_404(async_client):
    """POST /battle/simulate 未知机体 ID → 404（此前误走 500，B2 实证遗留）。"""
    resp = await async_client.post(
        "/battle/simulate",
        json={"mecha_a_id": "mech_rx78", "mecha_b_id": "no_such_mecha"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "机体配置不存在"


async def test_simulate_returns_four_block_timeline(async_client):
    """POST /battle/simulate 正常 ID → 200 四块结构（meta/init/rounds/result）。"""
    resp = await async_client.post(
        "/battle/simulate",
        json={"mecha_a_id": "mech_rx78", "mecha_b_id": "mech_zaku"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"meta", "init", "rounds", "result"}
    assert body["meta"]["route"] == "debug"
