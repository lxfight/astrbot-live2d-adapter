"""Live2D 消息事件 - 处理消息发送到 Live2D 客户端"""

from collections.abc import AsyncGenerator
from typing import Any

try:
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent, MessageChain
    from astrbot.api.message_components import BaseMessageComponent, Plain
except ImportError as e:
    raise ImportError(
        f"Failed to import AstrBot runtime modules; this adapter must run inside AstrBot: {e}"
    ) from e

from ..converters.output_converter import OutputMessageConverter
from ..core.protocol import BasePacket
from ..core.protocol import Protocol as ProtocolClass


class Live2DMessageEvent(AstrMessageEvent):
    """Live2D 消息事件 - 继承自 AstrMessageEvent"""

    def __init__(
        self,
        message_str: str,
        message_obj: Any,
        platform_meta: Any,
        session_id: str,
        websocket_server: Any,
        client_id: str,
        config: dict,
        resource_manager: Any | None = None,
    ):
        """
        初始化 Live2D 消息事件

        Args:
            message_str: 纯文本消息
            message_obj: AstrBotMessage 对象
            platform_meta: 平台元数据
            session_id: 会话 ID
            websocket_server: WebSocket 服务器实例
            client_id: 客户端 ID
            config: 配置字典
        """
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.websocket_server = websocket_server
        self.client_id = client_id
        self.config = config
        self.resource_manager = resource_manager

        # 初始化消息转换器
        self.output_converter = OutputMessageConverter(
            enable_tts=config.get("enable_tts", True),
            tts_mode=config.get("tts_mode", "remote"),
            resource_manager=self.resource_manager,
        )

    def _empty_chain(self) -> MessageChain:
        return MessageChain()

    async def send(self, message: MessageChain | None) -> None:
        """
        发送消息到 Live2D 客户端

        Args:
            message: 消息链
        """
        if not message or not message.chain:
            logger.warning("[Live2D] 消息链为空，跳过发送")
            await super().send(self._empty_chain())
            return

        try:
            # 检查是否有 TTS URL（从 extra 中获取，如果 AstrBot TTS 插件生成了）
            tts_url = self.get_extra("tts_url")

            # 转换 MessageChain 为表演序列
            sequence = self.output_converter.convert(message, tts_url=tts_url)

            if not sequence:
                logger.warning("[Live2D] 转换后的表演序列为空")
                await super().send(self._empty_chain())
                return

            # 创建 perform.show 数据包
            packet = ProtocolClass.create_perform_show(
                sequence=sequence,
                interrupt=True,  # 默认中断当前表演
            )

            # 发送到客户端
            await self._send_to_client(packet)

            logger.info(
                f"[Live2D] 已发送表演序列到客户端 {self.client_id}，包含 {len(sequence)} 个元素"
            )

        except Exception as e:
            logger.error(f"[Live2D] 发送消息失败: {e}", exc_info=True)

        # 调用父类方法（用于统计等）
        await super().send(self._empty_chain())

    async def send_streaming(
        self, generator: AsyncGenerator[MessageChain, None], use_fallback: bool = False
    ) -> None:
        """
        发送流式消息到 Live2D 客户端

        Args:
            generator: 消息链生成器
            use_fallback: Whether to force fallback (send after buffering all chunks).
        """
        enable_streaming = self.config.get("enable_streaming", True)

        if use_fallback or not enable_streaming:
            full_components: list[BaseMessageComponent] = []
            async for chain in generator:
                if chain and chain.chain:
                    full_components.extend(chain.chain)
            if full_components:
                await self.send(MessageChain(chain=full_components))
            else:
                await self.send(self._empty_chain())
            await super().send_streaming(generator, use_fallback)
            return

        # 流式输出：逐块发送
        try:
            buffer = ""

            async for chain in generator:
                if not chain or not chain.chain:
                    continue

                for comp in chain.chain:
                    if isinstance(comp, Plain):
                        text = comp.text
                        buffer += text

                        # 当缓冲区累积到一定长度或遇到句子结束符时发送
                        if len(buffer) >= 10 or any(
                            p in buffer for p in ["。", "！", "？", "\n"]
                        ):
                            sequence = self.output_converter.convert_streaming(buffer)
                            if sequence:
                                packet = ProtocolClass.create_perform_show(
                                    sequence=sequence,
                                    interrupt=False,  # 流式输出不中断
                                )
                                await self._send_to_client(packet)
                                logger.debug(f"[Live2D] 流式发送: {buffer[:50]}...")
                            buffer = ""

            # 发送剩余缓冲区内容
            if buffer:
                sequence = self.output_converter.convert_streaming(buffer)
                if sequence:
                    packet = ProtocolClass.create_perform_show(
                        sequence=sequence, interrupt=False
                    )
                    await self._send_to_client(packet)

            logger.info("[Live2D] 流式消息发送完成")

        except Exception as e:
            logger.error(f"[Live2D] 流式发送失败: {e}", exc_info=True)

        # 调用父类方法
        await super().send_streaming(generator, use_fallback)

    async def _send_to_client(self, packet: BasePacket) -> None:
        """
        通过 WebSocket 发送数据包到客户端

        Args:
            packet: 数据包
        """
        if not self.websocket_server:
            logger.error("[Live2D] WebSocket 服务器未初始化")
            return

        try:
            if getattr(self.websocket_server, "send_to", None):
                await self.websocket_server.send_to(self.client_id, packet)
            else:
                # Fallback to broadcast for older server versions.
                await self.websocket_server.broadcast(packet)
        except Exception as e:
            logger.error(f"[Live2D] 发送数据包到客户端失败: {e}", exc_info=True)


# 兼容性导出
__all__ = ["Live2DMessageEvent"]
