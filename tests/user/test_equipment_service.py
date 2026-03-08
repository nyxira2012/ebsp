"""EquipmentService 测试

测试装备系统的核心功能：
1. unequip() - 卸载装备
2. equip() - 挂载/替换装备
3. delete_mecha_safe() - 安全销毁机体前的装备卸载
"""

import pytest
from unittest.mock import AsyncMock, Mock
from sqlalchemy.ext.asyncio import AsyncSession

from src.user.equipment_service import EquipmentService, EquipmentServiceError
from src.user.inventory import InventoryService
from src.database.models import UserEquipment, UserMecha
from src.models import MechaConfig, EquipmentConfig
from src.loader import DataLoader


@pytest.fixture
async def test_user_with_equip(db_session: AsyncSession):
    """创建测试用户和装备数据"""
    from src.database.models import User
    from src.user.security import hash_password

    # 创建测试用户
    user = User(
        username="equip_tester",
        password_hash=hash_password("password123")
    )
    db_session.add(user)
    await db_session.flush()

    # 创建测试机体
    mecha = UserMecha(
        user_id=user.id,
        mech_id="mech_rx78",
        nickname="RX-78",
        upgrades={}
    )
    db_session.add(mecha)
    await db_session.flush()

    # 创建测试装备（已装备状态）
    equipped = UserEquipment(
        user_id=user.id,
        equipment_id="wpn_beam_rifle",
        is_equipped=True,
        equipped_mecha_id=mecha.id,
        equipped_slot_idx=0
    )
    db_session.add(equipped)

    # 创建测试装备（未装备状态）
    unequipped = UserEquipment(
        user_id=user.id,
        equipment_id="wpn_vulcan",
        is_equipped=False
    )
    db_session.add(unequipped)
    await db_session.flush()

    return {"user": user, "mecha": mecha, "equipped": equipped, "unequipped": unequipped}


@pytest.fixture
def mock_loader():
    """模拟 DataLoader"""
    loader = Mock(spec=DataLoader)

    # Mock MechaConfig
    mecha_config = MechaConfig(
        id="mech_rx78",
        name="RX-78",
        portrait_id="m_rx78",
        series="RX",
        slots=["WEAPON", "WEAPON", "SPECIAL"],
        init_hp=5000,
        init_en=100,
        init_armor=1000,
        init_mobility=100,
        init_hit=10.0,
        init_precision=10.0,
        init_crit=5.0,
        init_dodge=10.0,
        init_parry=10.0,
        init_block=10.0,
        init_block_red=500
    )
    loader.get_mecha_config.return_value = mecha_config

    # Mock EquipmentConfig
    weapon_config = EquipmentConfig(
        id="wpn_beam_rifle",
        name="Beam Rifle",
        type="WEAPON",
        series=[],
        modifiers={}
    )
    loader.get_equipment_config.return_value = weapon_config

    return loader


@pytest.fixture
def mock_inventory_service():
    """模拟 InventoryService"""
    service = Mock(spec=InventoryService)
    service.can_add = AsyncMock(return_value=True)
    return service


# ============================================================================
# unequip() 测试
# ============================================================================

@pytest.mark.asyncio
async def test_unequip_success(db_session: AsyncSession, test_user_with_equip):
    """测试成功卸载装备"""
    data = test_user_with_equip
    inv_service = Mock(spec=InventoryService)
    inv_service.can_add = AsyncMock(return_value=True)
    loader = Mock()

    service = EquipmentService(db_session, inv_service, loader)

    result = await service.unequip(data["user"].id, data["equipped"].id)

    assert result.is_equipped is False
    assert result.equipped_mecha_id is None
    assert result.equipped_slot_idx is None
    assert inv_service.can_add.called


@pytest.mark.asyncio
async def test_unequip_equipment_not_found(db_session: AsyncSession, test_user_with_equip):
    """测试卸载不存在的装备"""
    data = test_user_with_equip
    service = EquipmentService(db_session, Mock(), Mock())

    with pytest.raises(EquipmentServiceError, match="装备不存在或无权限"):
        await service.unequip(data["user"].id, 99999)


@pytest.mark.asyncio
async def test_unequip_not_equipped(db_session: AsyncSession, test_user_with_equip):
    """测试卸载未装备的装备"""
    data = test_user_with_equip
    service = EquipmentService(db_session, Mock(), Mock())

    with pytest.raises(EquipmentServiceError, match="该装备目前未处于已装备状态"):
        await service.unequip(data["user"].id, data["unequipped"].id)


