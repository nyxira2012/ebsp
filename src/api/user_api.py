"""
用户 API 路由

提供用户注册、登录、存档管理的 HTTP 接口。

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
    GameSaveCreate,
    GameSaveUpdate,
    GameSaveResponse,
    SaveData,
    SaveMetadata,
)
from src.user.repository import UserRepository, GameSaveRepository
from src.user.auth import create_access_token
from src.user.dependencies import get_current_user, get_optional_user
from src.models import MechaSnapshot

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
    """
    用户注册

    - **username**: 用户名 (3-32 字符)
    - **password**: 密码 (最少 6 字符)
    - **email**: 邮箱 (可选)
    """
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
    """
    用户登录

    - **username**: 用户名
    - **password**: 密码

    返回 JWT Token，需要在请求头中携带:
        Authorization: Bearer <token>
    """
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
):
    """获取当前用户信息"""
    return UserResponse.model_validate(current_user)

# ==============================================================================
# 游戏存档管理
# ==============================================================================

@router.get("/saves", response_model=List[GameSaveResponse])
async def list_saves(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """获取当前用户的所有存档"""
    saves = await GameSaveRepository.list_by_user(session, current_user.id)
    return [GameSaveResponse.model_validate(s) for s in saves]

@router.post("/saves", response_model=GameSaveResponse, status_code=status.HTTP_201_CREATED)
async def create_save(
    save_data: GameSaveCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    创建新存档

    - **slot_id**: 存档位 (1-3)
    - **save_name**: 存档名称
    - **save_data**: 存档数据 (包含 mecha 快照和 metadata)
    """
    try:
        save = await GameSaveRepository.create(session, current_user.id, save_data)
        await session.commit()
        return GameSaveResponse.model_validate(save)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

@router.get("/saves/{save_id}", response_model=GameSaveResponse)
async def get_save(
    save_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """获取指定存档详情"""
    save = await GameSaveRepository.get_by_id(session, save_id)

    if save is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="存档不存在",
        )

    # 验证权限
    if save.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该存档",
        )

    return GameSaveResponse.model_validate(save)

@router.put("/saves/{save_id}", response_model=GameSaveResponse)
async def update_save(
    save_id: int,
    update_data: GameSaveUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """更新存档 (名称、出战状态或数据)"""
    save = await GameSaveRepository.get_by_id(session, save_id)

    if save is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="存档不存在",
        )

    # 验证权限
    if save.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权修改该存档",
        )

    # 更新存档
    updated = await GameSaveRepository.update(
        session,
        save_id,
        save_name=update_data.save_name,
        is_deployed=update_data.is_deployed,
        save_data=update_data.save_data,
    )

    await session.commit()
    return GameSaveResponse.model_validate(updated)

@router.post("/saves/{save_id}/deploy", response_model=GameSaveResponse)
async def deploy_save(
    save_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """设置指定存档为出战存档"""
    save = await GameSaveRepository.get_by_id(session, save_id)

    if save is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="存档不存在",
        )

    # 验证权限
    if save.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作该存档",
        )

    # 设置出战
    deployed = await GameSaveRepository.set_deployed(session, current_user.id, save_id)
    await session.commit()
    return GameSaveResponse.model_validate(deployed)

@router.delete("/saves/{save_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_save(
    save_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """删除存档"""
    save = await GameSaveRepository.get_by_id(session, save_id)

    if save is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="存档不存在",
        )

    # 验证权限
    if save.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权删除该存档",
        )

    success = await GameSaveRepository.delete(session, save_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="存档不存在",
        )

    await session.commit()

@router.get("/saves/deployed/mecha", response_model=dict)
async def get_deployed_mecha(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    """
    获取当前出战存档的 MechaSnapshot 数据

    用于战斗模拟时加载用户的机体配置
    """
    deployed_save = await GameSaveRepository.get_deployed(session, current_user.id)

    if deployed_save is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="未设置出战存档",
        )

    # 从存档还原 MechaSnapshot
    mecha = GameSaveRepository.to_mecha_snapshot(deployed_save)

    return {
        "save_id": deployed_save.id,
        "mecha": mecha.model_dump(mode='json'),
    }

# ==============================================================================
# 辅助函数: 从 MechaSnapshot 创建存档数据
# ==============================================================================

def create_save_data_from_mecha(mecha: MechaSnapshot, summary: str = "", last_area: str = "") -> SaveData:
    """
    从 MechaSnapshot 创建存档数据

    用于战斗结束后保存进度

    Args:
        mecha: MechaSnapshot 运行时对象
        summary: 存档摘要
        last_area: 最后所在区域

    Returns:
        SaveData 对象
    """
    return SaveData(
        version="1.0",
        mecha=mecha.model_dump(mode='json'),
        metadata=SaveMetadata(
            summary=summary,
            last_area=last_area,
            play_time=0,
        ),
    )
