"""Live2D 平台适配器 - AstrBot 平台适配器实现"""

import asyncio
import logging
from asyncio import Queue

try:
    from astrbot.api.event import MessageChain
    from astrbot.api.message_components import Plain
    from astrbot.api.platform import (
        AstrBotMessage,
        MessageMember,
        MessageType,
        Platform,
        PlatformMetadata,
        register_platform_adapter,
    )
    from astrbot.core.platform.message_session import MessageSesion
except ImportError as e:
    raise ImportError(
        f"无法导入 AstrBot 模块，请确保此适配器作为 AstrBot 插件运行: {e}"
    )

from ..converters.input_converter import InputMessageConverter
from ..converters.output_converter import OutputMessageConverter
from ..core.config import ConfigLike
from ..core.protocol import BasePacket, Protocol
from ..server.resource_manager import ResourceManager
from ..server.resource_server import ResourceServer
from ..server.websocket_server import WebSocketServer
from .message_event import Live2DMessageEvent

logger = logging.getLogger(__name__)


@register_platform_adapter(
    "live2d",
    "Live2D 桌面应用适配器，支持 Live2D-Bridge Protocol v1.0",
    default_config_tmpl={
        "type": "live2d",
        "enable": False,
        "id": "live2d_default",
        "ws_host": "0.0.0.0",
        "ws_port": 9090,
        "ws_path": "/astrbot/live2d",
        "auth_token": "your_secret_token",
        "max_connections": 1,
        "kick_old": True,
        "enable_auto_emotion": True,
        "enable_tts": False,
        "tts_mode": "local",
        "resource_enabled": True,
        "resource_host": "0.0.0.0",
        "resource_port": 9091,
        "resource_path": "/resources",
        "resource_dir": "./data/live2d_resources",
        "resource_base_url": "",
        "resource_token": "",
        "resource_max_inline_bytes": 262144,
    },
    adapter_display_name="Live2D",
    support_streaming_message=True,
)
class Live2DPlatformAdapter(Platform):
    """Live2D 平台适配器"""

    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: Queue
    ):
        """初始化适配器

        Args:
            platform_config: 平台配置（来自用户配置）
            platform_settings: 平台设置
            event_queue: 事件队列
        """
        super().__init__(platform_config, event_queue)

        self.settings = platform_settings
        self.platform_config = platform_config

        # 初始化配置对象（用于兼容现有代码）
        self.config_obj: ConfigLike = self._create_config_from_dict(platform_config)

        # WebSocket 服务器实例
        self.ws_server: WebSocketServer | None = None
        self.resource_server: ResourceServer | None = None

        self.resource_manager = ResourceManager(
            storage_dir=self.config_obj.resource_dir,
            base_url=self.config_obj.resource_base_url,
            resource_path=self.config_obj.resource_path,
            max_inline_bytes=self.config_obj.resource_max_inline_bytes,
            token=self.config_obj.resource_token,
        )

        # 消息转换器
        self.input_converter = InputMessageConverter(resource_manager=self.resource_manager)
        self.output_converter = OutputMessageConverter(
            enable_auto_emotion=platform_config.get("enable_auto_emotion", True),
            enable_tts=platform_config.get("enable_tts", False),
            tts_mode=platform_config.get("tts_mode", "local"),
            resource_manager=self.resource_manager,
            resource_config={
                "max_inline_bytes": self.config_obj.resource_max_inline_bytes,
                "base_url": self.config_obj.resource_base_url,
                "resource_path": self.config_obj.resource_path,
            },
        )

        # 当前连接的客户端ID（单一连接约束）
        self.current_client_id: str | None = None

        logger.info(f"[Live2D] 平台适配器已初始化，ID: {self.config.get('id')}")

    def _create_config_from_dict(self, config_dict: dict) -> ConfigLike:
        """从字典创建 Config 对象（用于兼容现有 WebSocketServer）

        Args:
            config_dict: 配置字典

        Returns:
            Config 对象
        """

        # 创建一个模拟 Config 类的对象
        class ConfigAdapter:
            def __init__(self, data: dict):
                self._data = data

            @property
            def server_host(self) -> str:
                return self._data.get("ws_host", "0.0.0.0")

            @property
            def server_port(self) -> int:
                return self._data.get("ws_port", 9090)

            @property
            def auth_token(self) -> str:
                return self._data.get("auth_token", "")

            @property
            def ws_path(self) -> str:
                return self._data.get("ws_path", "/ws")

            @property
            def max_connections(self) -> int:
                return self._data.get("max_connections", 1)

            @property
            def kick_old(self) -> bool:
                return self._data.get("kick_old", True)

            @property
            def resource_enabled(self) -> bool:
                return self._data.get("resource_enabled", True)

            @property
            def resource_host(self) -> str:
                return self._data.get("resource_host", self.server_host)

            @property
            def resource_port(self) -> int:
                return self._data.get("resource_port", 9091)

            @property
            def resource_path(self) -> str:
                return self._data.get("resource_path", "/resources")

            @property
            def resource_dir(self) -> str:
                return self._data.get("resource_dir", "./data/live2d_resources")

            @property
            def resource_base_url(self) -> str:
                base_url = self._data.get("resource_base_url", "")
                if base_url:
                    return base_url
                return f"http://{self.resource_host}:{self.resource_port}"

            @property
            def resource_token(self) -> str:
                token = self._data.get("resource_token", "")
                if token:
                    return token
                return self.auth_token

            @property
            def resource_max_inline_bytes(self) -> int:
                return int(self._data.get("resource_max_inline_bytes", 262144))

        return ConfigAdapter(config_dict)

    def meta(self) -> PlatformMetadata:
        """返回平台元数据

        Returns:
            PlatformMetadata 对象
        """
        return PlatformMetadata(
            name="live2d",
            description="Live2D 桌面应用适配器，支持 Live2D-Bridge Protocol v1.0",
            id=self.config.get("id", "live2d_default"),
            adapter_display_name="Live2D",
            support_streaming_message=True,
        )

    def _get_client_session(self, client_id: str) -> dict:
        ws_server = self.ws_server
        if not ws_server:
            return {}
        return ws_server.handler.client_states.get(client_id, {}).get(
            "session", {}
        )

    def _resolve_message_type(self, metadata: dict) -> MessageType:
        raw_type = metadata.get("messageType") or metadata.get("type")
        if isinstance(raw_type, MessageType):
            return raw_type
        if isinstance(raw_type, str):
            normalized = raw_type.strip().lower()
            if normalized in {"group", "group_message", "groupmessage"}:
                return MessageType.GROUP_MESSAGE
            if normalized in {"friend", "private", "friend_message", "privatemessage"}:
                return MessageType.FRIEND_MESSAGE
            if normalized in {"other", "system", "other_message"}:
                return MessageType.OTHER_MESSAGE
        if metadata.get("groupId") or metadata.get("group_id") or metadata.get("isGroup"):
            return MessageType.GROUP_MESSAGE
        return MessageType.FRIEND_MESSAGE

    def _resolve_session_info(
        self, client_id: str, metadata: dict, group_id: str | None = None
    ) -> tuple[str, str, str]:
        session_info = self._get_client_session(client_id)
        user_id = metadata.get("userId") or session_info.get("user_id") or client_id
        user_name = metadata.get("userName") or "Live2D User"
        session_id = (
            metadata.get("sessionId")
            or session_info.get("session_id")
            or group_id
            or client_id
        )
        return str(user_id), str(user_name), str(session_id)

    async def convert_message(
        self, packet: BasePacket, client_id: str
    ) -> AstrBotMessage | None:
        """将 Live2D 客户端的 input.message 转换为 AstrBotMessage

        Args:
            packet: 接收到的数据包
            client_id: 客户端 ID

        Returns:
            AstrBotMessage 对象，如果转换失败则返回 None
        """
        if packet.op != Protocol.OP_INPUT_MESSAGE:
            logger.warning(f"[Live2D] 非 input.message 类型数据包: {packet.op}")
            return None

        try:
            payload = packet.payload or {}
            content = payload.get("content", [])
            metadata = payload.get("metadata", {})

            # 使用 InputMessageConverter 转换消息内容
            message_components, message_str = self.input_converter.convert(content)

            if not message_str and not message_components:
                logger.warning("[Live2D] 空消息内容，跳过处理")
                return None

            # 构造 AstrBotMessage
            abm = AstrBotMessage()
            message_type = self._resolve_message_type(metadata)
            group_id = metadata.get("groupId") or metadata.get("group_id")
            abm.type = message_type
            abm.message_str = message_str
            abm.message = message_components
            abm.self_id = self.client_self_id
            sender_id, sender_name, session_id = self._resolve_session_info(
                client_id, metadata, str(group_id) if group_id else None
            )
            abm.sender = MessageMember(user_id=sender_id, nickname=sender_name)
            abm.session_id = session_id
            message_id = metadata.get("messageId") or packet.id
            abm.message_id = str(message_id)
            abm.timestamp = int(packet.ts)
            abm.raw_message = packet.payload
            if message_type == MessageType.GROUP_MESSAGE and group_id:
                abm.group_id = str(group_id)

            logger.info(f"[Live2D] 转换消息: {message_str[:50]}...")
            return abm

        except Exception as e:
            logger.error(f"[Live2D] 转换消息失败: {e}", exc_info=True)
            return None

    def convert_touch(self, packet: BasePacket, client_id: str) -> AstrBotMessage:
        """将 input.touch 转换为 AstrBotMessage"""
        payload = packet.payload or {}
        part = payload.get("part") or payload.get("area") or "Unknown"
        action = payload.get("action") or "tap"
        details = [f"part={part}", f"action={action}"]
        if payload.get("x") is not None:
            details.append(f"x={payload.get('x')}")
        if payload.get("y") is not None:
            details.append(f"y={payload.get('y')}")
        if payload.get("duration") is not None:
            details.append(f"duration={payload.get('duration')}")
        message_str = "[touch] " + " ".join(details)

        abm = AstrBotMessage()
        abm.type = MessageType.OTHER_MESSAGE
        abm.message_str = message_str
        abm.message = [Plain(message_str)] if Plain else []
        abm.self_id = self.client_self_id
        sender_id, sender_name, session_id = self._resolve_session_info(client_id, {})
        abm.sender = MessageMember(user_id=sender_id, nickname=sender_name)
        abm.session_id = session_id
        abm.message_id = packet.id
        abm.timestamp = int(packet.ts)
        abm.raw_message = packet.payload
        return abm

    def convert_shortcut(self, packet: BasePacket, client_id: str) -> AstrBotMessage:
        """将 input.shortcut 转换为 AstrBotMessage"""
        payload = packet.payload or {}
        key = payload.get("key") or ""
        message_str = f"[shortcut] key={key}" if key else "[shortcut]"

        abm = AstrBotMessage()
        abm.type = MessageType.OTHER_MESSAGE
        abm.message_str = message_str
        abm.message = [Plain(message_str)] if Plain else []
        abm.self_id = self.client_self_id
        sender_id, sender_name, session_id = self._resolve_session_info(client_id, {})
        abm.sender = MessageMember(user_id=sender_id, nickname=sender_name)
        abm.session_id = session_id
        abm.message_id = packet.id
        abm.timestamp = int(packet.ts)
        abm.raw_message = packet.payload
        return abm

    async def handle_msg(
        self,
        abm: AstrBotMessage,
        client_id: str,
        extras: dict[str, object] | None = None,
    ):
        """处理转换后的 AstrBotMessage，创建事件并提交到队列

        Args:
            abm: AstrBotMessage 对象
            client_id: 客户端 ID
            extras: 事件附加信息
        """
        try:
            # 创建 Live2DMessageEvent
            message_event = Live2DMessageEvent(
                message_str=abm.message_str,
                message_obj=abm,
                platform_meta=self.meta(),
                session_id=abm.session_id,
                websocket_server=self.ws_server,
                client_id=client_id,
                config={
                    "enable_auto_emotion": self.platform_config.get(
                        "enable_auto_emotion", True
                    ),
                    "enable_tts": self.platform_config.get("enable_tts", False),
                    "tts_mode": self.platform_config.get("tts_mode", "local"),
                    "enable_streaming": self.platform_config.get(
                        "enable_streaming", True
                    ),
                },
                resource_manager=self.resource_manager,
            )
            message_event.set_extra("live2d_client_id", client_id)
            if extras:
                for key, value in extras.items():
                    message_event.set_extra(key, value)

            # 提交事件到 AstrBot 事件队列
            self.commit_event(message_event)
            logger.info(f"[Live2D] 事件已提交到队列: session_id={abm.session_id}")

        except Exception as e:
            logger.error(f"[Live2D] 处理消息事件失败: {e}", exc_info=True)

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        """通过会话发送消息到 Live2D 客户端

        Args:
            session: 消息会话
            message_chain: 消息链
        """
        try:
            if not self.ws_server or not self.current_client_id:
                logger.warning("[Live2D] 无可用连接，无法发送消息")
                return

            # 转换 MessageChain 为表演序列
            sequence = self.output_converter.convert(message_chain)

            if not sequence:
                logger.warning("[Live2D] 转换后的表演序列为空，跳过发送")
                await super().send_by_session(session, message_chain)
                return

            # 创建 perform.show 数据包
            packet = Protocol.create_perform_show(sequence=sequence, interrupt=True)

            # 广播到客户端（实际上只会发送给唯一的客户端）
            await self.ws_server.broadcast(packet)

            logger.info(f"[Live2D] 已发送表演序列，包含 {len(sequence)} 个元素")

        except Exception as e:
            logger.error(f"[Live2D] 发送消息失败: {e}", exc_info=True)

        # 调用父类方法（用于统计）
        await super().send_by_session(session, message_chain)

    async def run(self):
        """平台适配器主运行逻辑 - 启动 WebSocket 服务器并处理消息"""
        try:
            logger.info("[Live2D] 正在启动平台适配器...")

            # 创建 WebSocket 服务器
            self.ws_server = WebSocketServer(
                self.config_obj, resource_manager=self.resource_manager
            )

            # 修改 handler 以接入 AstrBot 事件流程
            await self._setup_message_handler()

            # 启动 WebSocket 服务器
            await self.ws_server.start()

            # 启动资源服务器
            if self.config_obj.resource_enabled:
                self.resource_server = ResourceServer(
                    manager=self.resource_manager,
                    host=self.config_obj.resource_host,
                    port=self.config_obj.resource_port,
                    resource_path=self.config_obj.resource_path,
                    token=self.config_obj.resource_token,
                )
                await self.resource_server.start()

            logger.info("[Live2D] 平台适配器启动成功")
            logger.info(
                f"[Live2D] WebSocket: ws://{self.config_obj.server_host}:{self.config_obj.server_port}{self.config_obj.ws_path}"
            )

            # 保持运行
            await asyncio.Future()

        except Exception as e:
            logger.error(f"[Live2D] 平台适配器运行失败: {e}", exc_info=True)
            raise

    async def _setup_message_handler(self):
        """设置消息处理器，覆盖 handler.py 的行为以接入 AstrBot"""
        ws_server = self.ws_server
        if not ws_server:
            raise RuntimeError("[Live2D] WebSocket 服务器未初始化")

        async def on_message_received(client_id: str, packet: BasePacket):
            """统一消息处理器 - 接入 AstrBot 事件流程"""
            self.current_client_id = client_id

            if packet.op == Protocol.OP_INPUT_MESSAGE:
                abm = await self.convert_message(packet, client_id)
                if abm:
                    await self.handle_msg(
                        abm, client_id, extras={"live2d_op": packet.op}
                    )
                return

            if packet.op == Protocol.OP_INPUT_TOUCH:
                abm = self.convert_touch(packet, client_id)
                await self.handle_msg(
                    abm, client_id, extras={"live2d_op": packet.op}
                )
                return

            if packet.op == Protocol.OP_INPUT_SHORTCUT:
                abm = self.convert_shortcut(packet, client_id)
                await self.handle_msg(
                    abm, client_id, extras={"live2d_op": packet.op}
                )
                return

            logger.debug(f"[Live2D] 未处理的消息类型: {packet.op}")

        ws_server.handler.on_message_received = on_message_received

    async def terminate(self):
        """终止平台适配器运行"""
        try:
            logger.info("[Live2D] 正在停止平台适配器...")

            if self.ws_server:
                await self.ws_server.stop()

            if self.resource_server:
                await self.resource_server.stop()

            logger.info("[Live2D] 平台适配器已停止")

        except Exception as e:
            logger.error(f"[Live2D] 停止平台适配器失败: {e}", exc_info=True)
