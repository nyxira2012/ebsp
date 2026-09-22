"""
用户 API 路由

提供用户注册、登录、资产管理的 HTTP 接口。

设计原则:
- 使用 FastAPI 的依赖注入管理数据库会话
- JWT Token 认证（使用统一的认证依赖模块）
- RESTful API 风格
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from src.database.session import get_async_session
from src.database.models import User
from src.user.schemas import (
    UserCreate,
    UserResponse,
    UserLogin,
    Token,
    UserMechaDB,
    UserSquadDB,
    UserMothershipDB,
    MothershipCatalogItem,
    MothershipPurchaseRequest,
    MothershipSwitchRequest,
    StarterClaimResponse,
)
from src.user.repository import UserRepository, UserAssetRepository, MothershipRepository
from src.user.service import MechasNotOwnedError, OnboardingService, SquadNotReadyError
from src.user.auth import create_access_token
from src.user.dependencies import get_current_user
from src.user.item_system import GrantManifestMismatchError
from src.api.errors import commit_and_report_mismatch

# ==============================================================================
# 路由器
# ==============================================================================

router = APIRouter(prefix="/user", tags=["用户系统"])

# ==============================================================================
# 用户注册/登录
# ==============================================================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    session: AsyncSession = Depends(get_async_session),
):
    """用户注册"""
    try:
        user = await UserRepository.create(session, user_data)
        await session.commit()
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

@router.post("/login", response_model=Token)
async def login(
    user_data: UserLogin,
    session: AsyncSession = Depends(get_async_session),
):
    """用户登录"""
    user = await UserRepository.authenticate(session, user_data.username, user_data.password)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # 签发 Token
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id}
    )

    return Token(access_token=access_token)

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """获取当前用户信息（含新号引导状态位，Doc 7 v2.2 §11.4）"""
    resp = UserResponse.model_validate(current_user)
    mechas = await UserAssetRepository.list_user_mechas(session, current_user.id)
    resp.has_mecha = bool(mechas)
    resp.has_active_squad = await UserAssetRepository.get_active_squad(session, current_user.id) is not None
    return resp

# ==============================================================================
# 初始机体领取（Doc 7 v2.2 §11.4）
# ==============================================================================

@router.post("/mechas/claim-starter", response_model=StarterClaimResponse)
async def claim_starter_mecha(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """领取初始机体：旧式防卫工兵一台 + 编队补齐并激活 + 起步信用点与材料，
    一步到位（Doc 7 v2.2 §11.4 + Doc 17 场景 4.9）"""
    from src.api.context import get_loader

    try:
        result = await OnboardingService.claim_starter(
            session, current_user.id, loader=get_loader()
        )
    except GrantManifestMismatchError:
        # starter 清单是代码内置常量，走到这里属数据事故——与 pve/debug 同一
        # 收口：先提交 rejected 留档再 400「本批未发放，已记录」（回滚约束）
        await commit_and_report_mismatch(session)

    if not result["claimed"]:
        # 409 终态等价成功语义：detail 附当前首机与出战编队摘要，
        # 超时重试的前端据此自愈展示，不弹"领取失败"
        mecha = UserMechaDB.model_validate(result["mecha"])
        squad = (
            UserSquadDB.model_validate(result["squad"])
            if result["squad"] is not None
            else None
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "STARTER_ALREADY_CLAIMED",
                "message": "初始机体已领取过",
                "mecha": mecha.model_dump(mode="json"),
                "squad": squad.model_dump(mode="json") if squad else None,
            },
        )

    await session.commit()
    return StarterClaimResponse(
        mecha=UserMechaDB.model_validate(result["mecha"]),
        squad=UserSquadDB.model_validate(result["squad"]),
    )

# ==============================================================================
# 资产与编队 API (部分示例)
# ==============================================================================

@router.get("/mechas", response_model=List[UserMechaDB])
async def list_user_mechas(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """列出当前用户的所有机体"""
    mechas = await UserAssetRepository.list_user_mechas(session, current_user.id)
    return [UserMechaDB.model_validate(m) for m in mechas]

@router.post("/squads", response_model=UserSquadDB)
async def create_squad(
    name: str,
    mecha_ids: List[int],
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """创建一个新编队（成员归属校验：他人机体 ID → 400，Doc 7 v2.2 §11.5）"""
    try:
        await OnboardingService.assert_mechas_owned(session, current_user.id, mecha_ids)
    except MechasNotOwnedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": e.code,
                "message": "编队包含不属于你的机体",
                "mecha_ids": e.mecha_ids,
            },
        )
    squad = await UserAssetRepository.create_user_squad(session, current_user.id, name, mecha_ids)
    await session.commit()
    return UserSquadDB.model_validate(squad)

@router.post("/squads/{squad_id}/deploy", response_model=UserSquadDB)
async def set_active_squad(
    squad_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """设置活跃出战的小队"""
    squad = await UserAssetRepository.set_active_squad(session, current_user.id, squad_id)
    if not squad:
        raise HTTPException(status_code=404, detail="编队不存在")
    await session.commit()
    return UserSquadDB.model_validate(squad)

# ==============================================================================
# 母舰 API (Motherships)
# ==============================================================================

@router.get("/motherships", response_model=List[MothershipCatalogItem])
async def list_mothership_catalog(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """列出母舰目录和玩家所属状态"""
    db_mothership = await MothershipRepository.get_by_user_id(session, current_user.id)
    if not db_mothership:
        raise HTTPException(status_code=404, detail="未找到玩家母舰记录")
    
    # 获取所有的静态配置
    from src.api.context import get_loader
    loader = get_loader()
    
    owned_ids = db_mothership.data.get("owned_ids", [])
    current_id = db_mothership.data.get("current_id", "")
    
    result = []
    for m in loader.motherships.values():
        item = MothershipCatalogItem(
            **m.model_dump(),
            owned=(m.id in owned_ids),
            current=(m.id == current_id)
        )
        result.append(item)
    return result

@router.get("/motherships/current", response_model=UserMothershipDB)
async def get_current_mothership_state(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """获取玩家当前的母舰信息"""
    db_mothership = await MothershipRepository.get_by_user_id(session, current_user.id)
    if not db_mothership:
        raise HTTPException(status_code=404, detail="未找到玩家母舰记录")
    return UserMothershipDB.model_validate(db_mothership)

@router.post("/motherships/purchase", response_model=UserMothershipDB)
async def purchase_mothership(
    request: MothershipPurchaseRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """购买并装备一艘新的母舰"""
    from src.api.presentation_api import get_loader
    from src.user.service import MothershipService
    loader = get_loader()
    
    try:
        updated = await MothershipService.purchase_mothership(
            session, current_user, request.mothership_id, loader
        )
        await session.commit()
        return UserMothershipDB.model_validate(updated)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/motherships/switch", response_model=UserMothershipDB)
async def switch_mothership(
    request: MothershipSwitchRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """切换当前启用的母舰"""
    from src.user.service import MothershipService
    
    try:
        updated = await MothershipService.switch_mothership(
            session, current_user.id, request.mothership_id
        )
        await session.commit()
        return UserMothershipDB.model_validate(updated)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
