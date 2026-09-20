"""练习场 API 契约测试（Doc 16 v1.2）

只读列表接口的红线：
1. 条目字段恰为八项（名字/描述/敌我机体 ID/敌我机体官方名/环境 ID/类别）
   ——不泄露机体面板、不携带任何图片资源引用（Doc 14 §9.1：后端契约只报 ID）；
2. 下发的机体 ID 必须真实存在于 mechas.json，官方名从机体配置派生
   （名字单一真相归后端，练习场配置文件不写名字）；环境 ID 必须真实
   存在于 environments.json；
3. 列表是开战的唯一前置——条目 ID 直接可打 POST /battle/simulate，
   且练习场对局 route=training 落进战报 meta（Doc 14 v1.7）；
4. 加载期坏配置处置：无效机体/环境引用的条目剔除，不阻断启动
   （v1.2 起 kind 被环境吸收，列表角标从 environment_id 派生）；
5. 防御测试全链路（Doc 16 §5.3）：力场保护下玩家不可败、全程免死。
"""

import json
from pathlib import Path
import tempfile

import pytest
from httpx import AsyncClient

from src import DataLoader
from src.api.context import set_loader, get_loader
from src.models import MechaConfig, PracticeScenarioConfig, EnvironmentConfig

EXPECTED_FIELDS = {
    "name", "description",
    "mecha_a_id", "mecha_b_id",
    "mecha_a_name", "mecha_b_name",
    "environment_id",
    "kind",
}
VALID_KINDS = {"standard", "attack_test", "defense_test"}


@pytest.mark.asyncio
async def test_practice_list_returns_scenarios(async_client: AsyncClient):
    """列表非空、免鉴权可读、保持配置文件顺序（首个为经典演示局）"""
    resp = await async_client.get("/battle/practice")
    assert resp.status_code == 200
    scenarios = resp.json()
    assert isinstance(scenarios, list) and len(scenarios) > 0
    assert scenarios[0]["name"] == "初次出击"


@pytest.mark.asyncio
async def test_practice_item_fields_exactly_minimal(async_client: AsyncClient):
    """契约最小化：条目字段恰为八项，无面板数值/胜率/图片路径等任何多余字段"""
    resp = await async_client.get("/battle/practice")
    assert resp.status_code == 200
    for item in resp.json():
        assert set(item.keys()) == EXPECTED_FIELDS
        assert item["name"] and isinstance(item["description"], str)
        assert item["mecha_a_id"] and item["mecha_b_id"]
        assert item["kind"] in VALID_KINDS


@pytest.mark.asyncio
async def test_practice_mecha_refs_and_names_derived(async_client: AsyncClient):
    """机体 ID 必须存在，官方名必须与机体配置逐字一致（派生而非另写）；
    环境 ID 必须存在于 environments.json（列表能选、规则就在）"""
    loader = get_loader()
    resp = await async_client.get("/battle/practice")
    assert resp.status_code == 200
    for item in resp.json():
        assert item["mecha_a_id"] in loader.mechas
        assert item["mecha_b_id"] in loader.mechas
        assert item["mecha_a_name"] == loader.mechas[item["mecha_a_id"]].name
        assert item["mecha_b_name"] == loader.mechas[item["mecha_b_id"]].name
        assert item["environment_id"] in loader.environments


@pytest.mark.asyncio
async def test_practice_content_floor(async_client: AsyncClient):
    """内容底线（Doc 16 §3，v1.2 全量生效）：标准局 >=2、攻击测试 >=1、
    防御测试 >=1（防御木桩内容随 v1.2 批次 2 上线）"""
    resp = await async_client.get("/battle/practice")
    kinds = [item["kind"] for item in resp.json()]
    assert kinds.count("standard") >= 2
    assert kinds.count("attack_test") >= 1
    assert kinds.count("defense_test") >= 1


@pytest.mark.asyncio
async def test_practice_scenario_is_simulatable(async_client: AsyncClient):
    """全链路：取列表第一场，其机体 ID 直接打 simulate 出结算"""
    resp = await async_client.get("/battle/practice")
    assert resp.status_code == 200
    first = resp.json()[0]

    battle = await async_client.post("/battle/simulate", json={
        "mecha_a_id": first["mecha_a_id"],
        "mecha_b_id": first["mecha_b_id"],
        "route": "training",
    })
    assert battle.status_code == 200
    timeline = battle.json()
    # Doc 14 四块结构、结算与入口标记在场
    assert timeline["meta"]["route"] == "training"
    assert timeline["init"]["a"]["mecha_id"] == first["mecha_a_id"]
    assert timeline["init"]["b"]["mecha_id"] == first["mecha_b_id"]
    assert len(timeline["rounds"]) >= 1
    assert timeline["result"]["finish"] in ("ko", "decision", "draw")


