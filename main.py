"""AstrBot Live2D Adapter - AstrBot 插件入口"""

import logging

from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, register

from .adapters.platform_adapter import Live2DPlatformAdapter
from .commands.live2d_commands import Live2DCommands

logger = logging.getLogger(__name__)


@register(
    "live2d_adapter",
    "AstrBot Team",
    "Live2D 桌面应用平台适配器，支持 Live2D-Bridge Protocol v1.0",
    "1.0.0",
)
class Live2DAdapterPlugin(Star):
    """Live2D 适配器插件

    功能：
    - 将 Live2D 桌面应用接入 AstrBot
    - 支持 WebSocket 通讯（L2D-Bridge Protocol v1.0）
    - 支持文字、图片、语音等多模态消息
    - 支持 TTS 语音、Live2D 动作和表情控制
    """

    def __init__(self, context: Context):
        """初始化插件

        Args:
            context: AstrBot 上下文
        """
        super().__init__(context)
        self.context = context

        # 指令处理器（延迟初始化）
        self.commands_handler: Live2DCommands | None = None

        logger.info("[Live2D] 插件已加载")
        logger.info("[Live2D] 平台适配器将在 AstrBot 启动平台时自动启动")
        logger.info(
            "[Live2D] 可用指令: /live2d status, /live2d reload, /live2d say <text>"
        )

    @filter.command_group("live2d")
    def live2d(self):
        """Live2D 适配器管理"""

    @live2d.command("status")
    async def live2d_status(self, event: AstrMessageEvent):
        """查看连接状态"""
        try:
            if not self.commands_handler:
                adapter = self._get_live2d_adapter()
                if not adapter:
                    await event.send(MessageChain([Plain("[Live2D] 适配器未启动")]))
                    return
                self.commands_handler = Live2DCommands(adapter)

            result = await self.commands_handler.handle_command("status", [])
            if result:
                await event.send(result)
        except Exception as e:
            logger.error(f"[Live2D] status 指令执行失败: {e}", exc_info=True)
            await event.send(MessageChain([Plain(f"[Live2D] 执行失败: {e}")]))

    @live2d.command("reload")
    async def live2d_reload(self, event: AstrMessageEvent):
        """重载配置"""
        try:
            if not self.commands_handler:
                adapter = self._get_live2d_adapter()
                if not adapter:
                    await event.send(MessageChain([Plain("[Live2D] 适配器未启动")]))
                    return
                self.commands_handler = Live2DCommands(adapter)

            result = await self.commands_handler.handle_command("reload", [])
            if result:
                await event.send(result)
        except Exception as e:
            logger.error(f"[Live2D] reload 指令执行失败: {e}", exc_info=True)
            await event.send(MessageChain([Plain(f"[Live2D] 执行失败: {e}")]))

    @live2d.command("say")
    async def live2d_say(self, event: AstrMessageEvent, text: str = ""):
        """发送文本到 Live2D"""
        try:
            if not text:
                await event.send(
                    MessageChain([Plain("[Live2D] 用法: /live2d say <文本内容>")])
                )
                return

            if not self.commands_handler:
                adapter = self._get_live2d_adapter()
                if not adapter:
                    await event.send(MessageChain([Plain("[Live2D] 适配器未启动")]))
                    return
                self.commands_handler = Live2DCommands(adapter)

            result = await self.commands_handler.handle_command("say", [text])
            if result:
                await event.send(result)
        except Exception as e:
            logger.error(f"[Live2D] say 指令执行失败: {e}", exc_info=True)
            await event.send(MessageChain([Plain(f"[Live2D] 执行失败: {e}")]))

    def _get_live2d_adapter(self) -> Live2DPlatformAdapter | None:
        """获取 Live2D 平台适配器实例

        Returns:
            Live2DPlatformAdapter 实例，如果未找到则返回 None
        """
        try:
            # 从 AstrBot 的平台管理器中获取适配器实例
            # 注意：这里需要根据实际 AstrBot 架构调整
            platforms = getattr(self.context, "platforms", None)
            if platforms:
                for platform in platforms:
                    if isinstance(platform, Live2DPlatformAdapter):
                        return platform

            # 备用方案：通过全局变量或单例模式
            logger.warning("[Live2D] 无法从 context 获取适配器实例")
            return None

        except Exception as e:
            logger.error(f"[Live2D] 获取适配器实例失败: {e}", exc_info=True)
            return None
