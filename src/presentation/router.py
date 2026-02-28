"""
L1 绝对律令层 - 结局前置路由 (Outcome-First Routing)

职责：根据战斗结局，在第一毫秒就锁定演出频道，杜绝逻辑穿帮。
核心权重：结局（Result） > 意图（Intent） > 技能（Skill）
"""

from .models import RawAttackEvent
from .constants import Channel


class OutcomeRouter:
    """
    结局前置路由器。

    路由优先级（严格有序）：
    1. is_lethal → FATAL (致死判定，最高优先级)
    2. is_counter or is_support → SPECIAL (特殊频道)
    3. attack_result in (MISS, DODGE, PARRY) → EVADE (闪避/未命中)
    4. 其余 → IMPACT (命中/格挡/暴击)
    """

    # 路由优先级表（数字越小优先级越高）
    _ROUTING_RULES = [
        # 一类优先级：致死判定
        (lambda e: e.is_lethal, Channel.FATAL),
        # 二类优先级：特殊频道
        (lambda e: e.is_counter or e.is_support, Channel.SPECIAL),
        # 三类优先级：闪避/未命中
        (lambda e: e.attack_result in ("MISS", "DODGE", "PARRY"), Channel.EVADE),
    ]

    @classmethod
    def route(cls, event: RawAttackEvent) -> Channel:
        """
        根据 RawAttackEvent 路由到对应的演出频道。

        Args:
            event: 原始攻击事件

        Returns:
            Channel: 演出频道（FATAL/EVADE/IMPACT/SPECIAL）

        使用示例：
            channel = OutcomeRouter.route(raw_event)
            # channel 作为后续所有层的"门卫令牌"
        """
        for condition, channel in cls._ROUTING_RULES:
            if condition(event):
                return channel

        # 默认频道：命中/格挡/暴击等直接打击
        return Channel.IMPACT

    @classmethod
    def get_channel_description(cls, channel: Channel) -> str:
        """获取频道的描述信息（用于调试）"""
        descriptions = {
            Channel.FATAL: "致死演出 - 机体被摧毁",
            Channel.EVADE: "闪避演出 - 未命中/闪避/招架",
            Channel.IMPACT: "打击演出 - 命中/格挡/暴击",
            Channel.SPECIAL: "特殊演出 - 支援/反击",
        }
        return descriptions.get(channel, "未知频道")
