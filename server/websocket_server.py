"""WebSocket 服务器"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from astrbot.api import logger

from ..core.config import ConfigLike
from ..core.protocol import BasePacket
from ..core.protocol import Protocol as ProtocolClass
from .message_handler import MessageHandler


class WebSocketServer:
    """WebSocket 服务器"""

    def __init__(self, config: ConfigLike, resource_manager: Any | None = None):
        self.config = config
        self.handler = MessageHandler(config, resource_manager=resource_manager)
        self.clients: dict[str, Any] = {}
        self.server = None
        self.on_client_connected: Callable[[str], Awaitable[None]] | None = None
        self.on_client_disconnected: Callable[[str], Awaitable[None]] | None = None

    async def register(self, websocket, client_id: str):
        """注册客户端连接"""
        # 检查连接数限制
        if len(self.clients) >= self.config.max_connections:
            if self.config.kick_old and self.clients:
                # 踢掉最旧的连接
                old_id, old_ws = next(iter(self.clients.items()))
                logger.info(f"连接数已满，踢掉旧连接: {old_id}")
                await old_ws.close(1000, "新连接接入")
                del self.clients[old_id]
            else:
                # 拒绝新连接
                logger.warning("连接数已达上限，拒绝新连接")
                await websocket.close(1008, "连接数已满")
                return False

        self.clients[client_id] = websocket
        logger.info(f"客户端已连接: {client_id} (总数: {len(self.clients)})")

        if self.on_client_connected:
            try:
                await self.on_client_connected(client_id)
            except Exception as e:
                logger.warning(f"on_client_connected callback failed: {e!s}")
        return True

    async def unregister(self, client_id: str):
        """注销客户端连接"""
        if client_id in self.clients:
            del self.clients[client_id]
            logger.info(f"客户端已断开: {client_id} (总数: {len(self.clients)})")

            if self.on_client_disconnected:
                try:
                    await self.on_client_disconnected(client_id)
                except Exception as e:
                    logger.warning(f"on_client_disconnected callback failed: {e!s}")

    async def send_to(self, client_id: str, packet: BasePacket) -> None:
        """Send a packet to the specified client."""
        websocket = self.clients.get(client_id)
        if not websocket:
            logger.debug(f"Client {client_id} is not connected.")
            return

        try:
            await websocket.send(packet.to_json())
            logger.debug(f"发送消息到客户端 {client_id}: op={packet.op}")
        except Exception as e:
            logger.error(f"发送消息到客户端 {client_id} 失败: {e}")
            await self.unregister(client_id)

    async def broadcast(self, packet: BasePacket):
        """广播消息到所有客户端"""
        if not self.clients:
            logger.debug("没有已连接的客户端")
            return

        message = packet.to_json()
        disconnected = []

        for client_id, websocket in self.clients.items():
            try:
                await websocket.send(message)
                logger.debug(f"发送消息到客户端 {client_id}: op={packet.op}")
            except Exception as e:
                logger.error(f"发送消息到客户端 {client_id} 失败: {e}")
                disconnected.append(client_id)

        # 移除断开的客户端
        for client_id in disconnected:
            await self.unregister(client_id)

    async def handle_client(self, websocket):
        """处理客户端连接

        兼容 websockets 新版本：handler 只接收一个参数（连接对象），path 可从连接对象上获取。
        """
        # 兼容不同版本的 websockets：尽力提取 path（仅用于日志/调试）
        path = getattr(websocket, "path", None)
        if path is None:
            req = getattr(websocket, "request", None)
            path = getattr(req, "path", None)

        # 校验 WebSocket 路径（兼容 /ws 与 /astrbot/live2d）
        if path and self.config.ws_path:
            allowed_paths = {self.config.ws_path}
            allowed_paths.add("/ws")
            allowed_paths.add("/astrbot/live2d")
            if path not in allowed_paths:
                logger.warning(
                    f"拒绝连接: 路径不匹配 (期望: {self.config.ws_path}, 实际: {path})"
                )
                error = ProtocolClass.create_error_packet(
                    ProtocolClass.ERROR_INVALID_PAYLOAD,
                    f"路径不匹配，期望: {self.config.ws_path}",
                )
                await websocket.send(error.to_json())
                await websocket.close(1008, "路径不匹配")
                return

        client_id = None

        try:
            # 等待握手
            message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            if isinstance(message, bytes):
                message = message.decode("utf-8", errors="replace")
            packet = BasePacket.from_json(message)

            if packet.op != ProtocolClass.OP_HANDSHAKE:
                logger.error(f"首个消息不是握手: {packet.op}")
                error = ProtocolClass.create_error_packet(
                    ProtocolClass.ERROR_INVALID_PAYLOAD, "首个消息必须是握手"
                )
                await websocket.send(error.to_json())
                return

            # 获取客户端ID
            payload = packet.payload or {}
            client_id = (
                payload.get("clientId")
                or payload.get("deviceId")
                or payload.get("client")
                or BasePacket.generate_id()
            )

            # 处理握手
            response = await self.handler.handle_packet(packet, client_id)
            if response is None:
                logger.error("握手响应为空")
                return
            await websocket.send(response.to_json())

            # 如果握手失败，关闭连接
            if response.op == ProtocolClass.OP_ERROR:
                return

            # 注册客户端
            if not await self.register(websocket, client_id):
                return

            # 发送 ready 事件
            ready_packet = ProtocolClass.create_packet(
                ProtocolClass.OP_STATE_READY, payload={"clientId": client_id}
            )
            await websocket.send(ready_packet.to_json())

            # 消息循环
            async for message in websocket:
                try:
                    if isinstance(message, bytes):
                        message = message.decode("utf-8", errors="replace")
                    packet = BasePacket.from_json(message)
                    response = await self.handler.handle_packet(packet, client_id)

                    # 如果有响应，发送回客户端
                    if response:
                        await websocket.send(response.to_json())

                except Exception as e:
                    logger.error(f"处理消息时出错: {e}", exc_info=True)
                    error = ProtocolClass.create_error_packet(
                        ProtocolClass.ERROR_INVALID_PAYLOAD, f"消息处理失败: {e!s}"
                    )
                    await websocket.send(error.to_json())

        except asyncio.TimeoutError:
            logger.error("等待握手超时")

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"客户端连接关闭: {client_id}")

        except Exception as e:
            logger.error(f"处理客户端连接时出错: {e}", exc_info=True)

        finally:
            if client_id:
                await self.unregister(client_id)

    async def start(self):
        """启动服务器"""
        logger.info(
            f"启动 WebSocket 服务器: ws://{self.config.server_host}:{self.config.server_port}{self.config.ws_path}"
        )

        self.server = await websockets.serve(
            self.handle_client, self.config.server_host, self.config.server_port
        )

        logger.info("WebSocket 服务器已启动")

    async def stop(self):
        """停止服务器"""
        if self.server:
            logger.info("正在停止 WebSocket 服务器...")
            self.server.close()
            await self.server.wait_closed()
            logger.info("WebSocket 服务器已停止")

    async def run_forever(self):
        """持续运行服务器"""
        await self.start()

        try:
            # 保持服务器运行
            await asyncio.Future()
        except KeyboardInterrupt:
            logger.info("收到中断信号")
        finally:
            await self.stop()
