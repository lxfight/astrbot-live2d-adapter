"""消息处理器"""

from collections.abc import Callable

from astrbot.api import logger

from ..core.config import ConfigLike
from ..core.protocol import (
    BasePacket,
    create_expression_element,
    create_motion_element,
    create_text_element,
)
from ..core.protocol import (
    Protocol as ProtocolClass,
)


class MessageHandler:
    """消息处理器"""

    def __init__(self, config: ConfigLike, resource_manager=None):
        self.config = config
        self.resource_manager = resource_manager
        # 消息接收回调函数（由平台适配器注入）
        self.on_message_received: Callable | None = None
        self.client_states: dict[str, dict] = {}

    async def handle_packet(
        self, packet: BasePacket, client_id: str
    ) -> BasePacket | None:
        """
        处理接收到的数据包

        Args:
            packet: 接收到的数据包
            client_id: 客户端ID

        Returns:
            响应数据包（如果需要响应）
        """

        if packet.op == ProtocolClass.OP_HANDSHAKE:
            return await self.handle_handshake(packet, client_id)

        elif packet.op == ProtocolClass.OP_PING:
            return await self.handle_ping(packet)

        elif packet.op == ProtocolClass.OP_INPUT_TOUCH:
            return await self.handle_touch_input(packet, client_id)

        elif packet.op == ProtocolClass.OP_INPUT_MESSAGE:
            return await self.handle_message_input(packet, client_id)

        elif packet.op == ProtocolClass.OP_INPUT_SHORTCUT:
            return await self.handle_shortcut_input(packet, client_id)

        elif packet.op == ProtocolClass.OP_RESOURCE_PREPARE:
            return await self.handle_resource_prepare(packet)

        elif packet.op == ProtocolClass.OP_RESOURCE_COMMIT:
            return await self.handle_resource_commit(packet)

        elif packet.op == ProtocolClass.OP_RESOURCE_GET:
            return await self.handle_resource_get(packet)

        elif packet.op == ProtocolClass.OP_RESOURCE_RELEASE:
            return await self.handle_resource_release(packet)

        elif packet.op == ProtocolClass.OP_RESOURCE_PROGRESS:
            return await self.handle_resource_progress(packet, client_id)

        elif packet.op == ProtocolClass.OP_STATE_READY:
            return await self.handle_state_ready(packet, client_id)

        elif packet.op == ProtocolClass.OP_STATE_PLAYING:
            return await self.handle_state_playing(packet, client_id)

        elif packet.op == ProtocolClass.OP_STATE_CONFIG:
            return await self.handle_state_config(packet, client_id)

        elif packet.op == ProtocolClass.OP_STATE_MODEL:
            return await self.handle_state_model(packet, client_id)

        else:
            logger.warning(f"未知的操作码: {packet.op}")
            return None

    async def handle_handshake(self, packet: BasePacket, client_id: str) -> BasePacket:
        """处理握手请求"""
        payload = packet.payload or {}

        # 验证版本
        client_version = payload.get("version") or payload.get("protocol_version", "")
        if not client_version.startswith("1."):
            logger.error(f"版本不匹配: {client_version}")
            return ProtocolClass.create_error_packet(
                ProtocolClass.ERROR_VERSION_MISMATCH,
                "协议版本不兼容，请更新客户端",
                packet.id,
            )

        # 验证 Token
        if self.config.auth_token:
            client_token = payload.get("token", "")
            if client_token != self.config.auth_token:
                logger.error(f"Token 验证失败: {client_token}")
                return ProtocolClass.create_error_packet(
                    ProtocolClass.ERROR_AUTH_FAILED, "认证失败", packet.id
                )

        # 生成会话信息
        # Live2D 客户端使用固定的 client_id 作为 session_id
        # 类似私聊场景，同一个客户端永远是同一个 session_id
        session_id = client_id
        user_id = client_id
        self.client_states.setdefault(client_id, {})["session"] = {
            "session_id": session_id,
            "user_id": user_id,
        }

        logger.info(
            f"客户端 {client_id} 握手成功，分配 session_id: {session_id}, user_id: {user_id}"
        )
        capabilities = payload.get("capabilities") or []
        if capabilities:
            logger.info(f"客户端声明能力: {capabilities}")

        server_capabilities = [
            "input.message",
            "input.touch",
            "input.shortcut",
            "perform.show",
            "perform.interrupt",
            "state.ready",
            "state.playing",
            "state.config",
            "state.model",
        ]
        if self.resource_manager:
            server_capabilities.extend(
                [
                    "resource.prepare",
                    "resource.commit",
                    "resource.get",
                    "resource.release",
                    "resource.progress",
                ]
            )
        return ProtocolClass.create_handshake_ack(
            request_id=packet.id,
            session_id=session_id,
            user_id=user_id,
            capabilities=server_capabilities,
            config={
                "maxMessageLength": 5000,
                "supportedImageFormats": ["jpg", "png", "gif", "webp"],
                "supportedAudioFormats": ["mp3", "wav", "ogg"],
                "maxInlineBytes": getattr(
                    self.config, "resource_max_inline_bytes", 262144
                ),
                "resourceBaseUrl": getattr(self.config, "resource_base_url", ""),
            },
        )

    async def handle_ping(self, packet: BasePacket) -> BasePacket:
        """处理 Ping 请求"""
        return ProtocolClass.create_packet(ProtocolClass.OP_PONG, packet_id=packet.id)

    async def handle_touch_input(
        self, packet: BasePacket, client_id: str
    ) -> BasePacket | None:
        """处理触摸输入"""
        if self.on_message_received:
            try:
                await self.on_message_received(client_id, packet)
            except Exception as e:
                logger.error(f"触摸事件回调失败: {e}", exc_info=True)
            return None

        payload = packet.payload or {}
        part = payload.get("part") or payload.get("area") or "Unknown"
        action = payload.get("action", "tap")

        logger.info(f"客户端 {client_id} 触摸了 {part} ({action})")

        # 示例：触摸头部时播放特定动作
        if part == "Head":
            return ProtocolClass.create_perform_show(
                sequence=[
                    create_text_element("别摸我的头啦~", duration=2000),
                    create_expression_element("happy", fade=300),
                    create_motion_element("TapHead", index=0, priority=3),
                ],
                interrupt=True,
            )

        return None

    async def handle_message_input(
        self, packet: BasePacket, client_id: str
    ) -> BasePacket | None:
        """处理消息输入（input.message）"""
        payload = packet.payload or {}
        content = payload.get("content", [])

        logger.info(f"客户端 {client_id} 发送消息: {content}")

        # 如果注入了消息处理回调，调用它（由平台适配器处理并提交到 AstrBot）
        if self.on_message_received:
            try:
                await self.on_message_received(client_id, packet)
            except Exception as e:
                logger.error(f"消息处理回调失败: {e}", exc_info=True)
        else:
            # 如果没有回调（独立运行模式），返回简单回显
            logger.warning("未注入消息处理回调，使用回显模式")
            text_preview = ""
            for item in content:
                if item.get("type") == "text":
                    text_preview += item.get("text", "")

            return ProtocolClass.create_perform_show(
                sequence=[
                    create_text_element(f"收到了消息：{text_preview}", duration=3000)
                ],
                interrupt=True,
                packet_id=packet.id,
            )

        # 消息已交给 AstrBot 处理，不立即返回响应
        # AstrBot 处理完成后会通过 Live2DMessageEvent.send() 发送响应
        return None

    async def handle_shortcut_input(
        self, packet: BasePacket, client_id: str
    ) -> BasePacket | None:
        """处理快捷键输入"""
        if self.on_message_received:
            try:
                await self.on_message_received(client_id, packet)
            except Exception as e:
                logger.error(f"快捷键事件回调失败: {e}", exc_info=True)
            return None

        payload = packet.payload or {}
        key = payload.get("key", "")

        logger.info(f"客户端 {client_id} 触发快捷键: {key}")

        # 根据快捷键执行不同操作
        if key == "random_action":
            return ProtocolClass.create_perform_show(
                sequence=[
                    create_text_element("随机动作！", duration=2000),
                    create_motion_element("Idle", index=0, priority=2),
                ],
                interrupt=True,
            )

        return None

    async def handle_resource_prepare(self, packet: BasePacket) -> BasePacket:
        """处理资源上传申请"""
        if not self.resource_manager:
            return ProtocolClass.create_error_packet(
                ProtocolClass.ERROR_UNSUPPORTED_TYPE, "资源服务未启用", packet.id
            )
        payload = packet.payload or {}
        kind = payload.get("kind", "file")
        mime = payload.get("mime", "application/octet-stream")
        size = int(payload.get("size", 0) or 0)
        sha256 = payload.get("sha256")
        try:
            entry = self.resource_manager.prepare_upload(
                kind, mime, size=size, sha256=sha256
            )
        except ValueError as e:
            return ProtocolClass.create_error_packet(
                ProtocolClass.ERROR_FILE_UPLOAD_FAILED, str(e), packet.id
            )
        headers = {}
        if getattr(self.resource_manager, "token", None):
            headers["Authorization"] = f"Bearer {self.resource_manager.token}"
        return ProtocolClass.create_packet(
            ProtocolClass.OP_RESOURCE_PREPARE,
            payload={
                "rid": entry.rid,
                "upload": {
                    "method": "PUT",
                    "url": self.resource_manager.build_upload_url(entry.rid),
                    "headers": headers or None,
                },
                "resource": self.resource_manager.get_resource_payload(entry.rid),
            },
            packet_id=packet.id,
        )

    async def handle_resource_commit(self, packet: BasePacket) -> BasePacket:
        """处理资源上传确认"""
        if not self.resource_manager:
            return ProtocolClass.create_error_packet(
                ProtocolClass.ERROR_UNSUPPORTED_TYPE, "资源服务未启用", packet.id
            )
        payload = packet.payload or {}
        rid = payload.get("rid")
        size = payload.get("size")
        entry = self.resource_manager.commit_upload(rid, size=size)
        if not entry:
            return ProtocolClass.create_error_packet(
                ProtocolClass.ERROR_RESOURCE_NOT_FOUND, "资源不存在", packet.id
            )
        return ProtocolClass.create_packet(
            ProtocolClass.OP_RESOURCE_COMMIT,
            payload={"rid": entry.rid, "status": entry.status},
            packet_id=packet.id,
        )

    async def handle_resource_get(self, packet: BasePacket) -> BasePacket:
        """处理资源获取请求"""
        if not self.resource_manager:
            return ProtocolClass.create_error_packet(
                ProtocolClass.ERROR_UNSUPPORTED_TYPE, "资源服务未启用", packet.id
            )
        payload = packet.payload or {}
        rid = payload.get("rid")
        resource_payload = self.resource_manager.get_resource_payload(rid)
        if not resource_payload:
            return ProtocolClass.create_error_packet(
                ProtocolClass.ERROR_RESOURCE_NOT_FOUND, "资源不存在", packet.id
            )
        return ProtocolClass.create_packet(
            ProtocolClass.OP_RESOURCE_GET, payload=resource_payload, packet_id=packet.id
        )

    async def handle_resource_release(self, packet: BasePacket) -> BasePacket:
        """处理资源释放请求"""
        if not self.resource_manager:
            return ProtocolClass.create_error_packet(
                ProtocolClass.ERROR_UNSUPPORTED_TYPE, "资源服务未启用", packet.id
            )
        payload = packet.payload or {}
        rid = payload.get("rid")
        if not self.resource_manager.release(rid):
            return ProtocolClass.create_error_packet(
                ProtocolClass.ERROR_RESOURCE_NOT_FOUND, "资源不存在", packet.id
            )
        return ProtocolClass.create_packet(
            ProtocolClass.OP_RESOURCE_RELEASE,
            payload={"rid": rid, "released": True},
            packet_id=packet.id,
        )

    async def handle_resource_progress(
        self, packet: BasePacket, client_id: str
    ) -> BasePacket | None:
        """处理资源传输进度事件"""
        payload = packet.payload or {}
        logger.debug(f"客户端 {client_id} 资源进度: {payload}")
        return None

    async def handle_state_ready(
        self, packet: BasePacket, client_id: str
    ) -> BasePacket | None:
        """处理客户端就绪状态"""
        payload = packet.payload or {}
        self.client_states.setdefault(client_id, {})["ready"] = payload
        logger.info(f"客户端 {client_id} 状态就绪: {payload}")
        return None

    async def handle_state_playing(
        self, packet: BasePacket, client_id: str
    ) -> BasePacket | None:
        """处理播放状态更新"""
        payload = packet.payload or {}
        self.client_states.setdefault(client_id, {})["playing"] = payload
        logger.info(f"客户端 {client_id} 播放状态: {payload}")
        return None

    async def handle_state_config(
        self, packet: BasePacket, client_id: str
    ) -> BasePacket | None:
        """处理配置同步事件"""
        payload = packet.payload or {}
        self.client_states.setdefault(client_id, {})["config"] = payload
        logger.info(f"客户端 {client_id} 配置更新: {payload}")
        return None

    async def handle_state_model(
        self, packet: BasePacket, client_id: str
    ) -> BasePacket | None:
        """处理模型信息更新"""
        payload = packet.payload or {}
        self.client_states.setdefault(client_id, {})["model"] = payload

        model_name = payload.get("name", "unknown")
        motion_groups = payload.get("motionGroups", {})
        expressions = payload.get("expressions", [])

        # 计算总动作数和动作详情
        total_motions = 0
        motion_details = []
        if isinstance(motion_groups, dict):
            for group_name, motions in motion_groups.items():
                if isinstance(motions, list):
                    total_motions += len(motions)
                    motion_details.append(f"{group_name}({len(motions)})")

        logger.info(
            f"客户端 {client_id} 模型信息更新: "
            f"name={model_name}, "
            f"motion_groups={len(motion_groups)}, "
            f"total_motions={total_motions}, "
            f"expressions={len(expressions)}"
        )
        logger.debug(f"动作组详情: {', '.join(motion_details)}")

        # 打印每个动作组的详细动作列表
        for group_name, motions in motion_groups.items():
            if isinstance(motions, list):
                motion_files = [m.get('file', f"motion_{m.get('index', '?')}") for m in motions]
                logger.debug(f"  {group_name}: {motion_files}")

        logger.debug(f"表情列表: {expressions}")

        return None
