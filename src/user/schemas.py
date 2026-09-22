"""
用户领域 Pydantic 模型 (DTO)

定义用户相关的数据传输对象，用于 API 请求/响应验证。

设计原则:
- 复用 src/models.py 中的现有模型
- 提供清晰的输入输出接口
- 支持游戏存档的 JSON 序列化/反序列化
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List, Literal
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
    """用户响应模型

    has_mecha / has_active_squad 为新号引导状态位（Doc 7 v2.2 §11.4）：
    前端据此主动触发领取引导，而非等玩家踩 400 被动发现。
    credits 为信用点余额（Doc 17 场景 4.5：买前看得清定价与余额），
    from_attributes 下自动读取 users.credits 列。
    """
    id: int
    status: str
    credits: int = 0
    created_at: datetime
    has_mecha: bool = False
    has_active_squad: bool = False

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

class AffixEntry(BaseModel):
    """词条槽对象"""
    id: str       # 词条 ID，关联 data/affixes.json
    t: int        # 档位 1~4

class EquipmentRandomStats(BaseModel):
    """装备随机词条与强化属性契约 (参考 Doc 8)"""
    ilvl: int = 0
    affixes: List[AffixEntry] = Field(default_factory=list, max_length=3)
    skill: Optional[str] = None  # 抽中的技能 ID

    @property
    def color(self) -> int:
        """根据物品词条和技能数即时计算颜色分以标识稀有度 (Doc 8)"""
        return min(4, len(self.affixes) + (2 if self.skill else 0))

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
    equipped_mecha_id: Optional[int] = None
    equipped_slot_idx: Optional[int] = None
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

class StarterClaimResponse(BaseModel):
    """初始机体领取响应（Doc 7 v2.2 §11.4）"""
    mecha: UserMechaDB
    squad: UserSquadDB

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
    # 常驻入口「临时货舱有 N 件待处理」的数据源（Doc 17 场景 4.1/4.3，无寄存=0）
    pending_tickets: int = 0

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

class MaterialItemDB(UserItemDB):
    """材料条目 = UserItemDB + 展示名。

    name 查不到模板时回退 item_id——loot 掉的 item_id 可能不在
    items.json，不能因展示断链（Doc 17 场景 4.14 旧档照常显示）。
    """
    name: str

class InventoryItemsResponse(BaseModel):
    """背包资产清单响应（Doc 17 场景 4.8）。

    信用点单独显示、穿戴中装备单列一栏（不占货舱格）、材料带展示名。
    """
    credits: int
    equipments: List[UserEquipmentDB]   # 未装备（占格）
    equipped: List[UserEquipmentDB]     # 穿戴中（不占格，单列）
    items: List[MaterialItemDB]

class TicketView(BaseModel):
    """票据画面形状——字段与门面 ItemSystem._ticket_view 一一对应。

    附录 A4：占用格数与还差几格由系统算好定死，画面只显示、不改数。
    equipments/items 为票据 manifest 的原始条目（装备含随机词条、材料含数量）。
    """
    ticket_id: int
    receipt_id: str
    source: str
    status: str
    credits: int
    equipments: List[Dict[str, Any]] = Field(default_factory=list)
    items: List[Dict[str, Any]] = Field(default_factory=list)
    required_slots: int
    shortfall: int

class TicketListResponse(BaseModel):
    """待处理票据清单响应（GET /inventory/tickets，场景 4.3 常驻入口数据源）。"""
    tickets: List[TicketView] = Field(default_factory=list)

class DiscardTicketItemRequest(BaseModel):
    """逐件丢弃寄存物请求（二次确认在画面层，Doc 17 附录 A3）。"""
    entry_type: Literal["equipment", "item"]
    index: int = Field(ge=0, description="票据清单对应列表中的下标")

class DiscardItemRequest(BaseModel):
    """背包材料丢弃请求（丢弃直接生效不可恢复，Doc 17 §8 D7）。"""
    quantity: int = Field(gt=0)


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
