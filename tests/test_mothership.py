import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import Base, User, UserMothership
from src.user.repository import UserRepository, MothershipRepository
from src.user.schemas import UserCreate

# Setup in-memory sqlite for test
engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
TestingSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

@pytest.fixture(autouse=True)
async def db_session():
    # Setup tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with TestingSessionLocal() as session:
        yield session
    
    # Teardown
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.mark.asyncio
async def test_mothership_create_and_purchase(db_session: AsyncSession):
    # 1. Create User (which should trigger create_default)
    user_data = UserCreate(username="testuser", password="password123")
    user = await UserRepository.create(db_session, user_data)
    
    # 2. Verify default mothership
    ms = await MothershipRepository.get_by_user_id(db_session, user.id)
    assert ms is not None
    assert ms.data["current_id"] == "light_corvette"
    assert "light_corvette" in ms.data["owned_ids"]
    
    # 3. Purchase a new mothership
    purchased_ms = await MothershipRepository.purchase_mothership(db_session, user.id, "cruiser_alpha", cost=200000)
    assert purchased_ms is not None
    assert purchased_ms.data["current_id"] == "cruiser_alpha"
    assert "cruiser_alpha" in purchased_ms.data["owned_ids"]
    assert "light_corvette" in purchased_ms.data["owned_ids"]

    # 4. Switch mothership back
    switched_ms = await MothershipRepository.switch_mothership(db_session, user.id, "light_corvette")
    assert switched_ms is not None
    assert switched_ms.data["current_id"] == "light_corvette"
    assert switched_ms.data["switch_count_today"] == 1
    
    # 5. Switch to unowned mothership should fail
    with pytest.raises(ValueError):
        await MothershipRepository.switch_mothership(db_session, user.id, "unowned_ship")

@pytest.mark.asyncio
async def test_mothership_switch_limit(db_session: AsyncSession):
    user_data = UserCreate(username="limit_testuser", password="password123")
    user = await UserRepository.create(db_session, user_data)
    
    # 给用户多分配飞船，以供切换
    await MothershipRepository.purchase_mothership(db_session, user.id, "cruiser_alpha", cost=0)
    await MothershipRepository.purchase_mothership(db_session, user.id, "cruiser_beta", cost=0)
    
    # 第1次切换
    await MothershipRepository.switch_mothership(db_session, user.id, "cruiser_alpha")
    # 第2次切换
    await MothershipRepository.switch_mothership(db_session, user.id, "cruiser_beta")
    # 第3次切换
    ms = await MothershipRepository.switch_mothership(db_session, user.id, "light_corvette")
    assert ms.data["switch_count_today"] == 3
    
    # 第4次切换，应该被拦截抛错
    with pytest.raises(ValueError, match="今日切换母舰次数已达上限"):
        await MothershipRepository.switch_mothership(db_session, user.id, "cruiser_alpha")
