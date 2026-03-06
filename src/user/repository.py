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

from src.database.models import User
from src.user.schemas import UserCreate, UserResponse
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
# 用户资产 Repository (User Assets - Mixed Relational Architecture)
# ==============================================================================

from src.database.models import UserMecha, UserPilot, UserEquipment, UserSquad, BattleRecord

class UserAssetRepository:
    """用户资产数据访问类 (替代了旧的 GameSaveRepository)"""

    # --- Mecha (机体) 系列操作 ---

    @staticmethod
    async def create_user_mecha(
        session: AsyncSession, user_id: int, mech_id: str, nickname: str = ""
    ) -> UserMecha:
        db_mecha = UserMecha(
            user_id=user_id,
            mech_id=mech_id,
            nickname=nickname,
            upgrades={"hp": 0, "en": 0, "armor": 0, "mobility": 0}
        )
        session.add(db_mecha)
        await session.flush()
        await session.refresh(db_mecha)
        return db_mecha

    @staticmethod
    async def get_user_mecha(session: AsyncSession, user_mecha_id: int) -> Optional[UserMecha]:
        result = await session.execute(
            select(UserMecha).where(UserMecha.id == user_mecha_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_user_mechas(session: AsyncSession, user_id: int) -> List[UserMecha]:
        result = await session.execute(
            select(UserMecha).where(UserMecha.user_id == user_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_mecha_upgrades(
        session: AsyncSession, user_mecha_id: int, upgrades: dict
    ) -> Optional[UserMecha]:
        db_mecha = await UserAssetRepository.get_user_mecha(session, user_mecha_id)
        if not db_mecha:
            return None
        
        db_mecha.upgrades = upgrades
        db_mecha.updated_at = datetime.now(timezone.utc)
        
        await session.flush()
        await session.refresh(db_mecha)
        return db_mecha

    # --- Squad (编队) 系列操作 ---

    @staticmethod
    async def create_user_squad(
        session: AsyncSession, user_id: int, name: str, mecha_ids: List[int]
    ) -> UserSquad:
        db_squad = UserSquad(
            user_id=user_id,
            name=name,
            mecha_ids=mecha_ids,
            is_active=False
        )
        session.add(db_squad)
        await session.flush()
        await session.refresh(db_squad)
        return db_squad

    @staticmethod
    async def get_active_squad(session: AsyncSession, user_id: int) -> Optional[UserSquad]:
        result = await session.execute(
            select(UserSquad).where(
                and_(UserSquad.user_id == user_id, UserSquad.is_active == True)
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def set_active_squad(session: AsyncSession, user_id: int, squad_id: int) -> Optional[UserSquad]:
        # 清除该用户所有其他出战小队的状态
        await session.execute(
            update(UserSquad)
            .where(and_(UserSquad.user_id == user_id, UserSquad.is_active == True))
            .values(is_active=False)
        )
        
        # 将选中编队设为 Active
        result = await session.execute(
            select(UserSquad).where(UserSquad.id == squad_id)
        )
        db_squad = result.scalar_one_or_none()
        
        if db_squad:
            db_squad.is_active = True
            db_squad.updated_at = datetime.now(timezone.utc)
            await session.flush()
            await session.refresh(db_squad)
            
        return db_squad

    # --- Battle Records (回放) 系列操作 ---
    
    @staticmethod
    async def create_battle_record(
        session: AsyncSession, user_id: int, snapshot_data: dict
    ) -> BattleRecord:
        record = BattleRecord(
            user_id=user_id,
            snapshot_data=snapshot_data
        )
        session.add(record)
        await session.flush()
        await session.refresh(record)
        return record