@pytest.mark.asyncio
async def test_simulate_route_default_and_rejected(async_client: AsyncClient):
    """route 参数：缺省 debug 不变（金样张同路径）；pve/pvp 伪造被 422 拒绝"""
    default_resp = await async_client.post("/battle/simulate", json={
        "mecha_a_id": "mech_rx78", "mecha_b_id": "mech_zaku",
    })
    assert default_resp.status_code == 200
    assert default_resp.json()["meta"]["route"] == "debug"

    for forged in ("pve", "pvp"):
        resp = await async_client.post("/battle/simulate", json={
            "mecha_a_id": "mech_rx78", "mecha_b_id": "mech_zaku", "route": forged,
        })
        assert resp.status_code == 422


# ============================================================================
# 防御测试全链路（Doc 16 §5.3）：列表条目 → simulate（带环境）→ 力场兜底
# ============================================================================

@pytest.mark.asyncio
async def test_practice_defense_dummy_full_chain(async_client: AsyncClient, reloaded_skills):
    """防御测试全链路：从列表取 defense_test 条目，按条目透传开战——

    力场两效果（回合回满 + 致死钳制）经 reloaded_skills 共享夹具
    （tests/conftest.py）重注册后注入玩家快照，玩家恒满血且免死：
    不可能败（winner 恒 a，draw 实际不可达），全程任一事件落地后 HP
    均不落零。回合数不写死（D4 目标 40-60，随机方差写死必 flake）。
    """
    resp = await async_client.get("/battle/practice")
    assert resp.status_code == 200
    defense = [s for s in resp.json() if s["kind"] == "defense_test"]
    assert len(defense) >= 1
    target = defense[0]

    battle = await async_client.post("/battle/simulate", json={
        "mecha_a_id": target["mecha_a_id"],
        "mecha_b_id": target["mecha_b_id"],
        "environment_id": target["environment_id"],
        "route": "training",
        "use_user_save_for_a": False,
    })
    assert battle.status_code == 200
    timeline = battle.json()

    assert timeline["meta"]["route"] == "training"
    # 免死红线：全程扫描战报，玩家侧事件落地后 HP 恒不落零
    for round_block in timeline["rounds"]:
        for seq in round_block["attack_sequences"]:
            for event in seq["events"]:
                if event["state_after"] is not None:
                    assert event["state_after"]["a"]["hp"] > 0
    # 力场下玩家不可能败：终局只可能是 KO 掉木桩或回合期满判胜
    assert timeline["result"]["winner"] == "a"
    assert timeline["result"]["finish"] in ("ko", "decision")


def test_loader_drops_scenarios_with_unknown_mecha():
    """加载期交叉校验：引用不存在机体的条目被剔除，不进运行时"""
    loader = DataLoader(data_dir="data")
    loader.load_all()
    before = set(loader.practice_scenarios)

    from src.models import PracticeScenarioConfig
    loader.practice_scenarios["broken"] = PracticeScenarioConfig(
        id="broken", name="坏条目", description="",
        environment_id="env_field",
        mecha_a_id="mech_rx78", mecha_b_id="no_such_mecha",
    )
    loader._validate_practice_scenarios()

    assert "broken" not in loader.practice_scenarios
    assert set(loader.practice_scenarios) == before


def test_loader_drops_scenarios_with_unknown_environment():
    """加载期交叉校验（v1.2）：引用不存在环境的条目被剔除，不进运行时"""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "mechas.json").write_text(json.dumps([
            {"id": "m1", "name": "M1", "portrait_id": "p1",
             "init_hp": 100, "init_en": 10, "init_armor": 10, "init_mobility": 10,
             "init_hit": 0, "init_precision": 0, "init_crit": 0,
             "init_dodge": 0, "init_parry": 0, "init_block": 0, "init_block_red": 0}
        ], ensure_ascii=False), encoding="utf-8")
        (td / "environments.json").write_text(json.dumps([
            {"id": "env_field", "name": "野战", "kind": "standard"},
        ], ensure_ascii=False), encoding="utf-8")
        (td / "practice_scenarios.json").write_text(json.dumps([
            {"id": "ok", "name": "好条目", "description": "",
             "environment_id": "env_field",
             "mecha_a_id": "m1", "mecha_b_id": "m1"},
            {"id": "bad_env", "name": "坏环境", "description": "",
             "environment_id": "no_such_env",
             "mecha_a_id": "m1", "mecha_b_id": "m1"},
        ], ensure_ascii=False), encoding="utf-8")

        loader = DataLoader(data_dir=str(td))
        loader._load_from_json("mechas.json", MechaConfig, loader.mechas)
        loader._load_from_json("environments.json", EnvironmentConfig, loader.environments)
        loader._load_from_json("practice_scenarios.json", PracticeScenarioConfig, loader.practice_scenarios)
        loader._validate_practice_scenarios()

    assert set(loader.practice_scenarios) == {"ok"}
