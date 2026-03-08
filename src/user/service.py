"""
用户业务逻辑层 (Service Layer)

负责协调 Repository 进行复杂的跨表业务操作，并处理核心业务规则。
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, TYPE_CHECKING

from src.user.repository import MothershipRepository
from src.pve.services import MothershipIntegrationService
from src.database.models import User

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
        """购买母舰的完整业务流"""
        
        # 1. PVE 锁定检查 (P0)
        if await MothershipIntegrationService.is_pve_session_active(session, user.id):
            raise ValueError("PVE 出征期间全盘系统锁定，无法购买母舰")

        # 2. 静态配置检查
        if mothership_id not in loader.motherships:
            raise ValueError("无效的母舰型号")
        
        m_config = loader.motherships[mothership_id]

        # 3. 拥有状态检查
        db_mothership = await MothershipRepository.get_by_user_id(session, user.id)
        if db_mothership and mothership_id in db_mothership.data.get("owned_ids", []):
             raise ValueError("玩家已拥有该母舰")

        # 4. 经济系统检查 (P0)
        # TODO: 待钱包系统/信用点字段上线。目前由于不改数据库，采取硬编码模拟
        # 假设 User 模型未来会有 credits 字段： user.credits
        user_credits = getattr(user, "credits", 9999999) # 临时硬编码：默认拥有无限信用点
        if user_credits < m_config.price:
            raise ValueError(f"信用点不足。需要 {m_config.price}，当前 {user_credits}")

        # 5. 前置条件检查 (P0)
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

        # 6. 执行购买
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
