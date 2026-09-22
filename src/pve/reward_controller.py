from typing import Dict, Any, List, TYPE_CHECKING
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from src.user.item_system import ItemSystem, TicketStatus, make_receipt_id
from src.user.schemas import EquipmentData, ItemData
from src.database.models import ItemTicket, PveSession
from src.pve.models import PveSessionData
from src.pve.enums import ExitMethod
from src.pve.services import MothershipIntegrationService
from src.pve.progress_service import PveProgressService
from src.models import MothershipConfig

if TYPE_CHECKING:
    from src.loader import DataLoader


class RewardController:
    """PVE 收益控制器。

    负责管理会话期间产生的临时战利品，并在结算时根据退出方式折算收益，
    凭回执编号向物品系统递发放单建票据（Doc 17 场景 4.12）——结算自己
    不入库、不碰玩家存档，防重复由 item_tickets.receipt_id 唯一兜底。
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
        item_system: ItemSystem,
        mothership_config: MothershipConfig,
        loader: "DataLoader"
    ) -> Dict[str, Any]:
        """执行会话结算，将折算后的战利品凭票据递给物品系统（场景 4.12）。

        流程：幂等前置（同回执已有非 rejected 票据直接重建 summary 返回，
        "这批发过了"；rejected 留档不占幂等位，继续走折算+递单重校验）
        → 折算 → 非空则 submit_grant 建 pending 票据 → 删 PVE 会话 → 通关
        标记进度。折算后全空（如战败）不建票据，只走完收尾。

        Args:
            db (AsyncSession): 数据库异步会话。
            session_data (PveSessionData): 要结算的会话数据。
            exit_method (ExitMethod): 玩家退出的方式。
            item_system (ItemSystem): 物品系统门面，发放唯一通道。
            mothership_config (MothershipConfig): 用于计算紧急撤离税率的母舰配置。
            loader (DataLoader): 静态资源加载器，进度标记与清单校验用。

        Returns:
            Dict[str, Any]: 结算概要，含票据 id/状态与本批信用点；全空批次
            ticket_id=None。

        Raises:
            GrantManifestMismatchError: 清单不符（模板不存在/数量非法）。
                不捕获——submit_grant 门内已建 rejected 留档票据并记日志，
                finalize 在此中止：删会话/进度标记不执行，会话保留兜底
                "没入包的东西不会凭空消失"（场景 4.10）；API 层负责先提交
                留档再翻译 400。
        """
        session_id = session_data.session_id
        receipt_id = make_receipt_id("pve", str(session_id))

        # 1. 幂等前置：同回执已有非 rejected 票据 → "这批发过了"（场景
        #    4.4/4.12），用票据重建 summary 返回，跳过折算/进度标记/删会话。
        #    rejected 留档不占幂等位（场景 4.10）——mismatch 后数据修复的
        #    重结算必须能走到 submit_grant 复检，不能被留档票据短路
        existing = (await db.execute(
            select(ItemTicket).where(ItemTicket.receipt_id == receipt_id)
        )).scalar_one_or_none()
        if existing is not None and existing.status != TicketStatus.REJECTED:
            return cls._summary_from_ticket(existing, exit_method)

        # 2. 折算（DEFEATED 全失 / EMERGENCY_EXIT 税率切分 / 其余全量）
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

        summary = {
            "exit_method": exit_method.value,
            "original_equips": len(session_data.pending_rewards.equipments),
            "final_equips": len(final_equipments),
            "original_items": len(session_data.pending_rewards.items),
            "final_items": len(final_items),
            "ticket_id": None,
            "ticket_status": None,
            "credits": 0,
        }

        # 3. 非空批次 → 递发放单建票据；原批原始件数进 source_detail 供
        #    幂等重放时重建 summary
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
        credits = session_data.credits_earned

        if equip_dtos or item_dtos or credits:
            ticket = await item_system.submit_grant(
                session_data.user_id,
                receipt_id,
                "pve",
                equipments=equip_dtos,
                items=item_dtos,
                credits=credits,
                source_detail={
                    "session_id": session_id,
                    "original_equips": summary["original_equips"],
                    "original_items": summary["original_items"],
                },
            )
            summary["ticket_id"] = ticket.id
            summary["ticket_status"] = ticket.status
            summary["credits"] = credits

        # 4. 删除由于断线保护持有的 PveSession 表记 (如果不是纯内存测试阶段)
        stmt_del = delete(PveSession).where(PveSession.id == session_id)
        await db.execute(stmt_del)

        # 5. 如果是通关退出，标记进度
        if exit_method == ExitMethod.BOSS_CLEAR:
            new_zones = await PveProgressService.mark_zone_cleared(
                db=db,
                user_id=session_data.user_id,
                region_id=session_data.region_id,
                zone_id=session_data.zone_id,
                loader=loader
            )
            summary["new_unlocked_zones"] = new_zones

        # 不要主动 commit，将事务提交权交给上层 API 的 Session 依赖注入
        return summary

    @staticmethod
    def _summary_from_ticket(ticket: ItemTicket, exit_method: ExitMethod) -> Dict[str, Any]:
        """用已存在的票据重建结算概要（幂等重放路径，"这批发过了"）。

        final 件数与信用点取自票据 manifest；original 件数取自首次结算存
        的 source_detail（缺省时以 final 件数兜底——旧票据无溯源字段）。
        """
        manifest = ticket.manifest or {}
        detail = ticket.source_detail or {}
        equip_count = len(manifest.get("equipments", []))
        item_count = len(manifest.get("items", []))
        return {
            "exit_method": exit_method.value,
            "original_equips": int(detail.get("original_equips", equip_count)),
            "final_equips": equip_count,
            "original_items": int(detail.get("original_items", item_count)),
            "final_items": item_count,
            "ticket_id": ticket.id,
            "ticket_status": ticket.status,
            "credits": int(manifest.get("credits", 0)),
        }
