"""装备系统服务层 (Equipment Service)

管理装备的挂载 (equip) 与卸除 (unequip)，实现文档 4 和 7 的以下约束：
1. 槽位合法性验证（EXCLUSIVE / WEAPON / EQUIP）
2. 互斥与顶替流转（Swap-out）
3. 安全生命周期保护（显式卸载并校验背包容量）
4. 不依赖 CASCADE SET NULL
"""

import asyncio
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.database.models import UserEquipment, UserMecha
from src.user.inventory import InventoryService
from src.loader import DataLoader
from src.factory import MechaFactory


class EquipmentServiceError(Exception):
    """业务逻辑异常"""
    pass


class EquipmentService:
    """处理玩家装备拆装等业务"""

    def __init__(
        self,
        session: AsyncSession,
        inventory_service: InventoryService,
        loader: DataLoader
    ):
        self.session = session
        self.inventory_service = inventory_service
        self.loader = loader

    async def unequip(self, user_id: int, user_equipment_id: int) -> UserEquipment:
        """卸载装备
        
        执行显式卸载流：检查资产是否属于玩家 -> 检查是否正在装备 -> 检查背包容量 -> 解除关系。
        """
        # 1. 查找装备
        stmt = select(UserEquipment).where(
            and_(UserEquipment.id == user_equipment_id, UserEquipment.user_id == user_id)
        )
        equip: Optional[UserEquipment] = (await self.session.execute(stmt)).scalar_one_or_none()
        if not equip:
            raise EquipmentServiceError("装备不存在或无权限")
        if not equip.is_equipped:
            raise EquipmentServiceError("该装备目前未处于已装备状态")

        # 2. 容量检查 (Doc 4要求退载时如果触发容量超限拦截)
        # 注意: 虽然退载只释放1件装备到背包，理论上占1格，
        if not await self.inventory_service.can_add(user_id, 1):
            raise EquipmentServiceError("卸载失败，背包剩余容量不足")

        # 3. 执行显式卸载
        equip.equipped_mecha_id = None
        equip.equipped_slot_idx = None
        equip.is_equipped = False

        await self.session.flush()
        return equip

    async def equip(
        self, user_id: int, user_equipment_id: int, user_mecha_id: int, slot_idx: int
    ) -> UserEquipment:
        """挂载/替换装备
        
        校验槽位合法性，如果目标槽位已有装备，则触发替换逻辑。
        """
        # 1. 获取装备和机体
        equip_stmt = select(UserEquipment).where(
            and_(UserEquipment.id == user_equipment_id, UserEquipment.user_id == user_id)
        )
        equip: Optional[UserEquipment] = (await self.session.execute(equip_stmt)).scalar_one_or_none()
        
        if not equip:
            raise EquipmentServiceError("查无此装备")
        if equip.is_locked:
            pass # 锁定状态不影响装备，只影响分解/售卖
            
        mecha_stmt = select(UserMecha).where(
            and_(UserMecha.id == user_mecha_id, UserMecha.user_id == user_id)
        )
        mecha: Optional[UserMecha] = (await self.session.execute(mecha_stmt)).scalar_one_or_none()
        if not mecha:
            raise EquipmentServiceError("查无此机体")

        # 2. 从 Loader 中获取静态配置并验证槽位
        mecha_conf = self.loader.get_mecha_config(mecha.mech_id)
        equip_conf = self.loader.get_equipment_config(equip.equipment_id)
        
        if slot_idx < 0 or slot_idx >= len(mecha_conf.slots):
            raise EquipmentServiceError(f"非法的槽位索引。该机体仅有 {len(mecha_conf.slots)} 个可选槽位。")
        
        slot_type = mecha_conf.slots[slot_idx]
        
        # 3. 槽位合法性验证 (复用 MechaFactory)
        if not MechaFactory._validate_equipment_slot(equip_conf, slot_type, mecha_conf.series):
            raise EquipmentServiceError(
                f"合法性拦截: 该装备 {equip_conf.id} 类型 ({equip_conf.type}) 无法安装至槽位 {slot_type}"
            )

        # 4. 判断目标槽位是否已有旧装备 (Swap-out)
        existing_stmt = select(UserEquipment).where(
            and_(
                UserEquipment.user_id == user_id,
                UserEquipment.equipped_mecha_id == user_mecha_id,
                UserEquipment.equipped_slot_idx == slot_idx
            )
        )
        existing_equip: Optional[UserEquipment] = (await self.session.execute(existing_stmt)).scalar_one_or_none()

        if existing_equip and existing_equip.id == equip.id:
            return equip  # 装备在同一位置不需要做任何变动

        # 校验容量：如果当前装备已经在使用中（占0格），并且我们要将此槽位原有装备退回背包（占1格），那么净变动为+1，需要检查。
        if existing_equip and equip.is_equipped:
            if not await self.inventory_service.can_add(user_id, 1):
                raise EquipmentServiceError("替换失败：被替换的装备卸载后将导致背包超载")

        # 卸载槽位上原有的旧装备
        if existing_equip:
            existing_equip.equipped_mecha_id = None
            existing_equip.equipped_slot_idx = None
            existing_equip.is_equipped = False

        # 5. 执行挂载
        equip.equipped_mecha_id = mecha.id
        equip.equipped_slot_idx = slot_idx
        equip.is_equipped = True

        await self.session.flush()
        return equip

    async def delete_mecha_safe(self, user_id: int, user_mecha_id: int) -> None:
        """安全销毁机体
        
        执行显式卸载：在机体销毁业务中，必须先计算退回背包的装备是否会触发容量超限。
        如果在安全范围内，显式将 equipped_mecha_id 置空且 is_equipped=False。
        (参照 Doc 4: 安全生命周期保护)
        """
        # 1. 查找挂载在该机体上的所有装备
        stmt = select(UserEquipment).where(
            and_(UserEquipment.user_id == user_id, UserEquipment.equipped_mecha_id == user_mecha_id)
        )
        equips: List[UserEquipment] = list((await self.session.execute(stmt)).scalars().all())

        if not equips:
            # 没有挂载装备，直接允许底层删除（此模块不执行机体表的 DELETE，只处理装备卸载责任）
            return
            
        # 2. 检查背包容量
        # 卸下所有这些装备所需的新增容量 === 装备数量
        required_slots = len(equips)
        if not await self.inventory_service.can_add(user_id, required_slots):
            raise EquipmentServiceError(
                f"机体解雇失败：卸载的装备 ({required_slots}件) 将导致背包超载，请先清理背包。"
            )

        # 3. 显式卸载
        for eq in equips:
            eq.equipped_mecha_id = None
            eq.equipped_slot_idx = None
            eq.is_equipped = False
            
        await self.session.flush()
        # 调用方（例如 MechaService）在无报错返回后，再执行 session.delete(mecha)
