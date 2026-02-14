"""
渲染器 - 将演出事件渲染为文本或JSON格式
提供文本渲染（控制台输出）和JSON渲染（前端API）两种方式
"""

import json
from typing import List, Optional
from datetime import datetime
from .models import PresentationAttackEvent, PresentationRoundEvent


class TextRenderer:
    """文本渲染器 - 生成控制台友好的文本输出

    职责：
    1. 将 PresentationAttackEvent 渲染为格式化的文本
    2. 支持标签高亮显示（使用ANSI颜色代码）
    3. 生成四段式战斗描述（环境、先攻、反击、总结）

    使用方式：
        renderer = TextRenderer()
        text = renderer.render_attack(event)
        print(text)
    """

    # ANSI颜色代码
    COLOR_RESET = "\033[0m"
    COLOR_RED = "\033[91m"
    COLOR_GREEN = "\033[92m"
    COLOR_YELLOW = "\033[93m"
    COLOR_BLUE = "\033[94m"
    COLOR_MAGENTA = "\033[95m"
    COLOR_CYAN = "\033[96m"

    def render_attack(self, event: PresentationAttackEvent, use_color: bool = True) -> str:
        """渲染单个攻击事件为文本

        Args:
            event: 演出攻击事件
            use_color: 是否使用ANSI颜色代码（默认True）

        Returns:
            格式化的文本字符串
        """
        # 构建段落标识
        section_prefix = self._get_section_prefix(event)

        # 高亮显示标签
        tag_str = ""
        if event.display_tags:
            tag_str = " " + self._format_tags(event.display_tags, use_color)

        # 组装最终文本
        text = f"{section_prefix} {event.text}{tag_str}"

        return text

    def render_round(self, round_event: PresentationRoundEvent, use_color: bool = True) -> str:
        """渲染完整的回合事件为文本

        生成标准的四段式文本：
        - L1: 环境/先手
        - L2: 先手攻击
        - L3: 后手反击
        - L4: 回合总结

        Args:
            round_event: 演出回合事件
            use_color: 是否使用ANSI颜色代码

        Returns:
            完整回合的格式化文本
        """
        lines = []
        lines.append("=" * 80)
        lines.append(f"ROUND {round_event.round_number}")
        lines.append("=" * 80)
        lines.append("")

        # 渲染各个段落
        events = round_event.get_all_events()
        for event in events:
            if event:
                lines.append(self.render_attack(event, use_color))

        return "\n".join(lines)

    def _get_section_prefix(self, event: PresentationAttackEvent) -> str:
        """获取段落前缀标识

        Args:
            event: 演出攻击事件

        Returns:
            段落前缀字符串
        """
        section_type = event.section_type

        if section_type == "CONTEXT":
            return "- **[环境]**"
        elif section_type == "ACTION_FIRST":
            return "- **[先手]**"
        elif section_type == "ACTION_SECOND":
            return "- **[反击]**"
        elif section_type == "SUMMARY":
            return "- **[总结]**"
        else:
            return "-"

    def _format_tags(self, tags: List[str], use_color: bool) -> str:
        """格式化标签列表

        Args:
            tags: 标签字符串列表
            use_color: 是否使用颜色

        Returns:
            格式化后的标签字符串
        """
        if not tags:
            return ""

        formatted = []
        for tag in tags:
            if use_color:
                # 根据标签类型选择颜色
                color = self._get_tag_color(tag)
                formatted.append(f"{color}[{tag}]{self.COLOR_RESET}")
            else:
                formatted.append(f"[{tag}]")

        return " ".join(formatted)

    def _get_tag_color(self, tag: str) -> str:
        """根据标签类型返回对应的颜色代码

        Args:
            tag: 标签字符串

        Returns:
            ANSI颜色代码
        """
        if tag in ["暴击", "CRIT"]:
            return self.COLOR_RED
        elif tag in ["命中", "HIT"]:
            return self.COLOR_YELLOW
        elif tag in ["躲闪", "DODGE"]:
            return self.COLOR_CYAN
        elif tag in ["招架", "PARRY"]:
            return self.COLOR_BLUE
        elif tag in ["格挡", "BLOCK"]:
            return self.COLOR_MAGENTA
        else:
            return self.COLOR_GREEN


class JSONRenderer:
    """JSON渲染器 - 生成前端可用的JSON格式数据

    职责：
    1. 将 PresentationAttackEvent 转换为字典格式
    2. 将 PresentationRoundEvent 转换为完整的JSON对象
    3. 提供序列化方法，便于前端WebSocket传输

    使用方式：
        renderer = JSONRenderer()
        json_str = renderer.render_round(round_event)
        # 通过WebSocket发送给前端
    """

    def render_attack(self, event: PresentationAttackEvent) -> dict:
        """渲染单个攻击事件为字典格式

        Args:
            event: 演出攻击事件

        Returns:
            字典格式的演出数据
        """
        return {
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "round_number": event.round_number,
            "is_first_attack": event.is_first_attack,

            # 文本演出
            "text": event.text,
            "display_tags": event.display_tags,
            "section_type": event.section_type,

            # 视觉演出
            "anim_id": event.anim_id,
            "camera_cam": event.camera_cam,
            "vfx_ids": event.vfx_ids,
            "sfx_ids": event.sfx_ids,

            # 数据快照
            "damage_display": event.damage_display,
            "hit_location": event.hit_location,
            "attacker_name": event.attacker_name,
            "defender_name": event.defender_name,
            "weapon_name": event.weapon_name,
            "attack_result": event.attack_result,
            "range_tag": event.range_tag
        }

    def render_round(self, round_event: PresentationRoundEvent) -> dict:
        """渲染完整回合事件为JSON字典

        Args:
            round_event: 演出回合事件

        Returns:
            字典格式的完整回合数据
        """
        events = []

        # 渲染所有子事件
        if round_event.context_event:
            events.append(self.render_attack(round_event.context_event))
        if round_event.first_attack_event:
            events.append(self.render_attack(round_event.first_attack_event))
        if round_event.second_attack_event:
            events.append(self.render_attack(round_event.second_attack_event))
        if round_event.summary_event:
            events.append(self.render_attack(round_event.summary_event))

        return {
            "round_number": round_event.round_number,
            "timestamp": datetime.now().timestamp(),
            "events": events
        }

    def render_round_json(self, round_event: PresentationRoundEvent, indent: Optional[int] = None) -> str:
        """渲染完整回合事件为JSON字符串

        Args:
            round_event: 演出回合事件
            indent: JSON缩进空格数（None表示压缩输出）

        Returns:
            JSON格式字符串
        """
        data = self.render_round(round_event)
        return json.dumps(data, ensure_ascii=False, indent=indent)