@pytest.mark.asyncio
async def test_unequip_insufficient_capacity(db_session: AsyncSession, test_user_with_equip):
    """测试背包容量不足时卸载失败"""
    data = test_user_with_equip
    inv_service = Mock(spec=InventoryService)
    inv_service.can_add = AsyncMock(return_value=False)

    service = EquipmentService(db_session, inv_service, Mock())

    with pytest.raises(EquipmentServiceError, match="背包剩余容量不足"):
        await service.unequip(data["user"].id, data["equipped"].id)


# ============================================================================
# equip() 测试
# ============================================================================

@pytest.mark.asyncio
async def test_equip_to_empty_slot(db_session: AsyncSession, test_user_with_equip, mock_loader, mock_inventory_service):
    """测试装备到空槽位"""
    data = test_user_with_equip
    service = EquipmentService(db_session, mock_inventory_service, mock_loader)

    result = await service.equip(
        data["user"].id,
        data["unequipped"].id,
        data["mecha"].id,
        1  # 第二个槽位
    )

    assert result.is_equipped is True
    assert result.equipped_mecha_id == data["mecha"].id
    assert result.equipped_slot_idx == 1


@pytest.mark.asyncio
async def test_equip_same_slot_noop(db_session: AsyncSession, test_user_with_equip, mock_loader, mock_inventory_service):
    """测试装备到已装备的同一位置（无操作）"""
    data = test_user_with_equip
    service = EquipmentService(db_session, mock_inventory_service, mock_loader)

    result = await service.equip(
        data["user"].id,
        data["equipped"].id,
        data["mecha"].id,
        0  # 已经装备在这里
    )

    assert result.id == data["equipped"].id


@pytest.mark.asyncio
async def test_equip_replace_existing(db_session: AsyncSession, test_user_with_equip, mock_loader, mock_inventory_service):
    """测试替换已有装备"""
    data = test_user_with_equip
    service = EquipmentService(db_session, mock_inventory_service, mock_loader)

    # 旧装备应该被卸载
    await service.equip(
        data["user"].id,
        data["unequipped"].id,
        data["mecha"].id,
        0  # 替换槽位 0 的装备
    )

    # 使用 select 验证旧装备已卸载
    from sqlalchemy import select
    old_stmt = select(UserEquipment).where(UserEquipment.id == data["equipped"].id)
    old_result = await db_session.execute(old_stmt)
    old_equip = old_result.scalar_one()
    assert old_equip.is_equipped is False

    # 验证新装备已装备
    new_stmt = select(UserEquipment).where(UserEquipment.id == data["unequipped"].id)
    new_result = await db_session.execute(new_stmt)
    new_equip = new_result.scalar_one()
    assert new_equip.is_equipped is True
    assert new_equip.equipped_mecha_id == data["mecha"].id


@pytest.mark.asyncio
async def test_equip_equipment_not_found(db_session: AsyncSession, test_user_with_equip, mock_loader, mock_inventory_service):
    """测试装备不存在的装备"""
    data = test_user_with_equip
    service = EquipmentService(db_session, mock_inventory_service, mock_loader)

    with pytest.raises(EquipmentServiceError, match="查无此装备"):
        await service.equip(data["user"].id, 99999, data["mecha"].id, 0)


@pytest.mark.asyncio
async def test_equip_mecha_not_found(db_session: AsyncSession, test_user_with_equip, mock_loader, mock_inventory_service):
    """测试装备到不存在的机体"""
    data = test_user_with_equip
    service = EquipmentService(db_session, mock_inventory_service, mock_loader)

    with pytest.raises(EquipmentServiceError, match="查无此机体"):
        await service.equip(data["user"].id, data["unequipped"].id, 99999, 0)


@pytest.mark.asyncio
async def test_equip_invalid_slot(db_session: AsyncSession, test_user_with_equip, mock_loader, mock_inventory_service):
    """测试非法槽位索引"""
    data = test_user_with_equip
    service = EquipmentService(db_session, mock_inventory_service, mock_loader)

    with pytest.raises(EquipmentServiceError, match="非法的槽位索引"):
        await service.equip(data["user"].id, data["unequipped"].id, data["mecha"].id, 999)


@pytest.mark.asyncio
async def test_equip_incompatible_slot_type(db_session: AsyncSession, test_user_with_equip, mock_loader, mock_inventory_service):
    """测试装备类型不兼容"""
    data = test_user_with_equip

    # 修改槽位配置为 SPECIAL
    mecha_config = MechaConfig(
        id="mech_rx78",
        name="RX-78",
        portrait_id="m_rx78",
        series="RX",
        slots=["SPECIAL"],  # 只有 SPECIAL 槽位
        init_hp=5000,
        init_en=100,
        init_armor=1000,
        init_mobility=100,
        init_hit=10.0,
        init_precision=10.0,
        init_crit=5.0,
        init_dodge=10.0,
        init_parry=10.0,
        init_block=10.0,
        init_block_red=500
    )
    mock_loader.get_mecha_config.return_value = mecha_config

    service = EquipmentService(db_session, mock_inventory_service, mock_loader)

    with pytest.raises(EquipmentServiceError, match="合法性拦截"):
        await service.equip(data["user"].id, data["unequipped"].id, data["mecha"].id, 0)


