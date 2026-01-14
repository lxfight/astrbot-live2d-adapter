"""Live2D 消息事件 - 处理消息发送到 Live2D 客户端"""

from collections.abc import AsyncGenerator
from typing import Any

try:
    from astrbot import logger
    from astrbot.api.event import AstrMessageEvent, MessageChain
    from astrbot.api.message_components import Image, Plain
except ImportError:
    # 兼容性处理（用于独立测试）
    AstrMessageEvent = object
    MessageChain = Plain = Image = None
    import logging

    logger = logging.getLogger(__name__)

from ..converters.output_converter import OutputMessageConverter
from ..core.protocol import BasePacket, Protocol


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
            enable_auto_emotion=config.get("enable_auto_emotion", True),
            enable_tts=config.get("enable_tts", True),
            tts_mode=config.get("tts_mode", "remote"),
            resource_manager=self.resource_manager,
        )

    async def send(self, message: MessageChain | None) -> None:
        """
        发送消息到 Live2D 客户端

        Args:
            message: 消息链
        """
        if not message or not message.chain:
            logger.warning("[Live2D] 消息链为空，跳过发送")
            await super().send(MessageChain([]))
            return

        try:
            # 检查是否有 TTS URL（从 extra 中获取，如果 AstrBot TTS 插件生成了）
            tts_url = self.get_extra("tts_url")

            # 转换 MessageChain 为表演序列
            sequence = self.output_converter.convert(message, tts_url=tts_url)

            if not sequence:
                logger.warning("[Live2D] 转换后的表演序列为空")
                await super().send(MessageChain([]))
                return

            # 创建 perform.show 数据包
            packet = Protocol.create_perform_show(
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
        await super().send(MessageChain([]))

    async def send_streaming(
        self, generator: AsyncGenerator[MessageChain, None], use_fallback: bool = False
    ) -> None:
        """
        发送流式消息到 Live2D 客户端

        Args:
            generator: 消息链生成器
            use_fallback: 是否使用降级方案（未实现）
        """
        enable_streaming = self.config.get("enable_streaming", True)

        if not enable_streaming:
            # 禁用流式输出，等待所有内容后一次性发送
            full_text = ""
            final_chain = None

            async for chain in generator:
                if chain and chain.chain:
                    for comp in chain.chain:
                        if isinstance(comp, Plain):
                            full_text += comp.text
                    final_chain = chain

            if full_text and final_chain:
                await self.send(MessageChain([Plain(full_text)]))
            return

        # 流式输出：逐块发送
        try:
            buffer = ""
            tts_url = self.get_extra("tts_url")

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
                                packet = Protocol.create_perform_show(
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
                    # 最后一块添加情感动作
                    if self.output_converter.enable_auto_emotion:
                        from converters.emotion_analyzer import EmotionAnalyzer
                        from core.protocol import (
                            create_expression_element,
                            create_motion_element,
                        )

                        expression, motion = EmotionAnalyzer.analyze(buffer)
                        if expression:
                            sequence.append(
                                create_expression_element(expression, fade=300)
                            )
                        if motion:
                            sequence.append(
                                create_motion_element(
                                    group=motion.get("group", "Idle"),
                                    index=motion.get("index", 0),
                                    priority=2,
                                )
                            )

                    packet = Protocol.create_perform_show(
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
            # 调用 WebSocket 服务器的广播方法
            # （由于单一连接约束，广播实际上只会发送给唯一的客户端）
            await self.websocket_server.broadcast(packet)
        except Exception as e:
            logger.error(f"[Live2D] 发送数据包到客户端失败: {e}", exc_info=True)


# 兼容性导出
__all__ = ["Live2DMessageEvent"]
