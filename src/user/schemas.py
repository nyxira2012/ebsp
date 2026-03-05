"""
用户领域 Pydantic 模型 (DTO)

定义用户相关的数据传输对象，用于 API 请求/响应验证。

设计原则:
- 复用 src/models.py 中的现有模型
- 提供清晰的输入输出接口
- 支持游戏存档的 JSON 序列化/反序列化
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime

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
# 存档 DTO
# ==============================================================================

class SaveMetadata(BaseModel):
    """存档元数据"""
    summary: str = Field(default="", description="存档摘要")
    last_area: str = Field(default="", description="最后所在区域")
    play_time: int = Field(default=0, description="游戏时长（秒）")

class SaveData(BaseModel):
    """完整存档数据结构"""
    version: str = Field(default="1.0", description="存档版本")
    mecha: Dict[str, Any] = Field(..., description="机体快照数据")
    metadata: SaveMetadata = Field(default_factory=SaveMetadata, description="存档元数据")

class GameSaveCreate(BaseModel):
    """创建存档请求模型"""
    slot_id: int = Field(..., ge=1, le=3, description="存档位 (1-3)")
    save_name: str = Field(..., min_length=1, max_length=100, description="存档名称")
    save_data: SaveData = Field(..., description="存档数据")

class GameSaveUpdate(BaseModel):
    """更新存档请求模型"""
    save_name: Optional[str] = Field(None, min_length=1, max_length=100, description="存档名称")
    is_deployed: Optional[bool] = Field(None, description="是否设为出战存档")
    save_data: Optional[SaveData] = Field(None, description="存档数据")

class GameSaveResponse(BaseModel):
    """存档响应模型"""
    id: int
    user_id: int
    slot_id: int
    save_name: str
    is_deployed: bool
    save_data: SaveData
    updated_at: datetime

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
