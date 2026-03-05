"""
数据库会话管理

提供 FastAPI 的依赖注入函数，用于在请求处理过程中获取数据库会话。

设计原则：
- 确保每个请求使用独立的异步会话
- 请求结束后自动关闭会话，防止连接泄漏
- 支持上下文变量追踪当前用户
"""

from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status
from typing import AsyncGenerator, Optional

# 动态导入以支持测试中的覆盖
def _get_session_factory():
    from .base import AsyncSessionLocal
    return AsyncSessionLocal

# ==============================================================================
# 会话依赖项
# ==============================================================================

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖项：获取异步数据库会话

    用法:
        @app.get("/users/{user_id}")
        async def get_user(user_id: int, session: AsyncSession = Depends(get_async_session)):
            ...

    设计说明:
        - 使用 yield 确保请求结束后自动关闭会话
        - 每个请求获得独立的会话实例
        - 自动处理事务回滚 (发生异常时)
    """
    AsyncSessionLocal = _get_session_factory()
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # 正常情况下提交事务
            await session.commit()
        except Exception:
            # 发生异常时回滚事务
            await session.rollback()
            raise
        finally:
            # 确保会话被关闭
            await session.close()

# ==============================================================================
# 会话工厂 (用于测试和后台任务)
# ==============================================================================

async def create_session() -> AsyncSession:
    """
    创建新的数据库会话

    用于:
        - 测试场景
        - 后台任务
        - 不在 FastAPI 上下文中但需要数据库访问的场景

    注意: 使用完毕后需要手动关闭会话
    """
    AsyncSessionLocal = _get_session_factory()
    return AsyncSessionLocal()

# ==============================================================================
# 辅助函数
# ==============================================================================

async def ensure_session(session: Optional[AsyncSession]) -> AsyncSession:
    """
    确保返回有效的会话对象

    如果传入的 session 为 None，则创建新会话。
    用于支持可选会话参数的函数。

    Args:
        session: 可选的现有会话

    Returns:
        有效的 AsyncSession 实例
    """
    if session is None:
        return await create_session()
    return session
