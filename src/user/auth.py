"""
JWT 认证模块

提供 JWT Token 的签发和解析功能。

安全策略:
- 使用 HS256 算法
- 设置合理的过期时间
- 密钥从环境变量读取 (开发环境使用默认值)
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, status

# ==============================================================================
# JWT 配置
# ==============================================================================

# 从环境变量读取密钥，生产环境必须设置此变量
# 开发环境使用默认密钥（仅用于本地测试）
SECRET_KEY = os.getenv(
    "EBSP_JWT_SECRET_KEY",
    "ebsp_dev_secret_key_change_in_production_please"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 天

# 开发环境警告
if os.getenv("EBSP_JWT_SECRET_KEY") is None:
    import warnings
    warnings.warn(
        "⚠️ 使用默认 JWT 密钥 (仅供开发环境)! "
        "生产环境请设置 EBSP_JWT_SECRET_KEY 环境变量。"
    )

# ==============================================================================
# Token 操作
# ==============================================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT Token

    Args:
        data: 要编码的数据 (如 {"sub": username, "user_id": 123})
        expires_delta: 过期时间增量，默认使用 ACCESS_TOKEN_EXPIRE_MINUTES

    Returns:
        JWT Token 字符串
    """
    to_encode = data.copy()

    # 使用 datetime.now(timezone.utc) 替代已弃用的 datetime.utcnow()
    now = datetime.now(timezone.utc)

    # 设置过期时间
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    # 签发 Token
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    """
    解析 JWT Token

    Args:
        token: JWT Token 字符串

    Returns:
        解码后的数据字典

    Raises:
        HTTPException: Token 无效或过期
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"无效的认证凭据: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
