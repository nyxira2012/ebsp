"""
模板注册中心 - Template Registry

职责：管理和检索演出模板资源。
      从 YAML/JSON 配置文件加载 ActionBone 和 ReactionBone。

在 CPS v5.0 四层架构中的位置：
- 作为 L2 DualBidder 的数据源，提供竞标所需的 ActionBone 和 ReactionBone
- 模板数据是只读的（运行时），通过 load_from_config 初始化

数据流向：
    YAML 配置文件
         ↓
    TemplateLoader (loader.py)
         ↓
    TemplateRegistry (本模块)
         ↓
    DualBidder (bidder.py) - L2 层竞标
"""

from typing import List, Dict, Optional
from .template import (
    ActionBone, ReactionBone,
    # PresentationTemplate 仅保留用于 T0 脚本模板
    PresentationTemplate, TemplateConditions, TemplateContent, TemplateVisuals
)
from .constants import TemplateTier
from .loader import TemplateLoader


class TemplateRegistry:
    """
    模板注册中心。

    负责从配置文件加载并存储演出系统所需的原子化骨架模板：
    - ActionBone: 攻击方动作骨架（驱动 L2 Action 竞标）
    - ReactionBone: 防御方反应骨架（驱动 L2 Reaction 竞标）

    v5.0 架构：
    - 核心数据：ActionBone + ReactionBone（供 L2 DualBidder 使用）
    - 向后兼容：PresentationTemplate（仅用于 T0 scripted_manager 的强制模板）

    Attributes:
        _action_bones: ActionBone 库，用于攻击方动作竞标
        _reaction_bones: ReactionBone 库，用于防御方反应竞标
    """

    def __init__(self, config_path: Optional[str] = None):
        """初始化注册中心。

        Args:
            config_path: 可选的配置文件路径，如果提供则自动加载
        """
        self._action_bones: List[ActionBone] = []
        self._reaction_bones: List[ReactionBone] = []

        if config_path:
            self.load_from_config(config_path)

    @property
    def action_bones(self) -> List[ActionBone]:
        """ActionBone 库（v5.0 L2 DualBidder 使用）。"""
        return self._action_bones

    @property
    def reaction_bones(self) -> List[ReactionBone]:
        """ReactionBone 库（v5.0 L2 DualBidder 使用）。"""
        return self._reaction_bones

    def load_from_config(self, config_path: str) -> None:
        """从配置文件加载并注册模板。

        Args:
            config_path: YAML 配置文件路径

        Raises:
            FileNotFoundError: 当配置文件不存在时
            yaml.YAMLError: 当 YAML 解析失败时
        """
        action_bones, reaction_bones = TemplateLoader.load_from_file(config_path)

        self._action_bones.extend(action_bones)
        self._reaction_bones.extend(reaction_bones)
