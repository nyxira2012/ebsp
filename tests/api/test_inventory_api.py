import pytest
from httpx import AsyncClient
from src.database.models import User, UserEquipment, UserItem, UserMothership
from src.user.security import hash_password

@pytest.fixture
async def authenticated_client(async_client: AsyncClient, db_session):
    # 创建用户
    user = User(username="inv_user", password_hash=hash_password("pass123"))
    db_session.add(user)
    await db_session.flush()
    
    # 初始化默认母舰 (容量 50)
    mothership = UserMothership(
        user_id=user.id,
        data={"owned_ids": ["light_corvette"], "current_id": "light_corvette"}
    )
    db_session.add(mothership)
    await db_session.commit()
    
    # 登录获取 Token
    resp = await async_client.post("/api/user/login", json={"username": "inv_user", "password": "pass123"})
    token = resp.json()["access_token"]
    async_client.headers["Authorization"] = f"Bearer {token}"
    return async_client, user

@pytest.mark.asyncio
async def test_api_inventory_status(authenticated_client):
    client, user = authenticated_client
    
    resp = await client.get("/api/inventory/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["capacity"] == 50
    assert data["current"] == 0

@pytest.mark.asyncio
async def test_api_finalize_overload(authenticated_client, db_session):
    client, user = authenticated_client
    
    # 首先添加一些装备
    from sqlalchemy import insert
    db_session.add(UserEquipment(user_id=user.id, equipment_id="old_wpn", is_equipped=False))
    await db_session.commit()
    
    # 获取这个装备的 ID
    from sqlalchemy import select
    res = await db_session.execute(select(UserEquipment).where(UserEquipment.equipment_id == "old_wpn"))
    old_id = res.scalar().id
    
    # 调用 finalize: 丢弃旧的，添加新的
    payload = {
        "add_equipments": [{"equipment_id": "new_wpn", "enhancement_level": 1, "random_stats": {}}],
        "add_items": [{"item_id": "alloy", "quantity": 10}],
        "discard_ids": [old_id]
    }
    
    resp = await client.post("/api/inventory/finalize", json=payload)
    assert resp.status_code == 200
    
    # 验证数据库状态
    await db_session.close() # 重新获取 session 以看到最新变更 (或依赖 cleanup)
    # 此处依赖 async_client 的上下文
    
    resp_list = await client.get("/api/inventory/items")
    data = resp_list.json()
    
    # 旧装备应该没了
    assert not any(e["equipment_id"] == "old_wpn" for e in data["equipments"])
    # 新装备应该有了
    assert any(e["equipment_id"] == "new_wpn" for e in data["equipments"])
    # 材料应该有了
    assert any(i["item_id"] == "alloy" for i in data["items"])

@pytest.mark.asyncio
async def test_api_finalize_reject_invalid_discard(authenticated_client, db_session):
    client, user = authenticated_client
    
    # 尝试丢弃一个不存在的 ID
    payload = {
        "add_equipments": [],
        "add_items": [],
        "discard_ids": [99999]
    }
    
    resp = await client.post("/api/inventory/finalize", json=payload)
    assert resp.status_code == 400
    assert "无效资产" in resp.json()["detail"]
