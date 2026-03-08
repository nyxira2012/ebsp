"""背包系统核心功能测试

测试背包系统的核心逻辑：
1. 容量计算与检查 (Doc 12 §2)
2. 材料堆叠规则 (Doc 12 §2.2)
3. 装备不可堆叠 (Doc 12 §2.2)
4. 已装备装备不计入占用 (Doc 12 §2.2)
5. 超载检测与拦截 (Doc 12 §4.1)
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.database.models import User, UserEquipment, UserItem, UserMothership
from src.user.inventory import InventoryService, MockMothershipProvider
from src.user.schemas import EquipmentData, ItemData, AddResult
from src.user.security import hash_password


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
async def test_user(db_session: AsyncSession):
    """创建测试用户"""
    user = User(
        username="inventory_test_user",
        password_hash=hash_password("password123")
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def user_with_mixed_assets(db_session: AsyncSession):
    """创建拥有混合资产的测试用户"""
    user = User(
        username="mixed_asset_user",
        password_hash=hash_password("password123")
    )
    db_session.add(user)
    await db_session.flush()

    # 添加未装备装备 (占用3格)
    for i in range(3):
        db_session.add(UserEquipment(
            user_id=user.id,
            equipment_id=f"wpn_{i}",
            is_equipped=False
        ))

    # 添加已装备装备 (不占用)
    db_session.add(UserEquipment(
        user_id=user.id,
        equipment_id="wpn_equipped",
        is_equipped=True,
        equipped_mecha_id=1,
        equipped_slot_idx=0
    ))

    # 添加材料 (3种类型 = 3格)
    for item_id in ["mat_alloy", "mat_shard", "mat_crystal"]:
        db_session.add(UserItem(
            user_id=user.id,
            item_id=item_id,
            item_type="material",
            quantity=99
        ))

    await db_session.flush()

    # 初始化母舰 (容量100)
    db_session.add(UserMothership(
        user_id=user.id,
        data={"owned_ids": ["light_corvette"], "current_id": "light_corvette"}
    ))
    await db_session.flush()

    return user


# ============================================================================
# 容量上限计算测试 (Doc 12 §2.1)
# ============================================================================

class TestCapacityCalculation:
    """测试容量上限计算逻辑"""

    @pytest.mark.asyncio
    async def test_mock_provider_fixed_capacity(self, db_session: AsyncSession, test_user):
        """测试Mock提供者返回固定容量"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=150))
        capacity = await service.get_capacity(test_user.id)
        assert capacity == 150

    @pytest.mark.asyncio
    async def test_get_status_aggregates_correctly(self, db_session: AsyncSession, user_with_mixed_assets):
        """测试get_status正确聚合容量和占用"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=100))
        status = await service.get_status(user_with_mixed_assets.id)

        assert status.capacity == 100
        # 3件未装备装备 + 3种材料 = 6格占用
        assert status.current == 6
        assert status.available == 94

    @pytest.mark.asyncio
    async def test_capacity_from_max_mothership(self, db_session: AsyncSession, test_user):
        """测试容量取所有已拥有母舰的最大值"""
        # 创建拥有多个母舰的用户
        db_session.add(UserMothership(
            user_id=test_user.id,
            data={
                "owned_ids": ["small_ship", "medium_ship", "large_ship"],
                "current_id": "small_ship"
            }
        ))
        await db_session.flush()

        # Mock loader返回不同容量的母舰
        class MockLoader:
            motherships = {
                "small_ship": type('obj', (object,), {'cargo_capacity': 80})(),
                "medium_ship": type('obj', (object,), {'cargo_capacity': 150})(),
                "large_ship": type('obj', (object,), {'cargo_capacity': 200})(),
            }

        from src.user.inventory import DatabaseMothershipProvider
        provider = DatabaseMothershipProvider(db_session, MockLoader())
        service = InventoryService(db_session, mothership_provider=provider)

        capacity = await service.get_capacity(test_user.id)
        # 应该返回最大容量
        assert capacity == 200


# ============================================================================
# 占用计算测试 (Doc 12 §2.2)
# ============================================================================

class TestOccupancyCalculation:
    """测试货舱占用计算规则"""

    @pytest.mark.asyncio
    async def test_unequipped_equipment_counts(self, db_session: AsyncSession, test_user):
        """测试未装备装备每件占1格"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=100))

        # 添加5件未装备装备
        for i in range(5):
            db_session.add(UserEquipment(
                user_id=test_user.id,
                equipment_id=f"wpn_{i}",
                is_equipped=False
            ))
        await db_session.flush()

        occupancy = await service.get_occupancy(test_user.id)
        assert occupancy == 5

    @pytest.mark.asyncio
    async def test_equipped_not_counted(self, db_session: AsyncSession, test_user):
        """测试已装备装备不计入占用"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=100))

        # 添加5件装备，其中2件已装备
        for i in range(5):
            db_session.add(UserEquipment(
                user_id=test_user.id,
                equipment_id=f"wpn_{i}",
                is_equipped=(i < 2),  # 前2件已装备
                equipped_mecha_id=1 if i < 2 else None,
                equipped_slot_idx=i if i < 2 else None
            ))
        await db_session.flush()

        occupancy = await service.get_occupancy(test_user.id)
        # 只有3件未装备占用格子
        assert occupancy == 3

    @pytest.mark.asyncio
    async def test_materials_stack_by_type(self, db_session: AsyncSession, test_user):
        """测试材料按类型堆叠，每类占1格"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=100))

        # 添加3种材料，每种数量很大
        db_session.add(UserItem(user_id=test_user.id, item_id="mat_a", item_type="material", quantity=999))
        db_session.add(UserItem(user_id=test_user.id, item_id="mat_b", item_type="material", quantity=500))
        db_session.add(UserItem(user_id=test_user.id, item_id="mat_c", item_type="material", quantity=1))
        await db_session.flush()

        occupancy = await service.get_occupancy(test_user.id)
        # 3种材料 = 3格
        assert occupancy == 3

    @pytest.mark.asyncio
    async def test_mixed_assets_occupancy(self, db_session: AsyncSession, user_with_mixed_assets):
        """测试混合资产占用计算正确性"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=100))

        # fixture已创建: 3件未装备装备 + 1件已装备 + 3种材料
        occupancy = await service.get_occupancy(user_with_mixed_assets.id)

        # 3(未装备) + 3(材料种类) = 6格
        assert occupancy == 6


# ============================================================================
# 超载检测测试 (Doc 12 §4.1)
# ============================================================================

class TestOverflowDetection:
    """测试超载检测逻辑"""

    @pytest.mark.asyncio
    async def test_can_add_with_sufficient_space(self, db_session: AsyncSession, test_user):
        """测试有足够空间时返回True"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=100))

        # 背包空时
        assert await service.can_add(test_user.id, required_slots=50) is True
        assert await service.can_add(test_user.id, required_slots=100) is True
        assert await service.can_add(test_user.id, required_slots=0) is True

    @pytest.mark.asyncio
    async def test_can_add_insufficient_space(self, db_session: AsyncSession, test_user):
        """测试空间不足时返回False"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=10))

        # 先占用8格
        for i in range(8):
            db_session.add(UserEquipment(
                user_id=test_user.id,
                equipment_id=f"wpn_{i}",
                is_equipped=False
            ))
        await db_session.flush()

        # 剩余2格
        assert await service.can_add(test_user.id, required_slots=2) is True
        assert await service.can_add(test_user.id, required_slots=3) is False

    @pytest.mark.asyncio
    async def test_calculate_required_slots_new_items(self, db_session: AsyncSession, test_user):
        """测试计算新增物品所需格子数"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=100))

        # 5件装备 + 3种新材料
        required = await service.calculate_required_slots(
            test_user.id,
            equipments=[EquipmentData(equipment_id=f"wpn_{i}") for i in range(5)],
            items=[
                ItemData(item_id="mat_a"),
                ItemData(item_id="mat_b"),
                ItemData(item_id="mat_c")
            ]
        )

        # 5(装备) + 3(新材料种类) = 8格
        assert required == 8

    @pytest.mark.asyncio
    async def test_calculate_required_slots_existing_items_merge(self, db_session: AsyncSession, test_user):
        """测试已有材料类型不计入新格子"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=100))

        # 先添加2种材料
        db_session.add(UserItem(user_id=test_user.id, item_id="mat_a", item_type="material", quantity=10))
        db_session.add(UserItem(user_id=test_user.id, item_id="mat_b", item_type="material", quantity=10))
        await db_session.flush()

        # 再添加相同材料 + 1种新材料
        required = await service.calculate_required_slots(
            test_user.id,
            equipments=[],
            items=[
                ItemData(item_id="mat_a", quantity=50),  # 已存在，不占新格
                ItemData(item_id="mat_b", quantity=30),  # 已存在，不占新格
                ItemData(item_id="mat_c", quantity=1)    # 新材料，占1格
            ]
        )

        # 只有mat_c占新格子
        assert required == 1


# ============================================================================
# 添加资产与超载拦截 (Doc 12 §4.1)
# ============================================================================

class TestAddAssetsWithOverflow:
    """测试添加资产时的超载拦截"""

    @pytest.mark.asyncio
    async def test_add_assets_success(self, db_session: AsyncSession, test_user):
        """测试正常添加成功"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=100))

        result = await service.add_assets(
            test_user.id,
            equipments=[EquipmentData(equipment_id=f"wpn_{i}") for i in range(5)],
            items=[ItemData(item_id="mat_a")]
        )

        assert result == AddResult.SUCCESS

        # 验证数据已写入
        status = await service.get_status(test_user.id)
        assert status.current == 6  # 5装备 + 1材料

    @pytest.mark.asyncio
    async def test_add_assets_overflow_returns_overflow(self, db_session: AsyncSession, test_user):
        """测试超载时返回OVERFLOW，不写入数据"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=5))

        # 容量只有5，尝试添加10件装备
        result = await service.add_assets(
            test_user.id,
            equipments=[EquipmentData(equipment_id=f"wpn_{i}") for i in range(10)],
            items=[]
        )

        assert result == AddResult.OVERFLOW

        # 验证未写入任何数据
        stmt = select(func.count(UserEquipment.id)).where(UserEquipment.user_id == test_user.id)
        count = (await db_session.execute(stmt)).scalar()
        assert count == 0

    @pytest.mark.asyncio
    async def test_add_assets_items_merge_correctly(self, db_session: AsyncSession, test_user):
        """测试材料添加时正确合并数量"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=100))

        # 第一次添加
        await service.add_assets(
            test_user.id,
            equipments=[],
            items=[ItemData(item_id="mat_a", quantity=10)]
        )

        # 第二次添加相同材料
        await service.add_assets(
            test_user.id,
            equipments=[],
            items=[ItemData(item_id="mat_a", quantity=5)]
        )

        # 验证数量合并为15
        stmt = select(UserItem).where(UserItem.user_id == test_user.id, UserItem.item_id == "mat_a")
        item = (await db_session.execute(stmt)).scalar_one()
        assert item.quantity == 15

        # 仍然是1格占用
        status = await service.get_status(test_user.id)
        assert status.current == 1

    @pytest.mark.asyncio
    async def test_add_assets_partial_overflow_fails_all(self, db_session: AsyncSession, user_with_mixed_assets):
        """测试超载时全部失败，原子性保证"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=10))

        # 用户已有6格占用，剩余4格
        # 尝试添加5件装备 (应该失败)
        result = await service.add_assets(
            user_with_mixed_assets.id,
            equipments=[EquipmentData(equipment_id=f"wpn_{i}") for i in range(5)],
            items=[]
        )

        assert result == AddResult.OVERFLOW

        # 验证没有新增任何装备
        stmt = select(func.count(UserEquipment.id)).where(
            UserEquipment.user_id == user_with_mixed_assets.id,
            UserEquipment.is_equipped == False
        )
        count = (await db_session.execute(stmt)).scalar()
        # 仍然是原来的3件
        assert count == 3


# ============================================================================
# 边界条件测试
# ============================================================================

class TestEdgeCases:
    """测试边界条件"""

    @pytest.mark.asyncio
    async def test_empty_inventory_zero_occupancy(self, db_session: AsyncSession, test_user):
        """测试空背包占用为0"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=100))
        occupancy = await service.get_occupancy(test_user.id)
        assert occupancy == 0

    @pytest.mark.asyncio
    async def test_exactly_full_capacity(self, db_session: AsyncSession, test_user):
        """测试刚好填满容量的情况"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=10))

        # 填满10格
        result = await service.add_assets(
            test_user.id,
            equipments=[EquipmentData(equipment_id=f"wpn_{i}") for i in range(10)],
            items=[]
        )

        assert result == AddResult.SUCCESS

        status = await service.get_status(test_user.id)
        assert status.current == 10
        assert status.available == 0

    @pytest.mark.asyncio
    async def test_negative_required_slots_always_true(self, db_session: AsyncSession, test_user):
        """测试负数或0的required_slots总是返回True"""
        service = InventoryService(db_session, mothership_provider=MockMothershipProvider(capacity=0))

        # 容量为0，但required_slots<=0应该通过
        assert await service.can_add(test_user.id, required_slots=0) is True
        assert await service.can_add(test_user.id, required_slots=-1) is True
        assert await service.can_add(test_user.id, required_slots=-100) is True
