"""
渲染器层 - 将演出事件转换为可输出格式

职责：
- TextRenderer: 生成人类可读的终端文本（带颜色）

在演出系统架构中的位置：
这是 L4 AV Dispatcher 的下游，负责最终输出格式的转换。
不涉及业务逻辑，只负责序列化/格式化。

颜色编码：
- ACTION (黄色): 攻击方动作
- REACTION (蓝色): 防御方反应
- T1 (洋红): 高亮/特殊事件
- DAMAGE (红色): 伤害数值

历史注记：曾有 JSONRenderer 负责前端 JSON 输出，simulate 切换到
TimelineDocument 契约（Doc 15 红线 1：契约唯一拼装点）后零消费方，已删除。
"""

from typing import List
from .models import PresentationAttackEvent, PresentationRoundEvent, TemplateTier


class TextRenderer:
    """
    文本渲染器 - 将演出事件渲染为人类可读的终端文本。

    支持 ANSI 颜色代码，用于在控制台输出带颜色的战斗演出。
    是调试和开发阶段的主要可视化工具。

    Attributes:
        COLORS: ANSI 颜色代码映射表
    """

    # ANSI Color Codes
    COLORS = {
        "ACTION": "\033[93m",      # Yellow
        "REACTION": "\033[94m",    # Blue
        "T1": "\033[95m",          # Magenta (High-light)
        "DAMAGE": "\033[91m",      # Red
        "RESET": "\033[0m"
    }

    @staticmethod
    def render_attack(events: List[PresentationAttackEvent], use_color: bool = True) -> str:
        """渲染单次攻击的事件序列（通常为 Action + Reaction）。

        Args:
            events: 演出事件列表（通常是攻击方和防御方的一对事件）
            use_color: 是否使用 ANSI 颜色代码，默认为 True

        Returns:
            格式化的多行文本字符串

        Example:
            >>> events = [action_event, reaction_event]
            >>> print(TextRenderer.render_attack(events))
            ACTION: [T2_TACTICAL] 阿姆罗使用光束步枪展开了攻击！
            REACTION: 扎古的腰部被击中。（命中！-1200，中伤）
        """
        output = []
        for e in events:
            color = TextRenderer.COLORS["ACTION"] if e.event_type == "ACTION" else TextRenderer.COLORS["REACTION"]
            tier_prefix = f"[{e.tier.value}] " if e.tier != TemplateTier.T3_FALLBACK else ""

            reset = TextRenderer.COLORS["RESET"]

            line = f"{color if use_color else ''}{e.event_type}{reset if use_color else ''}: {tier_prefix}{e.text}"

            # Special damage display for reactions
            if e.event_type == "REACTION" and e.damage_display > 0:
                dmg_color = TextRenderer.COLORS["DAMAGE"]
                line += f" ({dmg_color if use_color else ''}Damage: {e.damage_display}{reset if use_color else ''})"

            output.append(line)
        return "\n".join(output)

    @staticmethod
    def render_round(round_event: PresentationRoundEvent, use_color: bool = True) -> str:
        """渲染完整回合的所有事件。

        Args:
            round_event: 回合事件对象，包含上下文、攻击序列和总结
            use_color: 是否使用 ANSI 颜色代码，默认为 True

        Returns:
            格式化的多行文本字符串，包含回合标题、上下文、攻击序列和总结

        Example:
            >>> print(TextRenderer.render_round(round_event))
            === ROUND 5 PRESENTATION ===
            --- Context ---
            ...
        """
        output = []
        output.append(f"=== ROUND {round_event.round_number} PRESENTATION ===")

        if round_event.context_events:
            output.append("--- Context ---")
            for ctx in round_event.context_events:
                output.append(f"{ctx.text}")

        for idx, seq in enumerate(round_event.attack_sequences, 1):
            output.append(f"--- Attack Sequence {idx} ---")
            output.append(TextRenderer.render_attack(seq.events, use_color))

        if round_event.summary_events:
            output.append("--- Summary ---")
            for summary in round_event.summary_events:
                output.append(f"{summary.text}")

        return "\n".join(output)
