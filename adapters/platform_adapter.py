"""Live2D 平台适配器 - AstrBot 平台适配器实现"""

import asyncio
import json
from asyncio import Queue
from pathlib import Path

try:
    from astrbot.api import logger
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
    from astrbot.core.star.star_tools import StarTools
except ImportError as e:
    raise ImportError(
        f"无法导入 AstrBot 模块，请确保此适配器作为 AstrBot 插件运行: {e}"
    )

from ..converters.input_converter import InputMessageConverter
from ..converters.output_converter import OutputMessageConverter
from ..core.config import ConfigLike
from ..core.desktop_request import DesktopRequestManager
from ..core.protocol import BasePacket
from ..core.protocol import Protocol as ProtocolClass
from ..server.resource_manager import ResourceManager
from ..server.resource_server import ResourceServer
from ..server.websocket_server import WebSocketServer
from .message_event import Live2DMessageEvent


@register_platform_adapter(
    "live2d",
    "Live2D 桌面应用适配器，支持 Live2D-Bridge Protocol v1.0",
    default_config_tmpl={
        "type": "live2d",
        "enable": False,
        "id": "live2d_default",
        # WebSocket 服务器配置 | WebSocket Server Configuration
        "ws_host": "0.0.0.0",  # WebSocket 服务监听地址 | Listen address
        "ws_port": 9090,  # WebSocket 服务端口 | Server port
        "ws_path": "/astrbot/live2d",  # WebSocket 连接路径 | Connection path
        "auth_token": "",  # 认证令牌(可选) | Auth token (optional)
        "max_connections": 1,  # 最大连接数 | Max connections
        "kick_old": True,  # 断开旧连接 | Kick old connections
        # 语音合成 | TTS
        "enable_tts": False,  # 启用TTS | Enable TTS
        # 流式消息 | Streaming
        "enable_streaming": True,  # 启用流式推送 | Enable streaming
        # 资源服务器 | Resource Server
        "resource_enabled": True,  # 启用资源服务 | Enable resource server
        "resource_host": "0.0.0.0",  # 资源服务监听地址 | Resource listen address
        "resource_port": 9091,  # 资源服务端口 | Resource port
        "resource_path": "/resources",  # 资源访问路径 | Resource path
        "resource_dir": "live2d_resources",  # 资源存储目录 | Resource directory
        "resource_base_url": "",  # 资源基础URL(空=自动) | Base URL (empty=auto)
        "resource_token": "",  # 资源访问令牌(空=复用auth_token) | Resource token
        "resource_max_inline_bytes": 262144,  # 内联资源最大字节(256KB) | Max inline bytes
        "resource_ttl_seconds": 604800,  # 资源TTL(7天) | Resource TTL (7 days)
        "resource_max_total_bytes": 1073741824,  # 最大总字节(1GB) | Max total bytes
        "resource_max_files": 2000,  # 最大文件数 | Max files
        # 临时文件 | Temporary Files
        "temp_dir": "live2d_temp",  # 临时文件目录 | Temp directory
        "temp_ttl_seconds": 21600,  # 临时文件TTL(6小时) | Temp TTL (6 hours)
        "temp_max_total_bytes": 268435456,  # 临时文件最大总字节(256MB) | Max temp bytes
        "temp_max_files": 5000,  # 临时文件最大数量 | Max temp files
        # 系统配置 | System Configuration
        "cleanup_interval_seconds": 600,  # 清理检查间隔(10分钟) | Cleanup interval
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

        # 获取插件数据目录
        plugin_data_dir = StarTools.get_data_dir("astrbot-live2d-adapter")

        # 初始化配置对象
        self.config_obj: ConfigLike = self._create_config_from_dict(
            self.config, plugin_data_dir
        )

        # WebSocket 服务器实例
        self.ws_server: WebSocketServer | None = None
        self.resource_server: ResourceServer | None = None

        self._stop_event = asyncio.Event()
        self._cleanup_task: asyncio.Task | None = None

        self.resource_manager: ResourceManager | None = None
        if self.config_obj.resource_enabled:
            resource_ttl_ms = (
                self.config_obj.resource_ttl_seconds * 1000
                if self.config_obj.resource_ttl_seconds > 0
                else None
            )
            self.resource_manager = ResourceManager(
                storage_dir=self.config_obj.resource_dir,
                base_url=self.config_obj.resource_base_url,
                resource_path=self.config_obj.resource_path,
                max_inline_bytes=self.config_obj.resource_max_inline_bytes,
                token=self.config_obj.resource_token,
                ttl_ms=resource_ttl_ms,
                max_total_bytes=self.config_obj.resource_max_total_bytes,
                max_total_files=self.config_obj.resource_max_files,
            )

        # 消息转换器
        self.input_converter = InputMessageConverter(
            temp_dir=self.config_obj.temp_dir,
            temp_ttl_seconds=self.config_obj.temp_ttl_seconds,
            temp_max_total_bytes=self.config_obj.temp_max_total_bytes,
            temp_max_files=self.config_obj.temp_max_files,
            resource_manager=self.resource_manager,
        )
        self.output_converter = OutputMessageConverter(
            enable_tts=self.config_obj.enable_tts,
            resource_manager=self.resource_manager,
            resource_config={
                "max_inline_bytes": self.config_obj.resource_max_inline_bytes,
                "base_url": self.config_obj.resource_base_url,
                "resource_path": self.config_obj.resource_path,
            },
        )

        # 当前连接的客户端ID（单一连接约束）
        self.current_client_id: str | None = None
        self._session_to_client_id: dict[str, str] = {}

        # 桌面感知请求管理器
        self.desktop_request_mgr = DesktopRequestManager()
        self._registered_tool_names: list[str] = []

        logger.info(f"[Live2D] 平台适配器已初始化，ID: {self.config.get('id')}")

    def _create_config_from_dict(
        self, config_dict: dict, plugin_data_dir: Path
    ) -> ConfigLike:
        """从配置字典创建配置对象

        Args:
            config_dict: 配置字典
            plugin_data_dir: 插件数据目录

        Returns:
            配置对象
        """

        class ConfigAdapter:
            def __init__(self, data: dict, base_dir: Path):
                self._data = data
                self._base_dir = base_dir

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
                return self._data.get("ws_path", "/astrbot/live2d")

            @property
            def max_connections(self) -> int:
                return self._data.get("max_connections", 1)

            @property
            def kick_old(self) -> bool:
                return self._data.get("kick_old", True)

            @property
            def enable_tts(self) -> bool:
                return self._data.get("enable_tts", False)

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
                default_dir = self._base_dir / "live2d_resources"
                resource_dir = self._data.get("resource_dir", str(default_dir))
                if not Path(resource_dir).is_absolute():
                    resource_dir = str(self._base_dir / resource_dir)
                return resource_dir

            @property
            def resource_base_url(self) -> str:
                base_url = self._data.get("resource_base_url", "")
                if base_url:
                    return base_url
                host = self.resource_host
                if host in {"0.0.0.0", "::"}:
                    host = "127.0.0.1"
                return f"http://{host}:{self.resource_port}"

            @property
            def resource_token(self) -> str:
                token = self._data.get("resource_token", "")
                return token if token else self.auth_token

            @property
            def resource_max_inline_bytes(self) -> int:
                return self._data.get("resource_max_inline_bytes", 262144)

            @property
            def resource_ttl_seconds(self) -> int:
                return self._data.get("resource_ttl_seconds", 604800)

            @property
            def resource_max_total_bytes(self) -> int:
                return self._data.get("resource_max_total_bytes", 1073741824)

            @property
            def resource_max_files(self) -> int:
                return self._data.get("resource_max_files", 2000)

            @property
            def temp_dir(self) -> str:
                default_dir = self._base_dir / "live2d_temp"
                temp_dir = self._data.get("temp_dir", str(default_dir))
                if not Path(temp_dir).is_absolute():
                    temp_dir = str(self._base_dir / temp_dir)
                return temp_dir

            @property
            def temp_ttl_seconds(self) -> int:
                return self._data.get("temp_ttl_seconds", 21600)

            @property
            def temp_max_total_bytes(self) -> int:
                return self._data.get("temp_max_total_bytes", 268435456)

            @property
            def temp_max_files(self) -> int:
                return self._data.get("temp_max_files", 5000)

            @property
            def enable_streaming(self) -> bool:
                return self._data.get("enable_streaming", True)

            @property
            def cleanup_interval_seconds(self) -> int:
                return self._data.get("cleanup_interval_seconds", 600)

        return ConfigAdapter(config_dict, plugin_data_dir)

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
        return ws_server.handler.client_states.get(client_id, {}).get("session", {})

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
        if (
            metadata.get("groupId")
            or metadata.get("group_id")
            or metadata.get("isGroup")
        ):
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
        if packet.op != ProtocolClass.OP_INPUT_MESSAGE:
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
                    "enable_tts": self.config.get("enable_tts", False),
                    "enable_streaming": self.config.get("enable_streaming", True),
                },
                resource_manager=self.resource_manager,
            )
            message_event.set_extra("live2d_client_id", client_id)
            if extras:
                for key, value in extras.items():
                    message_event.set_extra(key, value)

            # Cache session -> client mapping for correct routing in send_by_session.
            self._session_to_client_id[str(abm.session_id)] = client_id

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
            if not self.ws_server or not self.ws_server.clients:
                logger.warning("[Live2D] 无可用连接，无法发送消息")
                await super().send_by_session(session, message_chain)
                return

            target_client_id = self._session_to_client_id.get(str(session.session_id))
            if not target_client_id:
                # Fallback to the only connected client if possible.
                if len(self.ws_server.clients) == 1:
                    target_client_id = next(iter(self.ws_server.clients.keys()))
                else:
                    target_client_id = self.current_client_id

            if not target_client_id:
                logger.warning("[Live2D] 无法确定目标客户端，放弃发送")
                await super().send_by_session(session, message_chain)
                return

            # 获取客户端模型信息
            client_model_info = None
            if (
                hasattr(self.ws_server, "handler")
                and self.ws_server.handler
            ):
                client_state = self.ws_server.handler.client_states.get(
                    target_client_id, {}
                )
                client_model_info = client_state.get("model")

            # 更新转换器的模型信息
            self.output_converter.client_model_info = client_model_info or {}

            # 转换 MessageChain 为表演序列
            sequence = self.output_converter.convert(message_chain)

            if not sequence:
                logger.warning("[Live2D] 转换后的表演序列为空，跳过发送")
                await super().send_by_session(session, message_chain)
                return

            # 创建 perform.show 数据包
            packet = ProtocolClass.create_perform_show(
                sequence=sequence, interrupt=True
            )

            await self.ws_server.send_to(target_client_id, packet)

            logger.info(f"[Live2D] 已发送表演序列，包含 {len(sequence)} 个元素")

        except Exception as e:
            logger.error(f"[Live2D] 发送消息失败: {e}", exc_info=True)

        # 调用父类方法（用于统计）
        await super().send_by_session(session, message_chain)

    async def run(self):
        """平台适配器主运行逻辑 - 启动 WebSocket 服务器并处理消息"""
        try:
            logger.info("[Live2D] 正在启动平台适配器...")
            self._stop_event.clear()

            # 创建 WebSocket 服务器
            self.ws_server = WebSocketServer(
                self.config_obj, resource_manager=self.resource_manager
            )

            async def on_client_connected(client_id: str) -> None:
                self.current_client_id = client_id
                session = self._get_client_session(client_id)
                session_id = session.get("session_id")
                if session_id:
                    self._session_to_client_id[str(session_id)] = client_id

            async def on_client_disconnected(client_id: str) -> None:
                if self.current_client_id == client_id:
                    if self.ws_server and self.ws_server.clients:
                        self.current_client_id = next(iter(self.ws_server.clients))
                    else:
                        self.current_client_id = None

                for session_id, mapped in list(self._session_to_client_id.items()):
                    if mapped == client_id:
                        self._session_to_client_id.pop(session_id, None)

                self._unregister_desktop_tools()

            self.ws_server.on_client_connected = on_client_connected
            self.ws_server.on_client_disconnected = on_client_disconnected

            # 修改 handler 以接入 AstrBot 事件流程
            await self._setup_message_handler()

            # 启动 WebSocket 服务器
            await self.ws_server.start()

            # 启动资源服务器
            if self.resource_manager is not None:
                self.resource_server = ResourceServer(
                    manager=self.resource_manager,
                    host=self.config_obj.resource_host,
                    port=self.config_obj.resource_port,
                    resource_path=self.config_obj.resource_path,
                    token=self.config_obj.resource_token,
                )
                await self.resource_server.start()

            # Background cleanup task (resources + temp files)
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

            logger.info("[Live2D] 平台适配器启动成功")
            logger.info(
                f"[Live2D] WebSocket: ws://{self.config_obj.server_host}:{self.config_obj.server_port}{self.config_obj.ws_path}"
            )

            # 保持运行
            await self._stop_event.wait()

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

            if packet.op == ProtocolClass.OP_INPUT_MESSAGE:
                abm = await self.convert_message(packet, client_id)
                if abm:
                    await self.handle_msg(
                        abm, client_id, extras={"live2d_op": packet.op}
                    )
                return

            if packet.op == ProtocolClass.OP_INPUT_TOUCH:
                abm = self.convert_touch(packet, client_id)
                await self.handle_msg(abm, client_id, extras={"live2d_op": packet.op})
                return

            if packet.op == ProtocolClass.OP_INPUT_SHORTCUT:
                abm = self.convert_shortcut(packet, client_id)
                await self.handle_msg(abm, client_id, extras={"live2d_op": packet.op})
                return

            logger.debug(f"[Live2D] 未处理的消息类型: {packet.op}")

        ws_server.handler.on_message_received = on_message_received

        # 桌面感知响应路由
        ws_server.handler.on_desktop_response = (
            lambda pid, payload, error=None: self.desktop_request_mgr.resolve(pid, payload, error)
        )

        ws_server.handler.on_tools_declared = (
            lambda client_id, tools: self._register_desktop_tools(tools)
        )

    def _unregister_desktop_tools(self):
        """注销所有已注册的桌面工具"""
        for name in self._registered_tool_names:
            try:
                StarTools.unregister_llm_tool(name)
                logger.info(f"[Live2D] 已注销桌面工具: {name}")
            except Exception as e:
                logger.debug(f"[Live2D] 注销工具 {name} 失败: {e}")
        self._registered_tool_names.clear()

    def _register_desktop_tools(self, tools: list[dict]):
        """根据桌面端声明的工具列表动态注册到 AstrBot"""
        self._unregister_desktop_tools()
        for tool_decl in tools:
            tool_name = tool_decl.get("name")
            tool_desc = tool_decl.get("description", "")
            tool_params = tool_decl.get("parameters", [])
            if not tool_name:
                continue
            func_args = [
                {
                    "type": p.get("type", "string"),
                    "name": p.get("name"),
                    "description": p.get("description", ""),
                }
                for p in tool_params
            ]
            handler = self._make_tool_handler(tool_name)
            try:
                StarTools.register_llm_tool(tool_name, func_args, tool_desc, handler)
                self._registered_tool_names.append(tool_name)
                logger.info(f"[Live2D] 已注册桌面工具: {tool_name}")
            except Exception as e:
                logger.error(f"[Live2D] 注册工具 {tool_name} 失败: {e}")

    def _make_tool_handler(self, tool_name: str):
        """创建桌面工具的动态处理函数"""
        adapter = self

        async def handler(event=None, context=None, **kwargs):
            if not adapter.current_client_id:
                return "错误：Live2D 客户端未连接"
            packet = ProtocolClass.create_packet(
                ProtocolClass.OP_DESKTOP_TOOL_CALL,
                payload={"tool": tool_name, "args": kwargs},
            )
            try:
                result = await adapter.desktop_request_mgr.request(
                    adapter.ws_server, adapter.current_client_id, packet, timeout=30.0
                )
            except asyncio.TimeoutError:
                return f"错误：工具 {tool_name} 调用超时，桌面端未响应"
            except RuntimeError as e:
                return f"错误：{e}"
            if result.get("error"):
                return f"错误：{result['error']}"
            tool_result = result.get("result", {})
            # 截图工具：图片附加到消息上下文
            if tool_name == "capture_screenshot" and event:
                return adapter._handle_screenshot_result(event, tool_result)
            # 通用结果格式化
            if isinstance(tool_result, dict):
                window = tool_result.get("window")
                if window is not None:
                    if window:
                        return (
                            f"当前活跃窗口：{window.get('title', '未知')}\n"
                            f"进程：{window.get('processName', '未知')}"
                        )
                    return "未检测到活跃窗口"
            return json.dumps(tool_result, ensure_ascii=False) if tool_result else "操作完成"

        return handler

    def _handle_screenshot_result(self, event, tool_result: dict) -> str:
        """处理截图结果，将图片附加到消息上下文"""
        image_data = tool_result.get("image", "") if isinstance(tool_result, dict) else ""
        if image_data:
            if image_data.startswith(("http://", "https://")):
                image_comp = self.input_converter.convert_image({"url": image_data})
            else:
                image_comp = self.input_converter.convert_image({"data": image_data})
            if image_comp:
                event.message_obj.message.append(image_comp)
        window_info = tool_result.get("window", {}) if isinstance(tool_result, dict) else {}
        title = window_info.get("title", "未知")
        return f"已截取屏幕截图（来源：{title}），图片已附加到上下文中，请分析图片内容。"

    def _run_cleanup(self) -> None:
        """Best-effort cleanup for disk resources and temp files."""
        if self.resource_manager:
            try:
                stats = self.resource_manager.cleanup()
                if stats.get("removed"):
                    logger.debug(
                        "[Live2D] Resource cleanup: removed=%s bytes=%s",
                        stats.get("removed"),
                        stats.get("removed_bytes"),
                    )
            except Exception as e:
                logger.debug(f"[Live2D] Resource cleanup failed: {e!s}")

        try:
            stats = self.input_converter.cleanup_temp_files()
            if stats.get("removed"):
                logger.debug(
                    "[Live2D] Temp cleanup: removed=%s bytes=%s",
                    stats.get("removed"),
                    stats.get("removed_bytes"),
                )
        except Exception as e:
            logger.debug(f"[Live2D] Temp cleanup failed: {e!s}")

    async def _cleanup_loop(self) -> None:
        interval = int(self.config.get("cleanup_interval_seconds", 600) or 600)
        if interval < 10:
            interval = 10

        self._run_cleanup()

        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
            if self._stop_event.is_set():
                break
            self._run_cleanup()

    async def terminate(self):
        """终止平台适配器运行"""
        try:
            logger.info("[Live2D] 正在停止平台适配器...")
            self._stop_event.set()

            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
                self._cleanup_task = None

            if self.ws_server:
                await self.ws_server.stop()

            if self.resource_server:
                await self.resource_server.stop()

            self._unregister_desktop_tools()

            logger.info("[Live2D] 平台适配器已停止")

        except Exception as e:
            logger.error(f"[Live2D] 停止平台适配器失败: {e}", exc_info=True)
