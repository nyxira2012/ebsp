"""
用户业务逻辑层 (Service Layer)

负责协调 Repository 进行复杂的跨表业务操作，并处理核心业务规则。
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Tuple, TYPE_CHECKING

from src.user.repository import MothershipRepository, UserAssetRepository, UserRepository
from src.user.item_system import ItemSystem, make_receipt_id
from src.user.schemas import ItemData
from src.pve.services import MothershipIntegrationService
from src.database.models import User, UserSquad

if TYPE_CHECKING:
    from src.loader import DataLoader

class MothershipService:
    """母舰相关业务逻辑"""

    @staticmethod
    async def purchase_mothership(
        session: AsyncSession,
        user: User,
        mothership_id: str,
        loader: "DataLoader"  # 静态数据加载器
    ):
        """购买母舰的完整业务流（Doc 17 场景 4.5/4.6：钱货一笔，同事务完成）"""

        # 1. PVE 锁定检查 (P0)
        if await MothershipIntegrationService.is_pve_session_active(session, user.id):
            raise ValueError("PVE 出征期间全盘系统锁定，无法购买母舰")

        # 2. 静态配置检查
        if mothership_id not in loader.motherships:
            raise ValueError("无效的母舰型号")

        m_config = loader.motherships[mothership_id]

        # 3. 拥有状态快查（快速失败；正确性由步骤 6 锁后复查兜底）
        db_mothership = await MothershipRepository.get_by_user_id(session, user.id)
        if db_mothership and mothership_id in db_mothership.data.get("owned_ids", []):
             raise ValueError("玩家已拥有该母舰")

        # 4. 前置条件检查 (P0)
        # TODO: 待成就系统/关卡进度系统对接
        if m_config.required_chapter:
            # current_chapter = user.progression.get("max_chapter", 0)
            current_chapter = 0 # 硬编码：新用户默认为 0
            if current_chapter < m_config.required_chapter:
                raise ValueError(f"购买失败。需通关第 {m_config.required_chapter} 章节")

        if m_config.required_achievement:
            # owned_achievements = user.progression.get("achievements", [])
            owned_achievements = [] # 硬编码
            if m_config.required_achievement not in owned_achievements:
                raise ValueError(f"购买失败。需达成成就: {m_config.required_achievement}")

        # 5. 真扣款（场景 4.6）：行锁 users 行核对扣减，不够→InsufficientCreditsError
        #    分文不动；行锁同时串行化同用户并发购买——T2 在 T1 提交后才能扣款
        item_system = ItemSystem(session, loader=loader)
        await item_system.charge_credits(user.id, m_config.price)

        # 6. 锁后复查拥有状态（场景 4.5 防双扣）：并发同款购买在扣款处排队，
        #    T1 提交后 T2 才走到这里——复查发现已拥有 → 抛错整笔回滚，已扣款
        #    随事务回滚，余额不动（行锁读的新鲜度由 repository 的
        #    populate_existing 单点保证）
        db_mothership = await MothershipRepository.get_by_user_id(session, user.id, for_update=True)
        if db_mothership and mothership_id in db_mothership.data.get("owned_ids", []):
            raise ValueError("玩家已拥有该母舰")

        # 7. 执行购买
        updated = await MothershipRepository.purchase_mothership(
            session, user.id, mothership_id, cost=m_config.price
        )
        if not updated:
            raise ValueError("修改用户母舰记录失败")

        return updated

    @staticmethod
    async def switch_mothership(
        session: AsyncSession, 
        user_id: int, 
        mothership_id: str
    ):
        """切换母舰"""
        
        # 1. PVE 锁定检查
        if await MothershipIntegrationService.is_pve_session_active(session, user_id):
            raise ValueError("PVE 出征期间全盘系统锁定，无法切换母舰")
            
        return await MothershipRepository.switch_mothership(session, user_id, mothership_id)

class SquadNotReadyError(ValueError):
    """出战编队未就绪（Doc 7 v2.2 §11.2 的 400 分流载体）。

    Attributes:
        code: 机器可读错误码（STARTER_NOT_CLAIMED / NO_ACTIVE_SQUAD）。
        message: 人读指引文案。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class MechasNotOwnedError(ValueError):
    """引用了不属于该用户的机体（Doc 7 v2.2 §11.5 的 400 分流载体）。

    Attributes:
        mecha_ids: 不在用户名下的机体 ID 列表。
    """

    code = "MECHA_NOT_OWNED"

    def __init__(self, mecha_ids: List[int]) -> None:
        super().__init__(f"机体不属于该用户: {mecha_ids}")
        self.mecha_ids = mecha_ids


