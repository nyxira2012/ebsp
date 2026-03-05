"""
用户安全模块

提供密码哈希和验证功能，使用 bcrypt 算法。

安全策略:
- 直接使用 bcrypt 库 (rounds=12)
- 不存储明文密码
- 提供安全的密码验证接口
"""

import bcrypt

# ==============================================================================
# 密码哈希配置
# ==============================================================================

# bcrypt 工作因子，控制计算成本
# 每增加 1，计算时间翻倍。12 是当前推荐值（约 300ms）
ROUNDS = 12

# ==============================================================================
# 密码哈希与验证
# ==============================================================================

def hash_password(password: str) -> str:
    """
    对明文密码进行哈希处理

    Args:
        password: 用户输入的明文密码

    Returns:
        bcrypt 哈希后的密码字符串

    示例:
        >>> hashed = hash_password("user123")
        >>> print(hashed)
        $2b$12$...
    """
    salt = bcrypt.gensalt(rounds=ROUNDS)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码与哈希密码是否匹配

    Args:
        plain_password: 用户输入的明文密码
        hashed_password: 存储在数据库中的哈希密码

    Returns:
        密码是否匹配

    示例:
        >>> hashed = hash_password("user123")
        >>> verify_password("user123", hashed)
        True
        >>> verify_password("wrong", hashed)
        False
    """
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )
