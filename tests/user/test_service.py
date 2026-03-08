"""
测试 MothershipService (用户业务逻辑层)

覆盖购买母舰和切换母舰的完整业务流程。
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.user.service import MothershipService
from src.user.security import hash_password
from src.database.models import User, UserMothership
from src.loader import DataLoader
from src.models import MothershipConfig


@pytest.fixture
async def service_test_user(db_session: AsyncSession) -> User:
    """创建测试用户（带默认母舰）"""
    user = User(
        username="service_tester",
        password_hash=hash_password("password123"),
    )
    db_session.add(user)
    await db_session.flush()

    # 手动创建默认母舰记录（模拟 UserRepository.create 的行为）
    from src.user.repository import MothershipRepository
    await MothershipRepository.create_default(db_session, user.id)

    return user


@pytest.fixture
def mock_loader() -> DataLoader:
    """模拟数据加载器"""
    loader = DataLoader()
    # 添加测试用的母舰配置
    loader.motherships = {
        "light_corvette": MothershipConfig(
            id="light_corvette",
            name="轻型护卫舰",
            generation=1,
            tier="common",
            engine_level=1,
            hp_regen_per_min=10,
            en_regen_per_min=5,
            region_level=1,
            cargo_capacity=100,
            emergency_extraction_tax=0.3,
            price=1000,
        ),
        "medium_frigate": MothershipConfig(
            id="medium_frigate",
            name="中型护卫舰",
            generation=2,
            tier="rare",
            engine_level=2,
            hp_regen_per_min=20,
            en_regen_per_min=10,
            region_level=2,
            cargo_capacity=200,
            emergency_extraction_tax=0.2,
            price=5000,
            # 无前置条件，可直接购买
        ),
        "heavy_cruiser": MothershipConfig(
            id="heavy_cruiser",
            name="重型巡洋舰",
            generation=2,
            tier="rare",
            engine_level=2,
            hp_regen_per_min=20,
            en_regen_per_min=10,
            region_level=2,
            cargo_capacity=200,
            emergency_extraction_tax=0.2,
            price=5000,
            required_chapter=5,  # 需要章节5
        ),
        "achievement_battleship": MothershipConfig(
            id="achievement_battleship",
            name="成就战列舰",
            generation=3,
            tier="epic",
            engine_level=3,
            hp_regen_per_min=30,
            en_regen_per_min=15,
            region_level=3,
            cargo_capacity=300,
            emergency_extraction_tax=0.1,
            price=10000,
            required_achievement="victory_100",  # 需要成就
        ),
    }
    return loader


@pytest.mark.asyncio
async def test_purchase_mothership_success(db_session: AsyncSession, service_test_user: User, mock_loader: DataLoader):
    """测试成功购买母舰"""
    result = await MothershipService.purchase_mothership(
        db_session, service_test_user, "medium_frigate", mock_loader
    )

    assert result is not None
    assert "medium_frigate" in result.data.get("owned_ids", [])
    assert result.data["current_id"] == "medium_frigate"


@pytest.mark.asyncio
async def test_purchase_mothership_invalid_id(db_session: AsyncSession, service_test_user: User, mock_loader: DataLoader):
    """测试购买无效的母舰ID"""
    with pytest.raises(ValueError, match="无效的母舰型号"):
        await MothershipService.purchase_mothership(
            db_session, service_test_user, "invalid_id", mock_loader
        )


@pytest.mark.asyncio
async def test_purchase_mothership_already_owned(db_session: AsyncSession, service_test_user: User, mock_loader: DataLoader):
    """测试购买已拥有的母舰"""
    # 先购买一次
    await MothershipService.purchase_mothership(
        db_session, service_test_user, "medium_frigate", mock_loader
    )

    # 再次购买应该失败
    with pytest.raises(ValueError, match="玩家已拥有该母舰"):
        await MothershipService.purchase_mothership(
            db_session, service_test_user, "medium_frigate", mock_loader
        )


@pytest.mark.asyncio
async def test_purchase_mothership_insufficient_credits(db_session: AsyncSession, service_test_user: User, mock_loader: DataLoader):
    """测试信用点不足"""
    # 直接在 User 对象上设置 credits 属性
    # service.py 中使用 getattr(user, "credits", 9999999)，有属性时会返回实际值
    service_test_user.credits = 100  # 只有100，但需要5000

    with pytest.raises(ValueError, match="信用点不足"):
        await MothershipService.purchase_mothership(
            db_session, service_test_user, "medium_frigate", mock_loader
        )


@pytest.mark.asyncio
async def test_purchase_mothership_chapter_requirement(db_session: AsyncSession, service_test_user: User, mock_loader: DataLoader):
    """测试章节前置条件"""
    with pytest.raises(ValueError, match="购买失败。需通关第 5 章节"):
        await MothershipService.purchase_mothership(
            db_session, service_test_user, "heavy_cruiser", mock_loader
        )


@pytest.mark.asyncio
async def test_purchase_mothership_achievement_requirement(db_session: AsyncSession, service_test_user: User, mock_loader: DataLoader):
    """测试成就前置条件"""
    with pytest.raises(ValueError, match="购买失败。需达成成就"):
        await MothershipService.purchase_mothership(
            db_session, service_test_user, "achievement_battleship", mock_loader
        )


@pytest.mark.asyncio
async def test_switch_mothership_success(db_session: AsyncSession, service_test_user: User, mock_loader: DataLoader):
    """测试成功切换母舰"""
    # 先购买第二艘母舰
    await MothershipService.purchase_mothership(
        db_session, service_test_user, "medium_frigate", mock_loader
    )

    # 切换回默认母舰
    result = await MothershipService.switch_mothership(
        db_session, service_test_user.id, "light_corvette"
    )

    assert result is not None
    assert result.data["current_id"] == "light_corvette"


@pytest.mark.asyncio
async def test_switch_mothership_not_owned(db_session: AsyncSession, service_test_user: User, mock_loader: DataLoader):
    """测试切换未拥有的母舰"""
    # 用户只有默认的 light_corvette，尝试切换到未拥有的母舰
    with pytest.raises(ValueError, match="玩家未拥有该母舰"):
        await MothershipService.switch_mothership(
            db_session, service_test_user.id, "medium_frigate"
        )
