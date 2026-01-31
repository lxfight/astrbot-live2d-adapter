"""Live2D 适配器指令处理"""

from __future__ import annotations

import logging

try:
    from astrbot.api import logger as _astr_logger
    from astrbot.api.event import MessageChain
    from astrbot.api.message_components import Plain
    from astrbot.api.star import Context
except Exception as e:  # pragma: no cover
    raise ImportError(
        f"Failed to import AstrBot runtime modules; this adapter must run inside AstrBot: {e}"
    )

from ..adapters.platform_adapter import Live2DPlatformAdapter
from ..core.protocol import Protocol, create_motion_element, create_text_element

logger = _astr_logger or logging.getLogger(__name__)


class Live2DCommands:
    """Live2D 适配器指令处理器"""

    def __init__(self, adapter: Live2DPlatformAdapter, context: Context | None = None):
        """初始化指令处理器

        Args:
            adapter: Live2D 平台适配器实例
            context: AstrBot plugin context (used for hot reload)
        """
        self.adapter = adapter
        self.context = context

    async def handle_command(
        self, command: str, args: list[str]
    ) -> MessageChain | None:
        """处理指令

        Args:
            command: 指令名称（不含 /live2d 前缀）
            args: 指令参数列表

        Returns:
            消息链（如果需要回复）
        """
        if command == "status":
            return await self._cmd_status(args)
        elif command == "reload":
            return await self._cmd_reload(args)
        elif command == "say":
            return await self._cmd_say(args)
        elif command == "interrupt":
            return await self._cmd_interrupt(args)
        else:
            return self._make_chain(
                f"未知指令: /live2d {command}\n可用指令: status, reload, say, interrupt"
            )

    async def _cmd_status(self, args: list[str]) -> MessageChain | None:
        """/live2d status - 查看连接状态"""
        try:
            ws_server = self.adapter.ws_server
            if not ws_server:
                return self._make_chain("[Live2D] WebSocket 服务器未启动")

            client_count = len(ws_server.clients)
            client_ids = list(ws_server.clients.keys())

            status_text = f"""[Live2D] 适配器状态
━━━━━━━━━━━━━━━━━━━━
📡 WebSocket: ws://{self.adapter.config_obj.server_host}:{self.adapter.config_obj.server_port}{self.adapter.config_obj.ws_path}
🔌 已连接客户端: {client_count}/{self.adapter.config_obj.max_connections}
"""

            if client_ids:
                status_text += f"👤 客户端 ID: {', '.join(client_ids[:3])}"
                if len(client_ids) > 3:
                    status_text += f" (+{len(client_ids) - 3} 个)"
            else:
                status_text += "⚠️ 当前无客户端连接"

            status_text += f"""

⚙️ 配置:
  - 自动情感: {"✅" if self.adapter.platform_config.get("enable_auto_emotion") else "❌"}
  - TTS: {"✅" if self.adapter.platform_config.get("enable_tts") else "❌"}
  - TTS 模式: {self.adapter.platform_config.get("tts_mode", "local")}
  - 流式输出: {"✅" if self.adapter.platform_config.get("enable_streaming", True) else "❌"}
"""

            return self._make_chain(status_text)

        except Exception as e:
            logger.error(f"[Live2D] status 指令执行失败: {e}", exc_info=True)
            return self._make_chain(f"[Live2D] 查询状态失败: {e}")

    async def _cmd_reload(self, args: list[str]) -> MessageChain | None:
        """/live2d reload - 重载配置"""
        try:
            if not self.context or not getattr(self.context, "platform_manager", None):
                return self._make_chain("[Live2D] Reload is unavailable (no context).")

            platform_id = self.adapter.meta().id
            platform_manager = self.context.platform_manager

            platform_config = None
            for cfg in getattr(platform_manager, "platforms_config", []) or []:
                if cfg.get("type") == "live2d" and cfg.get("id") == platform_id:
                    platform_config = cfg
                    break

            platform_config = platform_config or getattr(
                self.adapter, "platform_config", None
            )
            if not platform_config:
                return self._make_chain("[Live2D] Failed to locate platform config.")

            await platform_manager.reload(platform_config)

            try:
                new_inst = self.context.get_platform_inst(platform_id)
                if isinstance(new_inst, Live2DPlatformAdapter):
                    self.adapter = new_inst
            except Exception:
                pass

            return self._make_chain(f"[Live2D] Reloaded platform: {platform_id}")

        except Exception as e:
            logger.error(f"[Live2D] reload 指令执行失败: {e}", exc_info=True)
            return self._make_chain(f"[Live2D] 重载配置失败: {e}")

    async def _cmd_say(self, args: list[str]) -> MessageChain | None:
        """/live2d say <text> - 直接向 Live2D 客户端发送文本表演"""
        if not args:
            return self._make_chain("[Live2D] 用法: /live2d say <要说的内容>")

        text = " ".join(args)

        try:
            ws_server = self.adapter.ws_server
            if not ws_server or not ws_server.clients:
                return self._make_chain("[Live2D] 没有已连接的客户端")

            # 创建简单的文本表演序列
            sequence = [
                create_text_element(text, duration=0),
                create_motion_element("Idle", index=0, priority=2),
            ]

            # 发送 perform.show
            packet = Protocol.create_perform_show(sequence=sequence, interrupt=True)
            await ws_server.broadcast(packet)

            logger.info(f"[Live2D] say 指令已发送: {text[:50]}...")
            return self._make_chain(f"[Live2D] 已发送到客户端: {text[:100]}...")

        except Exception as e:
            logger.error(f"[Live2D] say 指令执行失败: {e}", exc_info=True)
            return self._make_chain(f"[Live2D] 发送失败: {e}")

    async def _cmd_interrupt(self, args: list[str]) -> MessageChain | None:
        """/live2d interrupt - 中断客户端当前表演"""
        try:
            ws_server = self.adapter.ws_server
            if not ws_server or not ws_server.clients:
                return self._make_chain("[Live2D] 没有已连接的客户端")

            packet = Protocol.create_perform_interrupt()
            await ws_server.broadcast(packet)

            logger.info("[Live2D] interrupt 指令已发送")
            return self._make_chain("[Live2D] 已发送中断指令")

        except Exception as e:
            logger.error(f"[Live2D] interrupt 指令执行失败: {e}", exc_info=True)
            return self._make_chain(f"[Live2D] 中断失败: {e}")

    def _make_chain(self, text: str) -> MessageChain | None:
        """创建消息链

        Args:
            text: 文本内容

        Returns:
            MessageChain 对象
        """
        chain = MessageChain()
        chain.chain.append(Plain(text))
        return chain
