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

    # 关系: 用户的资产
    mechas: Mapped[list["UserMecha"]] = relationship(
        "UserMecha", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    pilots: Mapped[list["UserPilot"]] = relationship(
        "UserPilot", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    equipments: Mapped[list["UserEquipment"]] = relationship(
        "UserEquipment", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    squads: Mapped[list["UserSquad"]] = relationship(
        "UserSquad", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    battle_records: Mapped[list["BattleRecord"]] = relationship(
        "BattleRecord", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', status='{self.status}')>"

# ==============================================================================
# 用户资产表 (User Assets - Mixed Relational Architecture)
# ==============================================================================

class UserMecha(Base, TimestampMixin):
    """用户机体资产表
    
    使用 JSONB 存储不固定的养成维度的进度（如血量改造、涂装等）。
    """
    __tablename__ = "user_mechas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mech_id: Mapped[str] = mapped_column(String(50))  # 对应 mechas.json
    nickname: Mapped[str] = mapped_column(String(100), default="")
    
    # 养成数据 (JSONB)
    # Default: {"hp": 0, "en": 0, "armor": 0, "mobility": 0}
    upgrades: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship("User", back_populates="mechas")

class UserPilot(Base, TimestampMixin):
    """用户驾驶员资产表"""
    __tablename__ = "user_pilots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    pilot_id: Mapped[str] = mapped_column(String(50))  # 对应 pilots.json
    
    # 养成数据 (等级、经验、技能点等)
    progression: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship("User", back_populates="pilots")

class UserEquipment(Base, TimestampMixin):
    """用户装备资产表"""
    __tablename__ = "user_equipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    equipment_id: Mapped[str] = mapped_column(String(50))  # 对应 equipments.json/weapons.json
    enhancement_level: Mapped[int] = mapped_column(Integer, default=0)
    
    # 随机词条与强化数据
    random_stats: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship("User", back_populates="equipments")

class UserSquad(Base, TimestampMixin):
    """用户编队表"""
    __tablename__ = "user_squads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100), default="小队 A")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # 出战机体的 user_mechas.id 列表
    mecha_ids: Mapped[list] = mapped_column(JSON, default=list)

    user: Mapped["User"] = relationship("User", back_populates="squads")

# ==============================================================================
# 录像持久化表 (Replays)
# ==============================================================================

class BattleRecord(Base, TimestampMixin):
    """战斗录像表
    
    存储完整计算后的 MechaSnapshot 序列化 JSON，以支撑绝对回放，不受平衡性改版的影响。
    """
    __tablename__ = "battle_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    
    # 完整的 Snapshot Dictionary (或整个战报上下文)
    snapshot_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="battle_records")

# ==============================================================================
# 复合索引 (可选优化)
# ==============================================================================

# 为常用查询创建复合索引
# - 用户名查询 (已在 username 字段上定义)
# - 用户存档查询 (已在 user_id 字段上定义)
# - 用户 + 存档位唯一约束 (建议在 Alembic 迁移中添加)
