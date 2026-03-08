"""
用户领域 Pydantic 模型 (DTO)

定义用户相关的数据传输对象，用于 API 请求/响应验证。

设计原则:
- 复用 src/models.py 中的现有模型
- 提供清晰的输入输出接口
- 支持游戏存档的 JSON 序列化/反序列化
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from src.models import UserMothershipData

# ==============================================================================
# 用户 DTO
# ==============================================================================

class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=32, description="用户名")
    email: Optional[str] = Field(None, max_length=255, description="邮箱地址")

class UserCreate(UserBase):
    """用户注册请求模型"""
    password: str = Field(..., min_length=6, max_length=100, description="密码")

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """验证用户名格式"""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('用户名只能包含字母、数字、下划线和连字符')
        return v

class UserResponse(UserBase):
    """用户响应模型"""
    id: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}

class UserLogin(BaseModel):
    """用户登录请求模型"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")

# ==============================================================================
# 用户资产 DTO (JSONB Contracts)
# ==============================================================================

class MechaUpgrades(BaseModel):
    """机体养成进度契约 (对应 UserMecha.upgrades JSONB 字段)"""
    hp: int = 0
    en: int = 0
    armor: int = 0
    mobility: int = 0

class PilotProgression(BaseModel):
    """驾驶员养成进度契约 (对应 UserPilot.progression JSONB 字段)"""
    level: int = 1
    exp: int = 0
    skill_points: int = 0

class EquipmentRandomStats(BaseModel):
    """装备随机词条与强化属性契约"""
    # 可以在这里预留随机词条槽位，或者附加属性加成
    bonus_attack: int = 0
    bonus_defense: int = 0
    special_effects: list[str] = Field(default_factory=list)

# ==============================================================================
# DB 读取模型 (Response DTOs)
# ==============================================================================

class UserMechaDB(BaseModel):
    id: int
    user_id: int
    mech_id: str
    nickname: str
    upgrades: MechaUpgrades
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class UserPilotDB(BaseModel):
    id: int
    user_id: int
    pilot_id: str
    progression: PilotProgression
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class UserEquipmentDB(BaseModel):
    id: int
    user_id: int
    equipment_id: str
    enhancement_level: int
    is_locked: bool
    is_equipped: bool
    random_stats: EquipmentRandomStats
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class UserItemDB(BaseModel):
    id: int
    user_id: int
    item_id: str
    item_type: str
    quantity: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class UserSquadDB(BaseModel):
    id: int
    user_id: int
    name: str
    is_active: bool
    mecha_ids: list[int]  # List of user_mechas.id
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class BattleRecordDB(BaseModel):
    id: int
    user_id: int
    snapshot_data: Dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}

# ==============================================================================
# 认证 DTO
# ==============================================================================

class Token(BaseModel):
    """JWT Token 响应模型"""
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    """Token 数据模型"""
    username: Optional[str] = None
    user_id: Optional[int] = None

# ==============================================================================
# 背包与道具 DTO (Inventory)
# ==============================================================================

class InventoryStatus(BaseModel):
    """背包状态"""
    current: int      # 当前占用格数
    capacity: int     # 容量上限
    available: int    # 剩余可用格数

class AddResult(Enum):
    """添加结果"""
    SUCCESS = "success"
    OVERFLOW = "overflow"

class EquipmentData(BaseModel):
    """待添加的装备数据"""
    equipment_id: str
    enhancement_level: int = 0
    random_stats: Dict[str, Any] = Field(default_factory=dict)

class ItemData(BaseModel):
    """待添加的材料数据"""
    item_id: str
    item_type: str = "material"
    quantity: int = 1


# ==============================================================================
# 母舰 DTO (Mothership)
# ==============================================================================

class UserMothershipDB(BaseModel):
    id: int
    user_id: int
    data: UserMothershipData
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class MothershipCatalogItem(BaseModel):
    id: str
    name: str
    generation: int
    tier: str
    engine_level: int
    hp_regen_per_min: int
    en_regen_per_min: int
    region_level: int
    cargo_capacity: int
    emergency_extraction_tax: float
    price: int
    sell_price_ratio: float
    required_chapter: Optional[int] = None
    required_achievement: Optional[str] = None
    owned: bool
    current: bool

class MothershipPurchaseRequest(BaseModel):
    mothership_id: str

class MothershipSwitchRequest(BaseModel):
    mothership_id: str
