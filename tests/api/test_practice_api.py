"""练习场 API 契约测试（Doc 16）

只读列表接口的红线：
1. 条目字段恰为 名字/描述/敌我机体 ID 四项——不泄露机体面板、
   不携带任何图片资源引用（Doc 14 §9.1：后端契约只报 ID）；
2. 下发的机体 ID 必须真实存在于 mechas.json（加载期交叉校验）；
3. 列表是开战的唯一前置——条目 ID 直接可打 POST /battle/simulate。
"""

import pytest
from httpx import AsyncClient

from src import DataLoader
from src.api.context import set_loader, get_loader

EXPECTED_FIELDS = {"name", "description", "mecha_a_id", "mecha_b_id"}


@pytest.mark.asyncio
async def test_practice_list_returns_scenarios(async_client: AsyncClient):
    """列表非空、免鉴权可读、保持配置文件顺序"""
    resp = await async_client.get("/battle/practice")
    assert resp.status_code == 200
    scenarios = resp.json()
    assert isinstance(scenarios, list)
    assert len(scenarios) > 0
    # 顺序即配置文件顺序（首个为经典演示局）
    assert scenarios[0]["name"] == "初次出击"


@pytest.mark.asyncio
async def test_practice_item_fields_exactly_minimal(async_client: AsyncClient):
    """契约最小化：条目字段恰为四项，无 id/面板/图片路径等任何多余字段"""
    resp = await async_client.get("/battle/practice")
    assert resp.status_code == 200
    for item in resp.json():
        assert set(item.keys()) == EXPECTED_FIELDS
        assert isinstance(item["name"], str) and item["name"]
        assert isinstance(item["description"], str)
        assert isinstance(item["mecha_a_id"], str) and item["mecha_a_id"]
        assert isinstance(item["mecha_b_id"], str) and item["mecha_b_id"]


@pytest.mark.asyncio
async def test_practice_mecha_refs_exist(async_client: AsyncClient):
    """下发的一切机体 ID 必须能在 mechas.json 找到（前端拿去查立绘对照表）"""
    loader = get_loader()
    resp = await async_client.get("/battle/practice")
    assert resp.status_code == 200
    for item in resp.json():
        assert item["mecha_a_id"] in loader.mechas
        assert item["mecha_b_id"] in loader.mechas


@pytest.mark.asyncio
async def test_practice_scenario_is_simulatable(async_client: AsyncClient):
    """全链路：取列表第一场，其机体 ID 直接打 simulate 出结算"""
    resp = await async_client.get("/battle/practice")
    assert resp.status_code == 200
    first = resp.json()[0]

    battle = await async_client.post("/battle/simulate", json={
        "mecha_a_id": first["mecha_a_id"],
        "mecha_b_id": first["mecha_b_id"],
    })
    assert battle.status_code == 200
    timeline = battle.json()
    # Doc 14 四块结构与结算在场
    assert timeline["meta"]["contract_version"]
    assert timeline["init"]["a"]["mecha_id"] == first["mecha_a_id"]
    assert timeline["init"]["b"]["mecha_id"] == first["mecha_b_id"]
    assert len(timeline["rounds"]) >= 1
    assert timeline["result"]["finish"] in ("ko", "decision", "draw")


def test_loader_drops_scenarios_with_unknown_mecha():
    """加载期交叉校验：引用不存在机体的条目被剔除，不进运行时"""
    loader = DataLoader(data_dir="data")
    loader.load_all()
    before = set(loader.practice_scenarios)

    from src.models import PracticeScenarioConfig
    loader.practice_scenarios["broken"] = PracticeScenarioConfig(
        id="broken", name="坏条目", description="",
        mecha_a_id="mech_rx78", mecha_b_id="no_such_mecha",
    )
    loader._validate_practice_scenarios()

    assert "broken" not in loader.practice_scenarios
    assert set(loader.practice_scenarios) == before
