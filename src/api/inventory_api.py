"""背包系统 REST API (Inventory API)

提供背包状态查询、物品列表获取及超载确认处理的 HTTP 接口。

设计原则：
    - 所有接口均需 JWT 认证（通过 get_current_user 依赖注入）
    - 数据库会话由 get_async_session 自动管理
    - 响应格式遵循 RESTful 规范

端点概览：
    - GET  /inventory/status     - 获取货舱容量状态
    - GET  /inventory/items       - 列出背包内所有资产
    - POST /inventory/finalize    - 超载确认处理（核心业务逻辑）

参考文档：Doc 12 背包与货舱系统设计
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from src.database.session import get_async_session
from src.database.models import User, UserEquipment, UserItem
from src.user.dependencies import get_current_user
from src.user.inventory import InventoryService
from src.user.schemas import (
    InventoryStatus,
    UserEquipmentDB,
    UserItemDB,
    AddResult,
    EquipmentData,
    ItemData
)
from src.api.context import get_loader

router = APIRouter(prefix="/inventory", tags=["背包系统"])

@router.get("/status", response_model=InventoryStatus)
async def get_inventory_status(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """获取当前背包容量状态。

    返回玩家的货舱使用情况，包括：
        - current: 当前占用格子数
        - capacity: 容量上限（基于拥有的母舰）
        - available: 剩余可用格子数

    Args:
        current_user: 当前登录用户（由JWT Token解析）
        session: 数据库会话

    Returns:
        InventoryStatus: 包含 current、capacity、available 的状态对象

    Example:
        >>> GET /api/inventory/status
        {
            "current": 15,
            "capacity": 80,
            "available": 65
        }
    """
    loader = get_loader()
    service = InventoryService(session, loader=loader)
    return await service.get_status(current_user.id)

@router.get("/items")
async def list_inventory_items(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """列出背包内所有未装备的资产（装备 + 材料）。

    查询两类资产：
        - equipments: 未装备的武器/防具（is_equipped=False）
        - items: 所有堆叠材料（按 item_id 合并后）

    Args:
        current_user: 当前登录用户（由JWT Token解析）
        session: 数据库会话

    Returns:
        Dict[str, List]: 包含 equipments 和 items 两个列表的字典

    Example:
        >>> GET /api/inventory/items
        {
            "equipments": [
                {
                    "id": 42,
                    "equipment_id": "beam_rifle_mk2",
                    "enhancement_level": 3,
                    "random_stats": {"attack": 15},
                    "is_locked": false,
                    "is_equipped": false
                }
            ],
            "items": [
                {
                    "id": 1,
                    "item_id": "titanium_alloy",
                    "item_type": "ALLOY",
                    "quantity": 500
                }
            ]
        }
    """
    from sqlalchemy import select

    # 1. 未装备的武器/防具
    stmt_equip = select(UserEquipment).where(
        UserEquipment.user_id == current_user.id,
        UserEquipment.is_equipped == False
    )
    equip_res = await session.execute(stmt_equip)
    equipments = [UserEquipmentDB.model_validate(e) for e in equip_res.scalars().all()]

    # 2. 堆叠材料
    stmt_item = select(UserItem).where(UserItem.user_id == current_user.id)
    item_res = await session.execute(stmt_item)
    items = [UserItemDB.model_validate(i) for i in item_res.scalars().all()]

    return {
        "equipments": equipments,
        "items": items
    }

@router.post("/finalize")
async def finalize_overload(
    add_equipments: List[EquipmentData],
    add_items: List[ItemData],
    discard_ids: List[int],
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session)
):
    """超载确认处理（核心业务逻辑）。

    当 PVE 战斗结算后，若玩家货舱溢出，客户端需引导玩家丢弃部分物品
    后调用此接口完成最终确认。流程如下：

        1. 彻底销毁 discard_ids 指定的现有装备（对应 UI 中的勾选丢弃）
        2. 验证丢弃列表的合法性（数量匹配、权属校验）
        3. 尝试将新获得的资产写入数据库
        4. 若写入后依然超载，则报错拦截（防止客户端作弊直接跳过清理）

    Args:
        add_equipments: 待添加的装备列表（来自 PVE 结算）
        add_items: 待添加的材料列表（来自 PVE 结算）
        discard_ids: 玩家选择丢弃的装备 ID 列表
        current_user: 当前登录用户
        session: 数据库会话

    Returns:
        Dict[str, str]: {"status": "success"} 表示操作成功

    Raises:
        HTTPException 400: 丢弃列表包含无效资产或已装备资产
        HTTPException 400: 货舱空间仍然不足，需要丢弃更多物品

    Example:
        >>> POST /api/inventory/finalize
        {
            "add_equipments": [
                {"equipment_id": "beam_saber", "enhancement_level": 0, "random_stats": {}}
            ],
            "add_items": [
                {"item_id": "titanium_alloy", "item_type": "ALLOY", "quantity": 100}
            ],
            "discard_ids": [42, 43]
        }
        Response: {"status": "success"}

    Note:
        [安全性增强] 显式验证 discard_ids 的合法性
        [TODO] 验证 add_assets 源自合法的 PVE 结算会话（需 pending_rewards 表支持）
    """
    from sqlalchemy import delete, select, func
    loader = get_loader()
    service = InventoryService(session, loader=loader)

    # 1. 显式验证待丢弃物品
    if discard_ids:
        # 去重处理
        unique_discard_ids = list(set(discard_ids))
        check_stmt = select(func.count(UserEquipment.id)).where(
            UserEquipment.id.in_(unique_discard_ids),
            UserEquipment.user_id == current_user.id,
            UserEquipment.is_equipped == False
        )
        existing_count = (await session.execute(check_stmt)).scalar() or 0
        if existing_count != len(unique_discard_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="丢弃列表中包含无效资产或已装备资产"
            )

        # 执行物理删除
        stmt = delete(UserEquipment).where(
            UserEquipment.id.in_(unique_discard_ids),
            UserEquipment.user_id == current_user.id,
            UserEquipment.is_equipped == False
        )
        await session.execute(stmt)

    # 2. TODO: 验证 add_equipments/add_items 是否与当前活跃的 PveSession.pending_rewards 匹配
    # 防止客户端直接构造请求刷取非结算物品

    # 3. 执行添加逻辑
    result = await service.add_assets(current_user.id, add_equipments, add_items)

    if result == AddResult.OVERFLOW:
        # 如果处理完丢弃任务后依然塞不下，说明玩家没清够
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="货舱空间仍然不足，请丢弃更多物品"
        )

    await session.commit()
    return {"status": "success"}

