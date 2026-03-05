"""
用户数据访问层 (Repository Pattern)

封装所有数据库操作，提供类型安全的数据访问接口。

设计原则:
- 使用 SQLAlchemy 异步查询
- 与 MechaFactory 集成，支持运行时状态还原
- 复用 src/models.py 的 Pydantic 模型进行序列化/反序列化
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, update
from sqlalchemy.exc import IntegrityError
from typing import Optional, List
from datetime import datetime, timezone

from src.database.models import User, GameSave
from src.user.schemas import UserCreate, UserResponse, GameSaveCreate, GameSaveResponse, SaveData
from src.user.security import hash_password, verify_password
from src.models import MechaSnapshot

# ==============================================================================
# 用户 Repository
# ==============================================================================

class UserRepository:
    """用户数据访问类"""

    @staticmethod
    async def create(session: AsyncSession, user_data: UserCreate) -> User:
        """
        创建新用户

        Args:
            session: 数据库会话
            user_data: 用户注册数据

        Returns:
            创建的用户对象

        Raises:
            ValueError: 用户名已存在
        """
        hashed_pwd = hash_password(user_data.password)

        db_user = User(
            username=user_data.username,
            password_hash=hashed_pwd,
            email=user_data.email,
            status="active",
        )

        try:
            session.add(db_user)
            await session.flush()
            await session.refresh(db_user)
            return db_user
        except IntegrityError:
            await session.rollback()
            raise ValueError(f"用户名 '{user_data.username}' 已存在")

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
        """
        根据 ID 获取用户

        检查软删除状态，已删除的用户返回 None

        Args:
            session: 数据库会话
            user_id: 用户 ID

        Returns:
            用户对象，不存在或已删除返回 None
        """
        result = await session.execute(
            select(User).where(
                and_(User.id == user_id, User.deleted_at.is_(None))
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_username(session: AsyncSession, username: str) -> Optional[User]:
        """
        根据用户名获取用户

        自动过滤已软删除的用户

        Args:
            session: 数据库会话
            username: 用户名

        Returns:
            用户对象，不存在或已删除返回 None
        """
        result = await session.execute(
            select(User).where(
                and_(User.username == username, User.deleted_at.is_(None))
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def authenticate(session: AsyncSession, username: str, password: str) -> Optional[User]:
        """
        验证用户凭据

        Args:
            session: 数据库会话
            username: 用户名
            password: 明文密码

        Returns:
            验证成功返回用户对象，失败返回 None
        """
        user = await UserRepository.get_by_username(session, username)
        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

# ==============================================================================
# 游戏存档 Repository
# ==============================================================================

class GameSaveRepository:
    """游戏存档数据访问类"""

    @staticmethod
    async def create(
        session: AsyncSession,
        user_id: int,
        save_data: GameSaveCreate,
    ) -> GameSave:
        """
        创建新存档

        Args:
            session: 数据库会话
            user_id: 用户 ID
            save_data: 存档数据

        Returns:
            创建的存档对象

        Raises:
            ValueError: 存档位已被占用
        """
        # 检查存档位是否已被占用
        existing = await GameSaveRepository.get_by_slot(session, user_id, save_data.slot_id)
        if existing:
            raise ValueError(f"存档位 {save_data.slot_id} 已被占用")

        # 创建新存档
        db_save = GameSave(
            user_id=user_id,
            slot_id=save_data.slot_id,
            save_name=save_data.save_name,
            save_data=save_data.save_data.model_dump(),
            is_deployed=False,
        )

        session.add(db_save)
        await session.flush()
        await session.refresh(db_save)
        return db_save

    @staticmethod
    async def get_by_id(session: AsyncSession, save_id: int) -> Optional[GameSave]:
        """
        根据 ID 获取存档

        Args:
            session: 数据库会话
            save_id: 存档 ID

        Returns:
            存档对象，不存在返回 None
        """
        result = await session.execute(
            select(GameSave).where(GameSave.id == save_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_slot(session: AsyncSession, user_id: int, slot_id: int) -> Optional[GameSave]:
        """
        获取用户指定存档位的存档

        Args:
            session: 数据库会话
            user_id: 用户 ID
            slot_id: 存档位 (1-3)

        Returns:
            存档对象，不存在返回 None
        """
        result = await session.execute(
            select(GameSave).where(
                and_(GameSave.user_id == user_id, GameSave.slot_id == slot_id)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_by_user(session: AsyncSession, user_id: int) -> List[GameSave]:
        """
        获取用户所有存档

        按存档位 (slot_id) 升序排列

        Args:
            session: 数据库会话
            user_id: 用户 ID

        Returns:
            存档对象列表
        """
        result = await session.execute(
            select(GameSave)
            .where(GameSave.user_id == user_id)
            .order_by(GameSave.slot_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_deployed(session: AsyncSession, user_id: int) -> Optional[GameSave]:
        """
        获取用户的出战存档

        Args:
            session: 数据库会话
            user_id: 用户 ID

        Returns:
            出战存档对象，未设置返回 None
        """
        result = await session.execute(
            select(GameSave).where(
                and_(GameSave.user_id == user_id, GameSave.is_deployed == True)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update(
        session: AsyncSession,
        save_id: int,
        save_name: Optional[str] = None,
        is_deployed: Optional[bool] = None,
        save_data: Optional[SaveData] = None,
    ) -> Optional[GameSave]:
        """
        更新存档

        Args:
            session: 数据库会话
            save_id: 存档 ID
            save_name: 新存档名称（可选）
            is_deployed: 是否设为出战（可选）
            save_data: 新存档数据（可选）

        Returns:
            更新后的存档对象，不存在则返回 None
        """
        db_save = await GameSaveRepository.get_by_id(session, save_id)
        if not db_save:
            return None

        # 更新字段
        if save_name is not None:
            db_save.save_name = save_name
        if is_deployed is not None:
            db_save.is_deployed = is_deployed
        if save_data is not None:
            db_save.save_data = save_data.model_dump()

        # 使用 datetime.now(timezone.utc) 替代已弃用的 datetime.utcnow()
        db_save.updated_at = datetime.now(timezone.utc)
        await session.flush()
        await session.refresh(db_save)
        return db_save

    @staticmethod
    async def set_deployed(session: AsyncSession, user_id: int, save_id: int) -> Optional[GameSave]:
        """
        设置指定存档为出战存档

        会自动取消该用户其他存档的出战状态。
        使用单条 UPDATE 语句实现，比循环更高效。

        Args:
            session: 数据库会话
            user_id: 用户 ID
            save_id: 存档 ID

        Returns:
            更新后的存档对象，不存在返回 None
        """
        # 使用一条 UPDATE 语句取消用户所有存档的出战状态
        await session.execute(
            update(GameSave)
            .where(and_(GameSave.user_id == user_id, GameSave.is_deployed == True))
            .values(is_deployed=False)
        )

        # 设置目标存档为出战
        db_save = await GameSaveRepository.update(session, save_id, is_deployed=True)
        return db_save

    @staticmethod
    async def delete(session: AsyncSession, save_id: int) -> bool:
        """
        删除存档

        Args:
            session: 数据库会话
            save_id: 存档 ID

        Returns:
            是否删除成功
        """
        db_save = await GameSaveRepository.get_by_id(session, save_id)
        if not db_save:
            return False

        await session.delete(db_save)
        return True

    @staticmethod
    def to_mecha_snapshot(save: GameSave) -> MechaSnapshot:
        """
        从存档数据还原 MechaSnapshot 对象

        通过 Pydantic 反序列化后，使用 TraitManager 重新注入运行时状态（Effects）。
        这确保了从存档加载的机体拥有完整的技能效果，可以参与战斗计算。

        Args:
            save: 存档对象

        Returns:
            MechaSnapshot 运行时对象，包含完整的 effects 列表

        Raises:
            ValueError: 存档数据无效
        """
        from src.skills import TraitManager

        try:
            mecha_data = save.save_data.get("mecha", {})

            # 使用 model_validate 进行 Pydantic 反序列化
            mecha = MechaSnapshot.model_validate(mecha_data)

            # 通过 TraitManager 重新注入运行时状态
            # 将 skills 列表中的技能 ID 转换为实际的 Effect 对象
            TraitManager.apply_traits(mecha)

            return mecha

        except Exception as e:
            raise ValueError(f"存档数据无效: {e}")
