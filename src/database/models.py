"""
数据库 ORM 模型定义

定义用户和游戏存档的 SQLAlchemy 映射表。

设计原则：
- 使用 sqlalchemy.JSON 存储游戏快照，确保 PostgreSQL 兼容
- 支持软删除和多存档位
- 预留扩展字段
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON, Text, UniqueConstraint
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
    items: Mapped[list["UserItem"]] = relationship(
        "UserItem", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    squads: Mapped[list["UserSquad"]] = relationship(
        "UserSquad", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    battle_records: Mapped[list["BattleRecord"]] = relationship(
        "BattleRecord", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    mothership: Mapped[Optional["UserMothership"]] = relationship(
        "UserMothership", back_populates="user", cascade="all, delete-orphan", lazy="selectin", uselist=False
    )
    pve_sessions: Mapped[list["PveSession"]] = relationship(
        "PveSession", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
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
    """用户装备资产表。

    存储玩家获得的所有装备（武器、防具等）。每件装备独立存储，
    不可堆叠，因为具有独立的随机词条和强化等级。

    容量计算：
        - is_equipped=False: 计入货舱占用（每件1格）
        - is_equipped=True: 不计入容量（已装备在机体上）

    Attributes:
        id: 主键
        user_id: 所属用户ID
        equipment_id: 装备ID（对应 data/equipments.json）
        enhancement_level: 强化等级（0-10）
        is_locked: 是否锁定（防误删）
        is_equipped: 是否已装备
        random_stats: 随机词条字典（如 {"attack": 15, "crit_rate": 5}）
    """
    __tablename__ = "user_equipments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    equipment_id: Mapped[str] = mapped_column(String(50))  # 对应 equipments.json/weapons.json
    enhancement_level: Mapped[int] = mapped_column(Integer, default=0)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_equipped: Mapped[bool] = mapped_column(Boolean, default=False)

    # 随机词条与强化数据
    random_stats: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship("User", back_populates="equipments")

class UserItem(Base, TimestampMixin):
    """用户通用物品表（可堆叠材料）。

    存储同质化的材料类物品（合金、碎片、遗迹等）。
    同一种材料只占用1个货舱格子，无论数量多少。

    堆叠规则：
        - 按 (user_id, item_id) 唯一约束
        - 同类材料自动合并数量

    Attributes:
        id: 主键
        user_id: 所属用户ID
        item_id: 物品ID（对应 data/items.json）
        item_type: 物品类型（ALLOY合金、SHARD碎片、RELIC遗迹等）
        quantity: 拥有数量

    Constraints:
        uq_user_item: 用户+物品唯一约束，确保堆叠行为
    """
    __tablename__ = "user_items"
    __table_args__ = (UniqueConstraint("user_id", "item_id", name="uq_user_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[str] = mapped_column(String(50), index=True)
    item_type: Mapped[str] = mapped_column(String(20), default="material")
    quantity: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped["User"] = relationship("User", back_populates="items")

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

class UserMothership(Base, TimestampMixin):
    """用户母舰表"""
    __tablename__ = "user_motherships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, unique=True
    )
    
    # UserMothershipData (JSONB)
    data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship("User", back_populates="mothership")

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
# PVE 探索相关 (PVE Exploration)
# ==============================================================================

class PveSession(Base, TimestampMixin):
    """PVE 探索会话表
    
    用于记录玩家当前的副本进度、血量/能量状态以及尚未结算的掉落物。
    作为“断线保护”的核心：掉落物在被 finalize_overload 确定入库前，始终保存在此处。
    """
    __tablename__ = "pve_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active") # active, overloaded, settled, failed
    
    region_id: Mapped[str] = mapped_column(String(50))
    current_node: Mapped[int] = mapped_column(Integer, default=0)
    
    # 待领取的临时战利品 JSON (含装备和堆叠物品)
    pending_loot: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped["User"] = relationship("User", back_populates="pve_sessions")

# ==============================================================================
# 复合索引 (可选优化)
# ==============================================================================

# 为常用查询创建复合索引
# - 用户名查询 (已在 username 字段上定义)
# - 用户存档查询 (已在 user_id 字段上定义)
# - 用户 + 存档位唯一约束 (建议在 Alembic 迁移中添加)
