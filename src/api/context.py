"""
API 内容上下文

用于存放全局共享的对象（如 DataLoader），避免循环引用。
"""

from src.loader import DataLoader

_loader: DataLoader | None = None

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
