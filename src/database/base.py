"""
数据库基础设施配置

提供 SQLAlchemy 的基础配置，包括：
- DeclarativeBase: ORM 模型基类
- AsyncEngine: 异步数据库引擎
- 数据库连接配置

设计原则：确保代码可无缝迁移到 PostgreSQL，无需修改业务逻辑
"""

import os
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime, timezone
from typing import Optional

# ==============================================================================
# 数据库配置
# ==============================================================================

# 从环境变量读取数据库 URL，支持开发/生产环境切换
# 开发环境: SQLite
# 生产环境: PostgreSQL (推荐 JSONB 类型)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./db/ebsp.db"
)

# PostgreSQL JSON 类型说明:
# - SQLite 使用 sqlalchemy.JSON (存储为 TEXT)
# - PostgreSQL 可使用 sqlalchemy.JSON (自动映射为 JSONB)
# - 迁移到 PostgreSQL 时无需修改代码，SQLAlchemy 会自动优化
# - 如需显式使用 JSONB，可在生产环境配置中设置:
#   from sqlalchemy.dialects.postgresql import JSONB

from typing import Any

# 创建异步引擎
# echo=True 可在开发时输出 SQL 日志，生产环境建议设为 False
engine_kwargs: dict[str, Any] = {
    "echo": os.getenv("DB_ECHO", "false").lower() == "true",
}

# 测试环境需要 StaticPool 确保内存数据库一致性
if ":memory:" in DATABASE_URL:
    from sqlalchemy.pool import StaticPool
    engine_kwargs["poolclass"] = StaticPool
    engine_kwargs["connect_args"] = {"check_same_thread": False}
# SQLite 特定配置（非内存数据库）
elif "sqlite" in DATABASE_URL:
    engine_kwargs["connect_args"] = {"check_same_thread": False}

async_engine = create_async_engine(DATABASE_URL, **engine_kwargs)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    expire_on_commit=False,  # 避免对象在 commit 后自动过期
    autocommit=False,
    autoflush=False,
)

# ==============================================================================
# ORM 基类
# ==============================================================================

class Base(AsyncAttrs, DeclarativeBase):
    """所有 ORM 模型的基类

    继承自 AsyncAttrs 和 DeclarativeBase，提供：
    - 异步查询支持
    - 声明式模型定义
    - 自动表名生成
    """
    pass

# ==============================================================================
# 通用字段 Mixin
# ==============================================================================

def _utc_now() -> datetime:
    """获取当前 UTC 时间

    使用 datetime.now(timezone.utc) 替代已弃用的 datetime.utcnow()
    """
    return datetime.now(timezone.utc)

class TimestampMixin:
    """时间戳字段混入类

    为模型提供 created_at 和 updated_at 字段
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=_utc_now,
        onupdate=_utc_now,
        nullable=False,
    )

class SoftDeleteMixin:
    """软删除字段混入类

    为模型提供 deleted_at 字段，支持软删除
    """
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        default=None,
        nullable=True,
    )

    @property
    def is_deleted(self) -> bool:
        """检查记录是否已被软删除"""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """执行软删除"""
        self.deleted_at = _utc_now()

    def restore(self) -> None:
        """恢复软删除的记录"""
        self.deleted_at = None

# ==============================================================================
# 数据库初始化
# ==============================================================================

async def init_db() -> None:
    """初始化数据库

    在应用启动时调用，创建所有表
    注意：生产环境应使用 Alembic 进行迁移管理
    """
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def close_db() -> None:
    """关闭数据库连接

    在应用关闭时调用
    """
    await async_engine.dispose()
