from typing import Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from src.user.inventory import InventoryService
from src.user.schemas import EquipmentData, ItemData
from src.database.models import PveRewardLedger, PveSession, User
from src.pve.models import PveSessionData
from src.pve.enums import ExitMethod
from src.pve.services import MothershipIntegrationService
from src.pve.progress_service import PveProgressService
from src.models import MothershipConfig

class RewardController:
    """PVE 收益控制器。

    负责管理会话期间产生的临时战利品，并在结算时根据退出方式决定最终的收益折算并入库。
    """
    
    @staticmethod
    def add_pending_loot(session_data: PveSessionData, loot: List[Dict[str, Any]]):
        """将战斗产生的掉落物存入临时奖励池。

        战利品在玩家成功执行撤离 (Extract) 操作前不属于玩家资产，仅暂存在会话对象中。

        Args:
            session_data (PveSessionData): 目标 PVE 会话实体。
            loot (List[Dict[str, Any]]): 掉落物品列表，每个元素应包含 type, id 等信息。
        """
        for item in loot:
            if item.get("type") == "equipment":
                session_data.pending_rewards.equipments.append(item)
            else:
                session_data.pending_rewards.items.append(item)
                
    @classmethod
    async def finalize(
        cls, 
        db: AsyncSession, 
        session_data: PveSessionData, 
        exit_method: ExitMethod,
        inventory_service: "InventoryService",
        mothership_config: "MothershipConfig",
        loader: Any
    ) -> Dict[str, Any]:
        """执行会话结算并将战利品正式入库。

        该流程包含幂等校验、战利品折损计算、以及与库存系统的交互。

        Args:
            db (AsyncSession): 数据库异步会话。
            session_data (PveSessionData): 要结算的会话数据。
            exit_method (ExitMethod): 玩家退出的方式。
            inventory_service (InventoryService): 库存系统服务，用于资产入库。
            mothership_config (Any): 用于计算紧急撤离税率的母舰配置。

        Returns:
            Dict[str, Any]: 结算概要信息，包含原始数量与实际入库数量。

        Raises:
            ValueError: 如果会话已结算过（防刷/重复领取）。
        """
        user_id = session_data.user_id
        session_id = session_data.session_id
        
        # 1. 软校验：查询记录是否已存在
        stmt = select(PveRewardLedger).where(PveRewardLedger.session_id == session_id)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise ValueError(f"Session {session_id} rewards already claimed.")
            
        # 2. 计算税率和实际所得
        if exit_method == ExitMethod.DEFEATED:
            # 战败：全部丢失
            final_equipments = []
            final_items = []
        elif exit_method == ExitMethod.EMERGENCY_EXIT:
            # 紧急撤离：应用母舰税率丢弃
            tax_rate = MothershipIntegrationService.calculate_discard_ratio(mothership_config)
            # 简化实现：根据税率按概率/比例丢弃。此处演示暴力切分
            equip_len = len(session_data.pending_rewards.equipments)
            item_len = len(session_data.pending_rewards.items)
            keep_equip_idx = int(equip_len * (1.0 - tax_rate))
            keep_item_idx = int(item_len * (1.0 - tax_rate))
            
            final_equipments = session_data.pending_rewards.equipments[:keep_equip_idx]
            final_items = session_data.pending_rewards.items[:keep_item_idx]
        else:
            # Boss Clear 或 Voluntary Exit: 全量获得
            final_equipments = session_data.pending_rewards.equipments
            final_items = session_data.pending_rewards.items
            
        from sqlalchemy.exc import IntegrityError
        
        # 3. 记录流水并触发硬核幂等校验 (DB 唯一索引强制拦截)
        summary = {
            "exit_method": exit_method.value,
            "original_equips": len(session_data.pending_rewards.equipments),
            "final_equips": len(final_equipments),
            "original_items": len(session_data.pending_rewards.items),
            "final_items": len(final_items)
        }
        ledger = PveRewardLedger(
            session_id=session_id,
            user_id=user_id,
            rewards_summary=summary
        )
        db.add(ledger)
        
        try:
            # 预提交以触发唯一键冲突检查
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise ValueError(f"Session {session_id} rewards are being processed or already claimed (Integrity Check).")
            
        # 4. 入库 (Inventory Service)
        # 将 Dict 转换为 DTO
        equip_dtos = [
            EquipmentData(
                equipment_id=eq["equipment_id"], 
                enhancement_level=eq.get("enhancement_level", 0),
                random_stats=eq.get("random_stats", {})
            ) for eq in final_equipments
        ]
        item_dtos = [
            ItemData(
                item_id=it["item_id"],
                item_type=it.get("item_type", "material"),
                quantity=it.get("quantity", 1)
            ) for it in final_items
        ]
        
        if equip_dtos or item_dtos:
            add_result = await inventory_service.add_assets(user_id, equip_dtos, item_dtos)
            summary["add_result"] = add_result.value
            
        # 注意: 信用点是即时入账的，不放在这里结。
            
        # 5. 删除由于断线保护持有的 PveSession 表记 (如果不是纯内存测试阶段)
        stmt_del = delete(PveSession).where(PveSession.id == session_id)
        await db.execute(stmt_del)

        # 6. 如果是通关退出，标记进度
        if exit_method == ExitMethod.BOSS_CLEAR:
            new_zones = await PveProgressService.mark_zone_cleared(
                db=db,
                user_id=user_id,
                region_id=session_data.region_id,
                zone_id=session_data.zone_id,
                loader=loader
            )
            summary["new_unlocked_zones"] = new_zones
        
        # 不要主动 commit，将事务提交权交给上层 API 的 Session 依赖注入
        
        return summary
