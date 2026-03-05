"""
数据库模块

提供数据库基础设施和 ORM 模型的统一导出接口
"""

from .base import (
    Base,
    async_engine,
    AsyncSessionLocal,
    init_db,
    close_db,
    TimestampMixin,
    SoftDeleteMixin,
)

from .models import User, GameSave
from .session import get_async_session, create_session, ensure_session

__all__ = [
    # 基础配置
    "Base",
    "async_engine",
    "AsyncSessionLocal",
    "init_db",
    "close_db",
    "TimestampMixin",
    "SoftDeleteMixin",
    # ORM 模型
    "User",
    "GameSave",
    # 会话管理
    "get_async_session",
    "create_session",
    "ensure_session",
]