class OnboardingService:
    """新号引导业务：初始机体领取与出战编队就绪校验（Doc 7 v2.2 §11.4）。

    背景：D3（无编队 400 化）+ D4（注册不送机体）曾构成死锁——全库无任何
    机体获取通道时新号永远无法进入战斗。claim-starter 是破除死锁的最小
    获取通道（D6 解 1）：免费领一台最弱杂兵机，经济系统上线后重裁退役。
    """

    STARTER_MECHA_ID = "mech_grunt"

    # 起步包数值（Doc 17 场景 4.9）：占位值，经济内容立项时重定——数值变更
    # 只动这两处；材料取 data/items.json 现成低价值物品 mat_scrap
    STARTER_CREDITS = 500
    STARTER_MATERIALS: List[Tuple[str, str, int]] = [("mat_scrap", "material", 5)]

    @staticmethod
    async def assert_squad_ready(session: AsyncSession, user_id: int) -> UserSquad:
        """校验出战编队就绪，未就绪抛 SquadNotReadyError。

        分流口径：无任何机体 → STARTER_NOT_CLAIMED（指引领取）；
        有机体但无激活编队/编队为空/引用了不存在的机体 → NO_ACTIVE_SQUAD
        （指引编队设置）。供 simulate 的 400 前置校验复用。

        Returns:
            UserSquad: 校验通过的出战编队（调用方可直接透传装配，免二次查询）。
        """
        mechas = await UserAssetRepository.list_user_mechas(session, user_id)
        if not mechas:
            raise SquadNotReadyError(
                "STARTER_NOT_CLAIMED",
                "尚未领取初始机体，请先领取（POST /user/mechas/claim-starter）",
            )
        owned_ids = {m.id for m in mechas}
        squad = await UserAssetRepository.get_active_squad(session, user_id)
        if squad is None or not squad.mecha_ids:
            raise SquadNotReadyError(
                "NO_ACTIVE_SQUAD",
                "没有有效的出战编队，请先创建或激活编队",
            )
        invalid = [mid for mid in squad.mecha_ids if mid not in owned_ids]
        if invalid:
            raise SquadNotReadyError(
                "NO_ACTIVE_SQUAD",
                f"出战编队引用了不存在的机体 {invalid}，请修正编队",
            )
        return squad

    @staticmethod
    async def assert_mechas_owned(
        session: AsyncSession, user_id: int, mecha_ids: List[int]
    ) -> None:
        """校验机体归属：不在用户名下的 ID 抛 MechasNotOwnedError。

        归属规则单点维护（Doc 7 v2.2 §11.5 引用完整性），供创建编队与
        PVE locked_mechas 的 400 前置校验复用。
        """
        owned_ids = await UserAssetRepository.list_user_mecha_ids(session, user_id)
        invalid = [mid for mid in mecha_ids if mid not in owned_ids]
        if invalid:
            raise MechasNotOwnedError(invalid)

    @staticmethod
    async def claim_starter(
        session: AsyncSession, user_id: int, loader: Optional["DataLoader"] = None
    ) -> dict:
        """领取初始机体：工兵机 + 默认编队 + 起步包，同事务一次落库（Doc 17 场景 4.9）。

        并发防线：对 users 行 with_for_update 串行化同用户并发领取
        （SQLite 单写者下退化为无锁，生产 PostgreSQL 生效）。已有机体时
        返回 claimed=False 的终态快照——由 API 层翻译为 409 终态等价成功
        （附当前首机与出战编队摘要，超时重试据此自愈展示）。

        起步包（起步信用点 + 起步材料）凭回执 starter:{user_id} 走发放门面
        建票据，随即整批放行入包——「一步拿到」语义，不留 pending（新号
        保底 50 格容量必够）；票据与台账留档共同兜防重发。任何一环失败
        整笔随事务回滚（禁止只领到一半）。

        Args:
            session: 数据库异步会话（事务边界归调用方）。
            user_id: 领取用户 ID。
            loader: 物品模板库；None 时门面跳过模板校验并回退 Mock 容量
                （测试缝隙），生产接线必须传。

        Returns:
            dict: {"claimed": bool, "mecha": UserMecha, "squad": UserSquad}。

        Raises:
            ValueError: 用户不存在。
            GrantManifestMismatchError: 起步包清单校验失败——清单是代码内置
                常量，不符属数据事故，直接上抛由 API 层先提交留档再 400。
        """
        user_row = await UserRepository.get_by_id(session, user_id, for_update=True)
        if user_row is None:
            raise ValueError("用户不存在")

        mechas = await UserAssetRepository.list_user_mechas(session, user_id)
        if mechas:
            squad = await UserAssetRepository.get_active_squad(session, user_id)
            return {"claimed": False, "mecha": mechas[0], "squad": squad}

        mecha = await UserAssetRepository.create_user_mecha(
            session, user_id, OnboardingService.STARTER_MECHA_ID
        )

        # 编队防御性补齐（评审 B3）：判重闸只保证"无机体"，不保证"无编队"
        # ——玩家可先手建空编队。无编队才新建；已有则塞入首个编队并激活。
        squads = await UserAssetRepository.list_user_squads(session, user_id)
        if squads:
            squad = squads[0]
            if mecha.id not in squad.mecha_ids:
                squad.mecha_ids = [*squad.mecha_ids, mecha.id]
                squad.updated_at = datetime.now(timezone.utc)
                await session.flush()
        else:
            squad = await UserAssetRepository.create_user_squad(
                session, user_id, "默认编队", [mecha.id]
            )

        activated = await UserAssetRepository.set_active_squad(session, user_id, squad.id)

        # 起步包：同事务 submit_grant + 立即放行（场景 4.9「一步拿到」）。
        # 回执与票据/台账的防重发由门面承担，本层不重复记账。
        item_system = ItemSystem(session, loader=loader)
        ticket = await item_system.submit_grant(
            user_id,
            make_receipt_id("starter", str(user_id)),
            "starter",
            equipments=[],
            items=[
                ItemData(item_id=item_id, item_type=item_type, quantity=quantity)
                for item_id, item_type, quantity in OnboardingService.STARTER_MATERIALS
            ],
            credits=OnboardingService.STARTER_CREDITS,
        )
        await item_system.accept_ticket(user_id, ticket.id)

        return {"claimed": True, "mecha": mecha, "squad": activated}