@pytest.mark.asyncio
async def test_equip_replace_insufficient_capacity(db_session: AsyncSession, test_user_with_equip, mock_loader):
    """测试替换时背包容量不足"""
    data = test_user_with_equip

    # 创建一个已装备的装备（作为被替换的装备）
    another_equipped = UserEquipment(
        user_id=data["user"].id,
        equipment_id="wpn_saber",
        is_equipped=True,
        equipped_mecha_id=data["mecha"].id,
        equipped_slot_idx=1
    )
    db_session.add(another_equipped)

    # 将 data["unequipped"] 设置为已装备状态（模拟替换两个已装备的装备）
    data["unequipped"].is_equipped = True
    data["unequipped"].equipped_mecha_id = data["mecha"].id
    data["unequipped"].equipped_slot_idx = 2

    await db_session.flush()

    inv_service = Mock(spec=InventoryService)
    inv_service.can_add = AsyncMock(return_value=False)  # 容量不足

    service = EquipmentService(db_session, inv_service, mock_loader)

    with pytest.raises(EquipmentServiceError, match="替换失败"):
        await service.equip(
            data["user"].id,
            data["unequipped"].id,
            data["mecha"].id,
            1  # 替换另一个已装备的装备
        )


# ============================================================================
# delete_mecha_safe() 测试
# ============================================================================

@pytest.mark.asyncio
async def test_delete_mecha_safe_no_equipment(db_session: AsyncSession, test_user_with_equip):
    """测试无装备时直接通过"""
    data = test_user_with_equip
    service = EquipmentService(db_session, Mock(), Mock())

    # 创建一个没有装备的机体
    empty_mecha = UserMecha(
        user_id=data["user"].id,
        mech_id="mech_zaku",
        nickname="Zaku",
        upgrades={}
    )
    db_session.add(empty_mecha)
    await db_session.flush()

    # 不应抛出异常
    await service.delete_mecha_safe(data["user"].id, empty_mecha.id)


@pytest.mark.asyncio
async def test_delete_mecha_safe_success(db_session: AsyncSession, test_user_with_equip):
    """测试成功卸载所有装备"""
    data = test_user_with_equip
    inv_service = Mock(spec=InventoryService)
    inv_service.can_add = AsyncMock(return_value=True)
    service = EquipmentService(db_session, inv_service, Mock())

    await service.delete_mecha_safe(data["user"].id, data["mecha"].id)

    # 使用 select 验证装备已卸载
    from sqlalchemy import select
    stmt = select(UserEquipment).where(UserEquipment.id == data["equipped"].id)
    result = await db_session.execute(stmt)
    equip = result.scalar_one()
    assert equip.is_equipped is False
    assert equip.equipped_mecha_id is None


@pytest.mark.asyncio
async def test_delete_mecha_safe_insufficient_capacity(db_session: AsyncSession, test_user_with_equip):
    """测试容量不足时阻止删除"""
    data = test_user_with_equip
    inv_service = Mock(spec=InventoryService)
    inv_service.can_add = AsyncMock(return_value=False)
    service = EquipmentService(db_session, inv_service, Mock())

    with pytest.raises(EquipmentServiceError, match="机体解雇失败.*背包超载"):
        await service.delete_mecha_safe(data["user"].id, data["mecha"].id)


@pytest.mark.asyncio
async def test_delete_mecha_safe_multiple_equipment(db_session: AsyncSession, test_user_with_equip):
    """测试卸载多件装备"""
    data = test_user_with_equip

    # 添加更多装备到同一机体
    for i in range(3):
        equip = UserEquipment(
            user_id=data["user"].id,
            equipment_id=f"wpn_{i}",
            is_equipped=True,
            equipped_mecha_id=data["mecha"].id,
            equipped_slot_idx=i
        )
        db_session.add(equip)
    await db_session.flush()

    inv_service = Mock(spec=InventoryService)
    inv_service.can_add = AsyncMock(return_value=True)
    service = EquipmentService(db_session, inv_service, Mock())

    await service.delete_mecha_safe(data["user"].id, data["mecha"].id)

    # 验证容量检查是正确的装备数量
    inv_service.can_add.assert_called_once_with(data["user"].id, 4)  # 1 原有 + 3 新增
