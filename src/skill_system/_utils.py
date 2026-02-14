"""共享工具函数"""


def get_target(target_type: str, context, owner):
    """获取目标机体。

    支持 "self" (效果持有人) 和 "enemy" (持有人的对手)。

    Args:
        target_type: 目标类型 ("self" 或 "enemy")
        context: 战斗上下文快照
        owner: 效果持有人

    Returns:
        目标机体对象，若无法识别则返回 None
    """
    if target_type == "self":
        return owner

    if target_type == "enemy":
        attacker = context.get_attacker()
        defender = context.get_defender()
        if owner == attacker:
            return defender
        if owner == defender:
            return attacker

    return None
