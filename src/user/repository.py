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
from sqlalchemy.orm.attributes import flag_modified
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
            
            # --- 初始化默认母舰 ---
            await MothershipRepository.create_default(session, db_user.id)
            
            return db_user
        except IntegrityError:
            await session.rollback()
            raise ValueError(f"用户名 '{user_data.username}' 已存在")

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: int, for_update: bool = False) -> Optional[User]:
        """
        根据 ID 获取用户

        检查软删除状态，已删除的用户返回 None

        Args:
            session: 数据库会话
            user_id: 用户 ID
            for_update: 是否加行锁（并发写同用户状态的场景，如领取初始机体）

        Returns:
            用户对象，不存在或已删除返回 None
        """
        stmt = select(User).where(
            and_(User.id == user_id, User.deleted_at.is_(None))
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await session.execute(stmt)
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

from src.database.models import UserMecha, UserPilot, UserEquipment, UserSquad, BattleRecord, UserMothership

class MothershipRepository:
    """母舰数据访问类"""

    @staticmethod
    async def get_by_user_id(session: AsyncSession, user_id: int, for_update: bool = False) -> Optional[UserMothership]:
        stmt = select(UserMothership).where(UserMothership.user_id == user_id)
        if for_update:
            # 行锁读保证读最新已提交版本：identity map 不回填已加载属性
            # （User.mothership selectin 常使本行早已入缓存），行锁等待横跨
            # 他人提交后必须重读，锁后复查才不拿旧 owned_ids（同
            # item_system._get_user 手法，单点维护）。调用方须先 flush：
            # autoflush=False 下未落库改动会被 populate_existing 静默丢弃。
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_default(session: AsyncSession, user_id: int) -> UserMothership:
        """为新用户初始化默认母舰"""
        db_mothership = UserMothership(
            user_id=user_id,
            data={
                "owned_ids": ["light_corvette"],
                "current_id": "light_corvette",
                "switch_count_today": 0,
                "last_switch_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")
            }
        )
        session.add(db_mothership)
        await session.flush()
        await session.refresh(db_mothership)
        return db_mothership

    @staticmethod
    async def purchase_mothership(session: AsyncSession, user_id: int, new_mothership_id: str, cost: int) -> Optional[UserMothership]:
        # 使用行锁防止并发购买导致的数据覆盖
        db_mothership = await MothershipRepository.get_by_user_id(session, user_id, for_update=True)
        if not db_mothership:
            return None
        
        # NOTE: 扣除信用点等逻辑应当在上层 Service 的事务中处理
        data = dict(db_mothership.data)
        if new_mothership_id not in data.get("owned_ids", []):
            data.setdefault("owned_ids", []).append(new_mothership_id)
        
        data["current_id"] = new_mothership_id
        db_mothership.data = data
        
        # 触发 sqlalchemy JSON 更新
        flag_modified(db_mothership, "data")
        
        await session.flush()
        await session.refresh(db_mothership)
        return db_mothership

    @staticmethod
    async def switch_mothership(session: AsyncSession, user_id: int, target_id: str) -> Optional[UserMothership]:
        # 使用行锁防止并发切换绕过次数限制
        db_mothership = await MothershipRepository.get_by_user_id(session, user_id, for_update=True)
        if not db_mothership:
            return None
            
        data = dict(db_mothership.data)
        if target_id not in data.get("owned_ids", []):
            raise ValueError(f"玩家未拥有该母舰: {target_id}")
            
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if data.get("last_switch_date") != today_str:
            data["switch_count_today"] = 0
            data["last_switch_date"] = today_str
            
        if data.get("switch_count_today", 0) >= 3:
            raise ValueError("今日切换母舰次数已达上限")
            
        data["current_id"] = target_id
        data["switch_count_today"] = data.get("switch_count_today", 0) + 1
        
        db_mothership.data = data
        
        # 触发 sqlalchemy JSON 更新
        flag_modified(db_mothership, "data")

        await session.flush()
        await session.refresh(db_mothership)
        return db_mothership

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
        """按持有先后（id 升序）列出玩家机体——战斗装配取「持有首台」的次序依据（2026-09-22）。"""
        result = await session.execute(
            select(UserMecha)
            .where(UserMecha.user_id == user_id)
            .order_by(UserMecha.id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_user_mecha_ids(session: AsyncSession, user_id: int) -> set:
        """当前用户名下机体 ID 集合（ID 投影：归属校验只需 ID，不整行水合）"""
        result = await session.execute(
            select(UserMecha.id).where(UserMecha.user_id == user_id)
        )
        return set(result.scalars().all())

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
        # first() 而非 scalar_one_or_none()：存量数据可能出现双 is_active，
        # 后者抛 MultipleResultsFound（500），绕过调用方的未就绪 400 语义
        return result.scalars().first()

    @staticmethod
    async def list_user_squads(session: AsyncSession, user_id: int) -> List[UserSquad]:
        result = await session.execute(
            select(UserSquad).where(UserSquad.user_id == user_id)
        )
        return list(result.scalars().all())

    @staticmethod
    async def set_active_squad(session: AsyncSession, user_id: int, squad_id: int) -> Optional[UserSquad]:
        # 清除该用户所有其他出战小队的状态
        await session.execute(
            update(UserSquad)
            .where(and_(UserSquad.user_id == user_id, UserSquad.is_active == True))
            .values(is_active=False)
        )

        # 将选中编队设为 Active（user_id 过滤：仅凭 squad_id 会激活他人编队，
        # Doc 7 v2.2 §11.5 现状修补项）
        result = await session.execute(
            select(UserSquad).where(
                and_(UserSquad.id == squad_id, UserSquad.user_id == user_id)
            )
        )
        db_squad = result.scalar_one_or_none()

        if db_squad:
            db_squad.is_active = True
            db_squad.updated_at = datetime.now(timezone.utc)
            await session.flush()
            await session.refresh(db_squad)

        return db_squad

# --- Equipment (装备) 系列操作 ---

    @staticmethod
    async def get_equipments_by_mecha(
        session: AsyncSession, user_mecha_id: int
    ) -> List[UserEquipment]:
        result = await session.execute(
            select(UserEquipment).where(UserEquipment.equipped_mecha_id == user_mecha_id)
        )
        return list(result.scalars().all())

    # --- Battle Records

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
