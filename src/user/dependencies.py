"""
用户认证依赖模块

提供 FastAPI 依赖项，统一管理 JWT 认证逻辑。

设计原则:
- 单一定义，避免重复
- 统一的用户状态检查（包括软删除）
- 支持可选认证和强制认证
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, cast

from src.database.models import User
from src.database.session import get_async_session
from src.user.auth import decode_access_token
from src.user.repository import UserRepository


# ==============================================================================
# 安全配置
# ==============================================================================

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


# ==============================================================================
# 认证依赖项
# ==============================================================================

async def _get_user_by_token(token: str, session: AsyncSession) -> Optional[User]:
    """
    从 Token 获取用户的内部函数

    Args:
        token: JWT Token 字符串
        session: 数据库会话

    Returns:
        用户对象，Token 无效或用户不存在返回 None
    """
    try:
        payload = decode_access_token(token)

        user_id: int = cast(int, payload.get("user_id"))
        if user_id is None:
            return None

        # 通过 ID 获取用户（已包含软删除检查）
        user = await UserRepository.get_by_id(session, user_id)

        # 额外检查用户状态
        if user is None or user.status != "active":
            return None

        return user

    except HTTPException:
        return None
    except Exception:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """
    强制认证依赖：获取当前用户

    用于需要登录的接口，未登录抛出 401 异常

    Raises:
        HTTPException: 未登录或 Token 无效
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await _get_user_by_token(credentials.credentials, session)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据或用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    session: AsyncSession = Depends(get_async_session),
) -> Optional[User]:
    """
    可选认证依赖：获取当前用户

    如果提供了有效 Token 则返回用户，否则返回 None
    不抛出异常，支持未登录用户访问
    """
    if credentials is None:
        return None

    return await _get_user_by_token(credentials.credentials, session)


# ==============================================================================
# 导出
# ==============================================================================

__all__ = [
    "get_current_user",
    "get_optional_user",
    "security",
    "optional_security",
]
