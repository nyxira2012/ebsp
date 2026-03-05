"""
数据库 ORM 模型定义

定义用户和游戏存档的 SQLAlchemy 映射表。

设计原则：
- 使用 sqlalchemy.JSON 存储游戏快照，确保 PostgreSQL 兼容
- 支持软删除和多存档位
- 预留扩展字段
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional, Dict, Any

from .base import Base, TimestampMixin, SoftDeleteMixin

# ==============================================================================
# 用户表 (Users)
# ==============================================================================

class User(Base, TimestampMixin, SoftDeleteMixin):
    """用户账户模型

    存储用户认证信息和基础配置
    """
    __tablename__ = "users"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 认证信息
    username: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # 扩展字段 (预留)
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        default=None,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default="active",
        nullable=False,
    )

    # 关系: 用户的游戏存档
    saves: Mapped[list["GameSave"]] = relationship(
        "GameSave",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', status='{self.status}')>"

# ==============================================================================
# 游戏存档表 (GameSaves)
# ==============================================================================

class GameSave(Base, TimestampMixin):
    """游戏存档模型

    存储用户的游戏进度快照，支持多存档位
    """
    __tablename__ = "game_saves"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 外键: 所属用户
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 存档元数据
    slot_id: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    save_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    is_deployed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # 存档数据 (JSON 快照)
    save_data: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
    )

    # 关系: 所属用户
    user: Mapped["User"] = relationship(
        "User",
        back_populates="saves",
    )

    def __repr__(self) -> str:
        return f"<GameSave(id={self.id}, user_id={self.user_id}, slot_id={self.slot_id}, name='{self.save_name}')>"

    @property
    def version(self) -> str:
        """获取存档版本号"""
        return self.save_data.get("version", "1.0")

    @property
    def metadata_summary(self) -> Dict[str, Any]:
        """获取存档元数据摘要"""
        return self.save_data.get("metadata", {})

# ==============================================================================
# 复合索引 (可选优化)
# ==============================================================================

# 为常用查询创建复合索引
# - 用户名查询 (已在 username 字段上定义)
# - 用户存档查询 (已在 user_id 字段上定义)
# - 用户 + 存档位唯一约束 (建议在 Alembic 迁移中添加)
