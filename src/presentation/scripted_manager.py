"""
T0 剧本强制层 - Scripted Presentation Manager

职责：允许外部剧本（剧情脚本、特殊事件）注入高优先级演出模板，
      完全绕过四层架构的正常竞标流程。

使用场景：
- 剧情关键战斗（如 BOSS 登场、角色觉醒）
- 特殊演出需求（如合体技、剧情杀）
- 测试/调试时的强制指定

优先级：T0_SCRIPTED > T0_LETHAL > T1_HIGHLIGHT > T2_TACTICAL > T2_5_DECAY > T3_FALLBACK

在机战/Gundam语境下：
- 阿姆罗与夏亚的最终对决
- 主角机首次启动/觉醒
- 特定角色的专属处决动画
"""

from typing import Dict, List, Optional
from .models import PresentationAttackEvent, RawAttackEvent
from .template import PresentationTemplate


class ScriptedPresentationManager:
    """
    T0 剧本强制管理器。

    允许外部系统（剧情脚本、任务系统、测试框架）在特定战斗时刻
    强制指定演出模板，完全绕过正常的 L1-L4 四层架构处理流程。

    这是演出系统的"后门"，用于处理那些不能通过常规模板匹配
    表达的特殊剧情演出。

    Attributes:
        _forced_templates: 强制模板映射表
            key: (round_number, attacker_id, defender_id) 元组
            value: PresentationTemplate 实例
    """

    def __init__(self):
        self._forced_templates: Dict[tuple, PresentationTemplate] = {}

    def inject_template(
        self,
        round_number: int,
        attacker_id: str,
        defender_id: str,
        template: PresentationTemplate
    ) -> None:
        """为特定战斗时刻注入强制演出模板。

        Args:
            round_number: 回合编号
            attacker_id: 攻击者实例 ID
            defender_id: 防御者实例 ID
            template: 要强制使用的演出模板（PresentationTemplate 实例）

        Example:
            >>> manager = ScriptedPresentationManager()
            >>> special_template = PresentationTemplate(...)
            >>> manager.inject_template(5, "amuro_01", "char_01", special_template)
            # 第5回合阿姆罗vs夏亚的战斗将使用 special_template
        """
        key = (round_number, attacker_id, defender_id)
        self._forced_templates[key] = template

    def get_forced_template(
        self,
        round_number: int,
        attacker_id: str,
        defender_id: str
    ) -> Optional[PresentationTemplate]:
        """查询指定战斗时刻是否有强制模板。

        Args:
            round_number: 回合编号
            attacker_id: 攻击者实例 ID
            defender_id: 防御者实例 ID

        Returns:
            PresentationTemplate: 如果存在强制模板则返回，否则返回 None
        """
        return self._forced_templates.get((round_number, attacker_id, defender_id))

    def clear(self) -> None:
        """清空所有强制模板。

        通常在战斗结束后调用，避免影响后续战斗。
        """
        self._forced_templates.clear()
