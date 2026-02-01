"""AstrBot Live2D Adapter - AstrBot 插件入口

这是一个精简的平台适配器插件，仅用于注册 Live2D 平台适配器。
"""

# 平台适配器会自动通过 @register_platform_adapter 装饰器注册
# 无需在这里做任何操作，只需导入即可
from .adapters.platform_adapter import Live2DPlatformAdapter  # noqa: F401

__all__ = ["Live2DPlatformAdapter"]
