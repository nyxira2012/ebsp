"""
用户系统 API 测试

测试内容:
- 用户注册/登录
- JWT Token 认证
- 存档 CRUD 接口
- 出战存档管理
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.user.schemas import UserCreate, GameSaveCreate, SaveData, SaveMetadata
from src.user.repository import UserRepository, GameSaveRepository
from src.models import MechaSnapshot


# ============================================================================
# 健康检查测试
# ============================================================================

class TestHealthCheck:
    """健康检查接口测试"""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, async_client: AsyncClient):
        """测试健康检查端点"""
        response = await async_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ============================================================================
# 用户注册/登录测试
# ==============================================================================

class TestUserAuth:
    """用户认证接口测试"""

    @pytest.mark.asyncio
    async def test_register_user_success(self, async_client: AsyncClient):
        """测试成功注册用户"""
        response = await async_client.post(
            "/api/user/register",
            json={
                "username": "newuser",
                "password": "password123",
                "email": "new@example.com"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "newuser"
        assert data["email"] == "new@example.com"
        assert "id" in data
        assert "password" not in data  # 不返回密码

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, async_client: AsyncClient):
        """测试重复用户名注册"""
        # 第一个用户
        await async_client.post(
            "/api/user/register",
            json={"username": "duplicate", "password": "pass123"}
        )

        # 尝试注册相同用户名
        response = await async_client.post(
            "/api/user/register",
            json={"username": "duplicate", "password": "pass456"}
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_register_invalid_username(self, async_client: AsyncClient):
        """测试无效用户名"""
        response = await async_client.post(
            "/api/user/register",
            json={"username": "a", "password": "pass123"}  # 用户名太短
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_login_success(self, async_client: AsyncClient):
        """测试成功登录"""
        # 先注册
        await async_client.post(
            "/api/user/register",
            json={"username": "loginuser", "password": "loginpass123"}
        )

        # 登录
        response = await async_client.post(
            "/api/user/login",
            json={"username": "loginuser", "password": "loginpass123"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, async_client: AsyncClient):
        """测试错误密码登录"""
        # 先注册
        await async_client.post(
            "/api/user/register",
            json={"username": "wrongpass", "password": "correct123"}
        )

        # 使用错误密码登录
        response = await async_client.post(
            "/api/user/login",
            json={"username": "wrongpass", "password": "wrong123"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, async_client: AsyncClient):
        """测试不存在的用户登录"""
        response = await async_client.post(
            "/api/user/login",
            json={"username": "nonexistent", "password": "pass123"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user(self, async_client: AsyncClient):
        """测试获取当前用户信息"""
        # 注册并登录
        await async_client.post(
            "/api/user/register",
            json={"username": "meuser", "password": "mepass123", "email": "me@example.com"}
        )
        login_response = await async_client.post(
            "/api/user/login",
            json={"username": "meuser", "password": "mepass123"}
        )
        token = login_response.json()["access_token"]

        # 获取用户信息
        response = await async_client.get(
            "/api/user/me",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "meuser"
        assert data["email"] == "me@example.com"

    @pytest.mark.asyncio
    async def test_get_current_user_unauthorized(self, async_client: AsyncClient):
        """测试未认证访问用户信息"""
        response = await async_client.get("/api/user/me")
        assert response.status_code == 401


# ============================================================================
# 认证辅助 Fixtures
# ============================================================================

@pytest.fixture
async def auth_token(async_client: AsyncClient) -> str:
    """获取认证 Token"""
    await async_client.post(
        "/api/user/register",
        json={"username": "testuser", "password": "testpass123"}
    )
    response = await async_client.post(
        "/api/user/login",
        json={"username": "testuser", "password": "testpass123"}
    )
    return response.json()["access_token"]

@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    """获取认证请求头"""
    return {"Authorization": f"Bearer {auth_token}"}

# ============================================================================
# 存档管理测试
# ============================================================================

class TestGameSaveAPI:
    """游戏存档 API 测试"""

    @pytest.mark.asyncio
    async def test_create_save(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_mecha_snapshot: MechaSnapshot
    ):
        """测试创建存档"""
        save_data = SaveData(
            version="1.0",
            mecha=test_mecha_snapshot.model_dump(mode='json'),
            metadata=SaveMetadata(summary="新游戏", last_area="起始地", play_time=0)
        )

        response = await async_client.post(
            "/api/user/saves",
            headers=auth_headers,
            json={
                "slot_id": 1,
                "save_name": "新游戏",
                "save_data": save_data.model_dump()
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["slot_id"] == 1
        assert data["save_name"] == "新游戏"
        assert data["is_deployed"] is False

    @pytest.mark.asyncio
    async def test_list_saves(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_mecha_snapshot: MechaSnapshot
    ):
        """测试获取存档列表"""
        # 创建多个存档
        for slot_id in [1, 2]:
            save_data = SaveData(
                version="1.0",
                mecha=test_mecha_snapshot.model_dump(mode='json'),
                metadata=SaveMetadata(summary=f"存档{slot_id}", last_area="测试", play_time=0)
            )
            await async_client.post(
                "/api/user/saves",
                headers=auth_headers,
                json={
                    "slot_id": slot_id,
                    "save_name": f"存档{slot_id}",
                    "save_data": save_data.model_dump()
                }
            )

        # 获取存档列表
        response = await async_client.get("/api/user/saves", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["slot_id"] == 1
        assert data[1]["slot_id"] == 2

    @pytest.mark.asyncio
    async def test_get_save_by_id(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_mecha_snapshot: MechaSnapshot
    ):
        """测试获取单个存档"""
        # 创建存档
        save_data = SaveData(
            version="1.0",
            mecha=test_mecha_snapshot.model_dump(mode='json'),
            metadata=SaveMetadata(summary="测试", last_area="测试", play_time=0)
        )
        create_response = await async_client.post(
            "/api/user/saves",
            headers=auth_headers,
            json={
                "slot_id": 1,
                "save_name": "测试存档",
                "save_data": save_data.model_dump()
            }
        )
        save_id = create_response.json()["id"]

        # 获取存档
        response = await async_client.get(f"/api/user/saves/{save_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == save_id
        assert data["save_name"] == "测试存档"

    @pytest.mark.asyncio
    async def test_update_save(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_mecha_snapshot: MechaSnapshot
    ):
        """测试更新存档"""
        # 创建存档
        save_data = SaveData(
            version="1.0",
            mecha=test_mecha_snapshot.model_dump(mode='json'),
            metadata=SaveMetadata(summary="原名称", last_area="测试", play_time=0)
        )
        create_response = await async_client.post(
            "/api/user/saves",
            headers=auth_headers,
            json={
                "slot_id": 1,
                "save_name": "原名称",
                "save_data": save_data.model_dump()
            }
        )
        save_id = create_response.json()["id"]

        # 更新存档
        response = await async_client.put(
            f"/api/user/saves/{save_id}",
            headers=auth_headers,
            json={"save_name": "新名称"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["save_name"] == "新名称"

    @pytest.mark.asyncio
    async def test_delete_save(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_mecha_snapshot: MechaSnapshot
    ):
        """测试删除存档"""
        # 创建存档
        save_data = SaveData(
            version="1.0",
            mecha=test_mecha_snapshot.model_dump(mode='json'),
            metadata=SaveMetadata(summary="待删除", last_area="测试", play_time=0)
        )
        create_response = await async_client.post(
            "/api/user/saves",
            headers=auth_headers,
            json={
                "slot_id": 1,
                "save_name": "待删除",
                "save_data": save_data.model_dump()
            }
        )
        save_id = create_response.json()["id"]

        # 删除存档
        response = await async_client.delete(f"/api/user/saves/{save_id}", headers=auth_headers)

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_deploy_save(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_mecha_snapshot: MechaSnapshot
    ):
        """测试设置出战存档"""
        # 创建两个存档
        for slot_id in [1, 2]:
            save_data = SaveData(
                version="1.0",
                mecha=test_mecha_snapshot.model_dump(mode='json'),
                metadata=SaveMetadata(summary=f"存档{slot_id}", last_area="测试", play_time=0)
            )
            await async_client.post(
                "/api/user/saves",
                headers=auth_headers,
                json={
                    "slot_id": slot_id,
                    "save_name": f"存档{slot_id}",
                    "save_data": save_data.model_dump()
                }
            )

        # 获取存档列表以找到 ID
        list_response = await async_client.get("/api/user/saves", headers=auth_headers)
        saves = list_response.json()

        # 设置第二个存档为出战
        response = await async_client.post(
            f"/api/user/saves/{saves[1]['id']}/deploy",
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_deployed"] is True

    @pytest.mark.asyncio
    async def test_get_deployed_mecha(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_mecha_snapshot: MechaSnapshot
    ):
        """测试获取出战存档机体数据"""
        # 创建并设置出战存档
        save_data = SaveData(
            version="1.0",
            mecha=test_mecha_snapshot.model_dump(mode='json'),
            metadata=SaveMetadata(summary="出战", last_area="测试", play_time=0)
        )
        create_response = await async_client.post(
            "/api/user/saves",
            headers=auth_headers,
            json={
                "slot_id": 1,
                "save_name": "出战存档",
                "save_data": save_data.model_dump()
            }
        )
        save_id = create_response.json()["id"]

        # 设为出战
        await async_client.post(f"/api/user/saves/{save_id}/deploy", headers=auth_headers)

        # 获取出战机体
        response = await async_client.get("/api/user/saves/deployed/mecha", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "save_id" in data
        assert "mecha" in data
        assert data["mecha"]["instance_id"] == test_mecha_snapshot.instance_id

    @pytest.mark.asyncio
    async def test_access_other_user_save_forbidden(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_mecha_snapshot: MechaSnapshot
    ):
        """测试访问其他用户存档被拒绝"""
        # 创建第一个用户和存档
        save_data = SaveData(
            version="1.0",
            mecha=test_mecha_snapshot.model_dump(mode='json'),
            metadata=SaveMetadata(summary="用户1", last_area="测试", play_time=0)
        )
        create_response = await async_client.post(
            "/api/user/saves",
            headers=auth_headers,
            json={
                "slot_id": 1,
                "save_name": "用户1的存档",
                "save_data": save_data.model_dump()
            }
        )
        save_id = create_response.json()["id"]

        # 注册第二个用户
        await async_client.post(
            "/api/user/register",
            json={"username": "user2", "password": "pass123"}
        )
        login_response = await async_client.post(
            "/api/user/login",
            json={"username": "user2", "password": "pass123"}
        )
        token2 = login_response.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        # 用户2尝试访问用户1的存档
        response = await async_client.get(
            f"/api/user/saves/{save_id}",
            headers=headers2
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unauthorized_access_saves(self, async_client: AsyncClient):
        """测试未认证访问存档接口被拒绝"""
        response = await async_client.get("/api/user/saves")
        assert response.status_code == 401


# ============================================================================
# 战斗接口可选认证测试
# ============================================================================

class TestBattleOptionalAuth:
    """战斗接口可选认证测试"""

    @pytest.mark.asyncio
    async def test_battle_simulate_no_auth(self, async_client: AsyncClient):
        """测试未认证用户可以模拟战斗"""
        response = await async_client.post(
            "/battle/simulate",
            json={"mecha_a_id": "rx78", "mecha_b_id": "zaku"}
        )

        # 可能返回 200 或 404，取决于数据是否存在
        # 但不应该返回 401 (认证错误)
        assert response.status_code in [200, 404, 500]

    @pytest.mark.asyncio
    async def test_battle_simulate_with_auth(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        test_mecha_snapshot: MechaSnapshot
    ):
        """测试已认证用户可以模拟战斗"""
        # 设置出战存档
        save_data = SaveData(
            version="1.0",
            mecha=test_mecha_snapshot.model_dump(mode='json'),
            metadata=SaveMetadata(summary="出战", last_area="测试", play_time=0)
        )
        create_response = await async_client.post(
            "/api/user/saves",
            headers=auth_headers,
            json={
                "slot_id": 1,
                "save_name": "出战存档",
                "save_data": save_data.model_dump()
            }
        )
        save_id = create_response.json()["id"]
        await async_client.post(f"/api/user/saves/{save_id}/deploy", headers=auth_headers)

        # 使用出战存档模拟战斗
        response = await async_client.post(
            "/battle/simulate",
            headers=auth_headers,
            json={
                "mecha_a_id": "rx78",
                "mecha_b_id": "zaku",
                "use_user_save_for_a": True
            }
        )

        # 可能返回 200 或 404/500，但不应该返回 401
        assert response.status_code in [200, 404, 500]
