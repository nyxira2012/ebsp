"""
渲染器层 - 将演出事件转换为可输出格式

职责：
- TextRenderer: 生成人类可读的终端文本（带颜色）
- JSONRenderer: 生成前端可用的 JSON 数据

在演出系统架构中的位置：
这是 L4 AV Dispatcher 的下游，负责最终输出格式的转换。
不涉及业务逻辑，只负责序列化/格式化。

颜色编码：
- ACTION (黄色): 攻击方动作
- REACTION (蓝色): 防御方反应
- T1 (洋红): 高亮/特殊事件
- DAMAGE (红色): 伤害数值
"""

from typing import List, Optional
import json
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


class JSONRenderer:
    """
    JSON 渲染器 - 将演出事件渲染为前端可用的 JSON 格式。

    用于前后端分离架构中，将演出数据序列化为前端可解析的格式。
    支持完整的战斗时间线导出。
    """

    @staticmethod
    def render_attack(events: List[PresentationAttackEvent]) -> str:
        """将单次攻击事件序列渲染为 JSON 字符串。

        Args:
            events: 演出事件列表

        Returns:
            JSON 格式的字符串，包含事件类型、文本、动画ID、特效、音效等信息
        """
        data = []
        for e in events:
            data.append({
                "type": e.event_type,
                "text": e.text,
                "anim_id": e.anim_id,
                "vfx": e.vfx_ids,
                "sfx": e.sfx_ids,
                "damage": e.damage_display,
                "tier": e.tier.value
            })
        return json.dumps(data, indent=2, ensure_ascii=False)

    @staticmethod
    def render_timeline(timeline: List[PresentationRoundEvent]) -> dict:
        """将完整战斗时间线渲染为可 JSON 序列化的字典。

        Args:
            timeline: 回合事件列表，代表整场战斗的演出序列

        Returns:
            包含完整战斗数据的可序列化字典，结构如下：
            {
                "rounds": [
                    {
                        "round_number": int,
                        "context_events": [...],
                        "attack_sequences": [...],
                        "summary_events": [...]
                    }
                ]
            }
        """
        rounds = []
        for round_event in timeline:
            round_data = {
                "round_number": round_event.round_number,
                "context_events": [
                    {
                        "type": e.event_type,
                        "text": e.text,
                        "anim_id": e.anim_id,
                        "vfx": e.vfx_ids,
                        "sfx": e.sfx_ids,
                        "tier": e.tier.value
                    } for e in round_event.context_events
                ],
                "attack_sequences": [
                    {
                        "attacker_id": seq.attacker_id,
                        "defender_id": seq.defender_id,
                        "events": [
                            {
                                "type": e.event_type,
                                "text": e.text,
                                "anim_id": e.anim_id,
                                "vfx": e.vfx_ids,
                                "sfx": e.sfx_ids,
                                "damage": e.damage_display,
                                "tier": e.tier.value
                            } for e in seq.events
                        ]
                    } for seq in round_event.attack_sequences
                ],
                "summary_events": [
                    {
                        "type": e.event_type,
                        "text": e.text,
                        "anim_id": e.anim_id,
                        "vfx": e.vfx_ids,
                        "sfx": e.sfx_ids,
                        "tier": e.tier.value
                    } for e in round_event.summary_events
                ]
            }
            rounds.append(round_data)
        return {"rounds": rounds}
