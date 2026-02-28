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
    Registry for managing and retrieving Presentation Templates.
    Loads from YAML/JSON files.

    v5.0 架构：
    - 核心数据：ActionBone + ReactionBone（L2 DualBidder 使用）
    - T0 脚本：PresentationTemplate（仅用于 scripted_manager 的强制模板）
    """
    def __init__(self, config_path: Optional[str] = None):
        # v5.0 核心：ActionBone 和 ReactionBone 库
        self._action_bones: List[ActionBone] = []
        self._reaction_bones: List[ReactionBone] = []

        # T0 脚本模板（仅用于特殊剧情事件）
        self._scripted_templates: Dict[str, PresentationTemplate] = {}

        # 初始化默认的 T3 Fallback（硬编码保底）
        self._initialize_defaults()

        # 从配置加载
        if config_path:
            self.load_from_config(config_path)

    @property
    def action_bones(self) -> List[ActionBone]:
        """ActionBone 库（v5.0 L2 DualBidder 使用）"""
        return self._action_bones

    @property
    def reaction_bones(self) -> List[ReactionBone]:
        """ReactionBone 库（v5.0 L2 DualBidder 使用）"""
        return self._reaction_bones

    @property
    def scripted_templates(self) -> Dict[str, PresentationTemplate]:
        """T0 脚本模板库（仅用于 scripted_manager）"""
        return self._scripted_templates

    def load_from_config(self, config_path: str):
        """Loads and registers templates from a configuration file."""
        # 加载 action_bones 和 reaction_bones
        action_bones, reaction_bones = TemplateLoader.load_from_file(config_path)

        # 存储新格式 action_bones / reaction_bones
        self._action_bones.extend(action_bones)
        self._reaction_bones.extend(reaction_bones)

    def _register_scripted_template(self, template: PresentationTemplate):
        """注册 T0 脚本模板（仅用于特殊剧情事件）"""
        self._scripted_templates[template.id] = template

    def get_scripted_template(self, template_id: str) -> Optional[PresentationTemplate]:
        """获取 T0 脚本模板"""
        return self._scripted_templates.get(template_id)

    def _initialize_defaults(self):
        """
        Initialize minimal hardcoded default templates (T3 Fallback)
        to ensure system works even if config fails.
        """
        # T3: Generic Fallback（硬编码保底，不走 YAML 配置）
        # 注意：这是系统最后的兜底，确保即使没有配置也能工作
        pass  # 默认值在 assembler.py 中硬编码处理
