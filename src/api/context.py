"""
API 内容上下文

用于存放全局共享的对象（如 DataLoader、TemplateRegistry），避免循环引用。
"""

from src.loader import DataLoader
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.presentation import TemplateRegistry

_loader: DataLoader | None = None
_presentation_registry: "TemplateRegistry | None" = None


def get_loader() -> DataLoader:
    """获取全局数据加载器"""
    global _loader
    if _loader is None:
        raise RuntimeError("数据加载器未初始化")
    return _loader


def set_loader(loader: DataLoader):
    """设置全局数据加载器"""
    global _loader
    _loader = loader


def get_presentation_registry() -> "TemplateRegistry":
    """获取全局演出模板注册表"""
    global _presentation_registry
    if _presentation_registry is None:
        raise RuntimeError("演出模板注册表未初始化，请先调用 initialize_presentation_registry()")
    return _presentation_registry


def initialize_presentation_registry(template_path: str) -> None:
    """初始化全局演出模板注册表"""
    global _presentation_registry
    from src.presentation import TemplateRegistry

    _presentation_registry = TemplateRegistry(template_path)
    action_count = len(_presentation_registry.action_bones)
    reaction_count = len(_presentation_registry.reaction_bones)
    print(f"✅ 演出模板加载完成: {action_count} ActionBone, {reaction_count} ReactionBone")
