"""
用户领域模块

提供用户和存档管理的统一导出接口
"""

from .security import hash_password, verify_password
from .schemas import (
    UserCreate,
    UserResponse,
    UserLogin,
    Token,
    TokenData,
    GameSaveCreate,
    GameSaveUpdate,
    GameSaveResponse,
    SaveData,
    SaveMetadata,
)
from .repository import UserRepository, GameSaveRepository
from .auth import create_access_token, decode_access_token, SECRET_KEY, ALGORITHM
from .dependencies import get_current_user, get_optional_user

__all__ = [
    # 安全
    "hash_password",
    "verify_password",
    # DTO
    "UserCreate",
    "UserResponse",
    "UserLogin",
    "Token",
    "TokenData",
    "GameSaveCreate",
    "GameSaveUpdate",
    "GameSaveResponse",
    "SaveData",
    "SaveMetadata",
    # Repository
    "UserRepository",
    "GameSaveRepository",
    # Auth
    "create_access_token",
    "decode_access_token",
    "SECRET_KEY",
    "ALGORITHM",
    # Dependencies
    "get_current_user",
    "get_optional_user",
]
