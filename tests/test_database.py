"""
数据库与用户系统测试

测试内容:
- UserRepository: 用户创建、查询、认证
- GameSaveRepository: 存档 CRUD、出战管理
- MechaSnapshot 序列化/反序列化
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import User, GameSave
from src.user.schemas import UserCreate, GameSaveCreate, SaveData, SaveMetadata
from src.user.repository import UserRepository, GameSaveRepository
from src.user.security import hash_password, verify_password
from src.models import MechaSnapshot


# ============================================================================
# 用户安全功能测试
# ==============================================================================

class TestPasswordSecurity:
    """密码哈希与验证测试 (标记为 slow，因 bcrypt 是有意设计的慢速算法)"""

    @pytest.mark.slow
    def test_hash_password(self):
        """测试密码哈希"""
        password = "test123"
        hashed = hash_password(password)

        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt 前缀

    def test_verify_password_correct(self):
        """测试正确密码验证"""
        password = "test123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_wrong(self):
        """测试错误密码验证"""
        password = "test123"
        wrong = "wrong123"
        hashed = hash_password(password)

        assert verify_password(wrong, hashed) is False


# ============================================================================
# UserRepository 测试
# ============================================================================

class TestUserRepository:
    """用户数据访问层测试"""

    @pytest.mark.asyncio
    async def test_create_user(self, db_session: AsyncSession, test_user_data: UserCreate):
        """测试创建用户"""
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        assert user.id is not None
        assert user.username == test_user_data.username
        assert user.email == test_user_data.email
        assert user.status == "active"
        assert user.password_hash != test_user_data.password
        assert verify_password(test_user_data.password, user.password_hash)

    @pytest.mark.asyncio
    async def test_create_user_duplicate_username(self, db_session: AsyncSession, test_user_data: UserCreate):
        """测试重复用户名"""
        # 创建第一个用户
        await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        # 尝试创建重复用户名
        with pytest.raises(ValueError, match="已存在"):
            await UserRepository.create(db_session, test_user_data)

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, db_session: AsyncSession, test_user_data: UserCreate):
        """测试根据 ID 获取用户"""
        created = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        user = await UserRepository.get_by_id(db_session, created.id)

        assert user is not None
        assert user.id == created.id
        assert user.username == test_user_data.username

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, db_session: AsyncSession):
        """测试获取不存在的用户 ID"""
        user = await UserRepository.get_by_id(db_session, 99999)
        assert user is None

    @pytest.mark.asyncio
    async def test_get_user_by_username(self, db_session: AsyncSession, test_user_data: UserCreate):
        """测试根据用户名获取用户"""
        created = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        user = await UserRepository.get_by_username(db_session, test_user_data.username)

        assert user is not None
        assert user.id == created.id
        assert user.username == test_user_data.username

    @pytest.mark.asyncio
    async def test_get_user_by_username_not_found(self, db_session: AsyncSession):
        """测试获取不存在的用户名"""
        user = await UserRepository.get_by_username(db_session, "nonexistent")
        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_success(self, db_session: AsyncSession, test_user_data: UserCreate):
        """测试成功认证"""
        await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        user = await UserRepository.authenticate(
            db_session,
            test_user_data.username,
            test_user_data.password
        )

        assert user is not None
        assert user.username == test_user_data.username

    @pytest.mark.asyncio
    async def test_authenticate_wrong_password(self, db_session: AsyncSession, test_user_data: UserCreate):
        """测试错误密码认证"""
        await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        user = await UserRepository.authenticate(
            db_session,
            test_user_data.username,
            "wrongpassword"
        )

        assert user is None

    @pytest.mark.asyncio
    async def test_authenticate_nonexistent_user(self, db_session: AsyncSession):
        """测试不存在的用户认证"""
        user = await UserRepository.authenticate(
            db_session,
            "nonexistent",
            "password"
        )

        assert user is None


# ============================================================================
# GameSaveRepository 测试
# ============================================================================

class TestGameSaveRepository:
    """游戏存档数据访问层测试"""

    @pytest.mark.asyncio
    async def test_create_save(
        self,
        db_session: AsyncSession,
        test_user_data: UserCreate,
        test_save_data: SaveData
    ):
        """测试创建存档"""
        # 创建用户
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        # 创建存档
        save_create = GameSaveCreate(
            slot_id=1,
            save_name="测试存档",
            save_data=test_save_data
        )
        save = await GameSaveRepository.create(db_session, user.id, save_create)
        await db_session.commit()

        assert save.id is not None
        assert save.user_id == user.id
        assert save.slot_id == 1
        assert save.save_name == "测试存档"
        assert save.is_deployed is False
        assert save.save_data["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_create_save_duplicate_slot(
        self,
        db_session: AsyncSession,
        test_user_data: UserCreate,
        test_save_data: SaveData
    ):
        """测试重复存档位"""
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        save_create = GameSaveCreate(
            slot_id=1,
            save_name="第一个存档",
            save_data=test_save_data
        )
        await GameSaveRepository.create(db_session, user.id, save_create)
        await db_session.commit()

        # 尝试在同一位置创建第二个存档
        save_create_2 = GameSaveCreate(
            slot_id=1,
            save_name="第二个存档",
            save_data=test_save_data
        )
        with pytest.raises(ValueError, match="已被占用"):
            await GameSaveRepository.create(db_session, user.id, save_create_2)

    @pytest.mark.asyncio
    async def test_get_save_by_id(
        self,
        db_session: AsyncSession,
        test_user_data: UserCreate,
        test_save_data: SaveData
    ):
        """测试根据 ID 获取存档"""
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        save_create = GameSaveCreate(
            slot_id=1,
            save_name="测试存档",
            save_data=test_save_data
        )
        created = await GameSaveRepository.create(db_session, user.id, save_create)
        await db_session.commit()

        save = await GameSaveRepository.get_by_id(db_session, created.id)

        assert save is not None
        assert save.id == created.id
        assert save.save_name == "测试存档"

    @pytest.mark.asyncio
    async def test_get_save_by_slot(
        self,
        db_session: AsyncSession,
        test_user_data: UserCreate,
        test_save_data: SaveData
    ):
        """测试根据存档位获取存档"""
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        save_create = GameSaveCreate(
            slot_id=2,
            save_name="存档位2",
            save_data=test_save_data
        )
        await GameSaveRepository.create(db_session, user.id, save_create)
        await db_session.commit()

        save = await GameSaveRepository.get_by_slot(db_session, user.id, 2)

        assert save is not None
        assert save.slot_id == 2
        assert save.save_name == "存档位2"

    @pytest.mark.asyncio
    async def test_list_saves_by_user(
        self,
        db_session: AsyncSession,
        test_user_data: UserCreate,
        test_save_data: SaveData
    ):
        """测试获取用户所有存档"""
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        # 创建多个存档
        for slot_id in [1, 2, 3]:
            save_create = GameSaveCreate(
                slot_id=slot_id,
                save_name=f"存档{slot_id}",
                save_data=test_save_data
            )
            await GameSaveRepository.create(db_session, user.id, save_create)
        await db_session.commit()

        saves = await GameSaveRepository.list_by_user(db_session, user.id)

        assert len(saves) == 3
        assert saves[0].slot_id == 1
        assert saves[1].slot_id == 2
        assert saves[2].slot_id == 3

    @pytest.mark.asyncio
    async def test_update_save(
        self,
        db_session: AsyncSession,
        test_user_data: UserCreate,
        test_save_data: SaveData
    ):
        """测试更新存档"""
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        save_create = GameSaveCreate(
            slot_id=1,
            save_name="原名",
            save_data=test_save_data
        )
        created = await GameSaveRepository.create(db_session, user.id, save_create)
        await db_session.commit()

        # 更新名称和出战状态
        updated = await GameSaveRepository.update(
            db_session,
            created.id,
            save_name="新名称",
            is_deployed=True
        )
        await db_session.commit()

        assert updated.save_name == "新名称"
        assert updated.is_deployed is True

    @pytest.mark.asyncio
    async def test_set_deployed(
        self,
        db_session: AsyncSession,
        test_user_data: UserCreate,
        test_save_data: SaveData
    ):
        """测试设置出战存档"""
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        # 创建两个存档
        save1 = GameSaveCreate(slot_id=1, save_name="存档1", save_data=test_save_data)
        save2 = GameSaveCreate(slot_id=2, save_name="存档2", save_data=test_save_data)
        created1 = await GameSaveRepository.create(db_session, user.id, save1)
        created2 = await GameSaveRepository.create(db_session, user.id, save2)
        await db_session.commit()

        # 设置存档2为出战
        deployed = await GameSaveRepository.set_deployed(db_session, user.id, created2.id)
        await db_session.commit()

        # 验证存档2是出战状态
        assert deployed.id == created2.id
        assert deployed.is_deployed is True

        # 验证存档1不是出战状态
        save1_check = await GameSaveRepository.get_by_id(db_session, created1.id)
        assert save1_check.is_deployed is False

    @pytest.mark.asyncio
    async def test_get_deployed(
        self,
        db_session: AsyncSession,
        test_user_data: UserCreate,
        test_save_data: SaveData
    ):
        """测试获取出战存档"""
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        save_create = GameSaveCreate(slot_id=1, save_name="出战存档", save_data=test_save_data)
        created = await GameSaveRepository.create(db_session, user.id, save_create)
        await db_session.commit()

        # 设置为出战
        await GameSaveRepository.set_deployed(db_session, user.id, created.id)
        await db_session.commit()

        # 获取出战存档
        deployed = await GameSaveRepository.get_deployed(db_session, user.id)

        assert deployed is not None
        assert deployed.id == created.id
        assert deployed.is_deployed is True

    @pytest.mark.asyncio
    async def test_delete_save(
        self,
        db_session: AsyncSession,
        test_user_data: UserCreate,
        test_save_data: SaveData
    ):
        """测试删除存档"""
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        save_create = GameSaveCreate(slot_id=1, save_name="待删除", save_data=test_save_data)
        created = await GameSaveRepository.create(db_session, user.id, save_create)
        await db_session.commit()

        # 删除存档
        success = await GameSaveRepository.delete(db_session, created.id)
        await db_session.commit()

        assert success is True

        # 验证已删除
        deleted = await GameSaveRepository.get_by_id(db_session, created.id)
        assert deleted is None


# ============================================================================
# MechaSnapshot 序列化测试
# ============================================================================

class TestMechaSnapshotSerialization:
    """MechaSnapshot 序列化/反序列化测试"""

    @pytest.mark.asyncio
    async def test_to_mecha_snapshot(
        self,
        db_session: AsyncSession,
        test_user_data: UserCreate,
        test_mecha_snapshot: MechaSnapshot
    ):
        """测试从存档还原 MechaSnapshot"""
        # 创建用户和存档
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        from src.user.schemas import SaveData
        save_data = SaveData(
            version="1.0",
            mecha=test_mecha_snapshot.model_dump(mode='json'),
            metadata=SaveMetadata(summary="测试", last_area="测试区", play_time=0)
        )

        save_create = GameSaveCreate(slot_id=1, save_name="测试", save_data=save_data)
        created = await GameSaveRepository.create(db_session, user.id, save_create)
        await db_session.commit()

        # 从存档还原
        restored = GameSaveRepository.to_mecha_snapshot(created)

        assert isinstance(restored, MechaSnapshot)
        assert restored.instance_id == test_mecha_snapshot.instance_id
        assert restored.mecha_name == test_mecha_snapshot.mecha_name
        assert restored.final_max_hp == test_mecha_snapshot.final_max_hp
        assert restored.current_hp == test_mecha_snapshot.current_hp

    @pytest.mark.asyncio
    async def test_invalid_save_data_raises_error(self, db_session: AsyncSession, test_user_data: UserCreate):
        """测试无效存档数据抛出异常"""
        user = await UserRepository.create(db_session, test_user_data)
        await db_session.commit()

        # 创建包含无效数据的存档（使用无效的数据类型）
        from src.user.schemas import SaveData
        save_data = SaveData(
            version="1.0",
            mecha={"final_max_hp": "invalid_type"},  # 无效数据类型
            metadata=SaveMetadata(summary="测试", last_area="测试区", play_time=0)
        )

        save_create = GameSaveCreate(slot_id=1, save_name="无效存档", save_data=save_data)
        created = await GameSaveRepository.create(db_session, user.id, save_create)
        await db_session.commit()

        # 尝试还原应该抛出异常
        with pytest.raises(ValueError, match="存档数据无效"):
            GameSaveRepository.to_mecha_snapshot(created)
