"""AstrBot Live2D Adapter - AstrBot 插件入口"""

from astrbot.api.star import Context, Star

from .adapters.platform_adapter import Live2DPlatformAdapter  # noqa: F401


class Main(Star):
    """Live2D 平台适配器插件"""

    def __init__(self, context: Context):
        super().__init__(context)


__all__ = ["Main", "Live2DPlatformAdapter"]
