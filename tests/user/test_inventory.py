import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.user.inventory import InventoryService, MockMothershipProvider
from src.user.schemas import EquipmentData, ItemData, AddResult
from src.database.models import UserEquipment, UserItem

@pytest.fixture
async def test_user(db_session: AsyncSession):
    from src.database.models import User
    from src.user.security import hash_password
    user = User(
        username="inventory_tester",
        password_hash=hash_password("password123")
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_inventory_capacity(db_session: AsyncSession, test_user):
    service = InventoryService(db_session)
    status = await service.get_status(test_user.id)
    assert status.capacity == 100
    assert status.current == 0
    assert status.available == 100

@pytest.mark.asyncio
async def test_add_equipments(db_session: AsyncSession, test_user):
    service = InventoryService(db_session)
    
    equipments = [
        EquipmentData(equipment_id="wpn_beam_rifle_01"),
        EquipmentData(equipment_id="wpn_vulcan_01")
    ]
    
    result = await service.add_assets(test_user.id, equipments=equipments, items=[])
    assert result == AddResult.SUCCESS
    
    status = await service.get_status(test_user.id)
    assert status.current == 2

@pytest.mark.asyncio
async def test_add_items_stacking(db_session: AsyncSession, test_user):
    service = InventoryService(db_session)
    
    items = [
        ItemData(item_id="mat_alloy_01", quantity=10),
        ItemData(item_id="mat_alloy_01", quantity=5),
        ItemData(item_id="mat_shard_01", quantity=1)
    ]
    
    result = await service.add_assets(test_user.id, equipments=[], items=items)
    assert result == AddResult.SUCCESS
    
    # 2 types of items -> 2 slots occupied
    status = await service.get_status(test_user.id)
    assert status.current == 2
    
    # Check quantities
    from sqlalchemy import select
    res = await db_session.execute(select(UserItem).where(UserItem.user_id == test_user.id))
    db_items = res.scalars().all()
    assert len(db_items) == 2
    for db_item in db_items:
        if db_item.item_id == "mat_alloy_01":
            assert db_item.quantity == 15
        elif db_item.item_id == "mat_shard_01":
            assert db_item.quantity == 1

@pytest.mark.asyncio
async def test_inventory_overflow(db_session: AsyncSession, test_user):
    class SmallMothershipProvider(MockMothershipProvider):
        async def get_max_capacity(self, user_id: int) -> int:
            return 2
            
    service = InventoryService(db_session, mothership_provider=SmallMothershipProvider())
    
    # Add 2 items (takes 2 slots)
    result = await service.add_assets(test_user.id, equipments=[], items=[
        ItemData(item_id="mat_1"),
        ItemData(item_id="mat_2")
    ])
    assert result == AddResult.SUCCESS
    
    # Try adding 1 more equipment (takes 1 slot, 2 + 1 > 2)
    result2 = await service.add_assets(test_user.id, equipments=[EquipmentData(equipment_id="wpn_1")], items=[])
    assert result2 == AddResult.OVERFLOW

@pytest.mark.asyncio
async def test_equipped_items_not_counted(db_session: AsyncSession, test_user):
    service = InventoryService(db_session)
    
    # Create 1 unequipped
    db_session.add(UserEquipment(user_id=test_user.id, equipment_id="wpn_1", is_equipped=False))
    # Create 1 equipped
    db_session.add(UserEquipment(user_id=test_user.id, equipment_id="wpn_2", is_equipped=True))
    await db_session.flush()
    
    status = await service.get_status(test_user.id)
    # Only 1 slot should be occupied by the unequipped equipment
    assert status.current == 1
