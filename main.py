"""AstrBot Live2D Adapter - AstrBot 插件入口"""

import asyncio
import time

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star
from astrbot.core.config.default import CONFIG_METADATA_2

from .adapters.platform_adapter import Live2DPlatformAdapter
from .core.protocol import Protocol


class Live2DAdapter(Star):
    """Live2D 平台适配器插件"""

    _registered: bool = False

    _live2d_items = {
        "ws_host": {
            "description": "WebSocket 监听地址",
            "type": "string",
            "hint": "WebSocket 服务监听地址，默认 0.0.0.0",
        },
        "ws_port": {
            "description": "WebSocket 端口",
            "type": "int",
            "hint": "WebSocket 服务端口，默认 9090",
        },
        "ws_path": {
            "description": "WebSocket 路径",
            "type": "string",
            "hint": "WebSocket 连接路径，默认 /astrbot/live2d",
        },
        "auth_token": {
            "description": "认证令牌",
            "type": "string",
            "hint": "认证令牌(可选)，用于客户端连接验证",
        },
        "max_connections": {
            "description": "最大连接数",
            "type": "int",
            "hint": "允许的最大客户端连接数，默认 1",
        },
        "kick_old": {
            "description": "断开旧连接",
            "type": "bool",
            "hint": "新连接时是否断开旧连接，默认 true",
        },
        "enable_tts": {
            "description": "启用 TTS",
            "type": "bool",
            "hint": "是否启用语音合成功能，默认 false",
        },
        "enable_streaming": {
            "description": "启用流式推送",
            "type": "bool",
            "hint": "是否启用流式消息推送，默认 true",
        },
        "resource_enabled": {
            "description": "启用资源服务",
            "type": "bool",
            "hint": "是否启用资源服务器，默认 true",
        },
        "resource_host": {
            "description": "资源服务监听地址",
            "type": "string",
            "hint": "资源服务监听地址，默认 0.0.0.0",
        },
        "resource_port": {
            "description": "资源服务端口",
            "type": "int",
            "hint": "资源服务端口，默认 9091",
        },
        "resource_path": {
            "description": "资源访问路径",
            "type": "string",
            "hint": "资源访问路径，默认 /resources",
        },
        "resource_dir": {
            "description": "资源存储目录",
            "type": "string",
            "hint": "资源文件存储目录，默认 live2d_resources",
        },
        "resource_base_url": {
            "description": "资源基础 URL",
            "type": "string",
            "hint": "资源基础 URL，留空则自动生成",
        },
        "resource_token": {
            "description": "资源访问令牌",
            "type": "string",
            "hint": "资源访问令牌，留空则复用 auth_token",
        },
        "resource_max_inline_bytes": {
            "description": "内联资源最大字节",
            "type": "int",
            "hint": "内联资源最大字节数，默认 262144 (256KB)",
        },
        "resource_ttl_seconds": {
            "description": "资源 TTL(秒)",
            "type": "int",
            "hint": "资源生存时间(秒)，默认 604800 (7天)",
        },
        "resource_max_total_bytes": {
            "description": "最大总字节",
            "type": "int",
            "hint": "资源最大总字节数，默认 1073741824 (1GB)",
        },
        "resource_max_files": {
            "description": "最大文件数",
            "type": "int",
            "hint": "资源最大文件数，默认 2000",
        },
        "temp_dir": {
            "description": "临时文件目录",
            "type": "string",
            "hint": "临时文件存储目录，默认 live2d_temp",
        },
        "temp_ttl_seconds": {
            "description": "临时文件 TTL(秒)",
            "type": "int",
            "hint": "临时文件生存时间(秒)，默认 21600 (6小时)",
        },
        "temp_max_total_bytes": {
            "description": "临时文件最大总字节",
            "type": "int",
            "hint": "临时文件最大总字节数，默认 268435456 (256MB)",
        },
        "temp_max_files": {
            "description": "临时文件最大数量",
            "type": "int",
            "hint": "临时文件最大数量，默认 5000",
        },
        "cleanup_interval_seconds": {
            "description": "清理检查间隔(秒)",
            "type": "int",
            "hint": "资源清理检查间隔(秒)，默认 600 (10分钟)",
        },
    }

    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context

    def _get_adapter(self) -> Live2DPlatformAdapter | None:
        """获取 Live2D 平台适配器实例"""
        try:
            platform_manager = self.context.platform_manager
            for platform in platform_manager.platform_insts:
                if isinstance(platform, Live2DPlatformAdapter):
                    return platform
            return None
        except Exception as e:
            logger.error(f"获取 Live2D 适配器失败: {e}")
            return None

    def _format_bytes(self, bytes_size: int) -> str:
        """格式化字节大小"""
        size = float(bytes_size)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f}{unit}"
            size /= 1024.0
        return f"{size:.1f}TB"

    def _format_duration(self, seconds: int) -> str:
        """格式化时长"""
        if seconds < 60:
            return f"{seconds}秒"
        elif seconds < 3600:
            return f"{seconds // 60}分钟"
        elif seconds < 86400:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}小时{minutes}分钟"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            return f"{days}天{hours}小时"

    @filter.command("live2d.status", alias={"l2d.status"})
    async def cmd_status(self, event: AstrMessageEvent) -> MessageChain:
        """显示 Live2D 适配器状态"""
        adapter = self._get_adapter()
        if not adapter:
            return MessageChain().message("[Live2D Adapter] 错误: 适配器未启动或未找到")
        return await self._cmd_status(adapter)

    @filter.command("live2d.info", alias={"l2d.info"})
    async def cmd_info(self, event: AstrMessageEvent) -> MessageChain:
        """显示当前客户端详细信息"""
        adapter = self._get_adapter()
        if not adapter:
            return MessageChain().message("[Live2D Adapter] 错误: 适配器未启动或未找到")
        return await self._cmd_info(adapter)

    @filter.command("live2d.list", alias={"l2d.list", "l2d.clients"})
    async def cmd_list(self, event: AstrMessageEvent) -> MessageChain:
        """列出所有连接的客户端"""
        adapter = self._get_adapter()
        if not adapter:
            return MessageChain().message("[Live2D Adapter] 错误: 适配器未启动或未找到")
        return await self._cmd_list(adapter)

    @filter.command("live2d.resources", alias={"l2d.resources", "l2d.res"})
    async def cmd_resources(self, event: AstrMessageEvent) -> MessageChain:
        """显示资源使用情况"""
        adapter = self._get_adapter()
        if not adapter:
            return MessageChain().message("[Live2D Adapter] 错误: 适配器未启动或未找到")
        return await self._cmd_resources(adapter)

    @filter.command("live2d.cleanup", alias={"l2d.cleanup"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_cleanup(self, event: AstrMessageEvent) -> MessageChain:
        """手动触发资源清理（仅管理员）"""
        adapter = self._get_adapter()
        if not adapter:
            return MessageChain().message("[Live2D Adapter] 错误: 适配器未启动或未找到")
        return await self._cmd_cleanup(adapter)

    @filter.command("live2d.config", alias={"l2d.config", "l2d.cfg"})
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def cmd_config(self, event: AstrMessageEvent) -> MessageChain:
        """显示当前配置（仅管理员）"""
        adapter = self._get_adapter()
        if not adapter:
            return MessageChain().message("[Live2D Adapter] 错误: 适配器未启动或未找到")
        return await self._cmd_config(adapter)

    async def _cmd_status(self, adapter: Live2DPlatformAdapter) -> MessageChain:
        """显示适配器状态"""
        try:
            # 连接信息
            ws_server = adapter.ws_server
            client_count = len(ws_server.clients) if ws_server else 0
            max_connections = adapter.config_obj.max_connections
            current_client = adapter.current_client_id

            # 资源使用情况
            resource_info = ""
            if adapter.resource_manager:
                rm = adapter.resource_manager
                resource_files = len(rm.resources)
                max_files = rm.max_total_files or 1
                total_bytes = sum(r.size for r in rm.resources.values())
                max_bytes = rm.max_total_bytes or 1
                usage_percent = (total_bytes / max_bytes * 100) if max_bytes > 0 else 0

                resource_info = f"""
资源使用:
  - 资源文件: {resource_files}/{max_files} ({resource_files / max_files * 100:.1f}%)
  - 存储空间: {self._format_bytes(total_bytes)}/{self._format_bytes(max_bytes)} ({usage_percent:.1f}%)"""

            # 临时文件信息
            temp_info = ""
            if adapter.input_converter and hasattr(
                adapter.input_converter, "get_temp_files_info"
            ):
                temp_info_data = adapter.input_converter.get_temp_files_info()
                temp_files = temp_info_data["count"]
                temp_bytes = temp_info_data["total_bytes"]
                max_temp_files = getattr(adapter.input_converter, "temp_max_files", 1)
                max_temp_bytes = getattr(
                    adapter.input_converter, "temp_max_total_bytes", 1
                )
                temp_usage = (
                    (temp_bytes / max_temp_bytes * 100) if max_temp_bytes > 0 else 0
                )

                temp_info = f"""
  - 临时文件: {temp_files}/{max_temp_files}
  - 临时空间: {self._format_bytes(temp_bytes)}/{self._format_bytes(max_temp_bytes)} ({temp_usage:.1f}%)"""

            # 服务器状态
            ws_status = "运行中" if ws_server and ws_server.server else "未运行"
            ws_addr = (
                f"{adapter.config_obj.server_host}:{adapter.config_obj.server_port}"
            )

            resource_server_status = "未启用"
            resource_addr = ""
            if adapter.resource_server:
                resource_server_status = "运行中"
                resource_addr = f"{adapter.config_obj.resource_host}:{adapter.config_obj.resource_port}"

            streaming_status = (
                "已启用"
                if getattr(adapter.config_obj, "enable_streaming", False)
                else "未启用"
            )
            tts_status = (
                "已启用"
                if getattr(adapter.config_obj, "enable_tts", False)
                else "未启用"
            )

            status_msg = f"""[Live2D Adapter] 适配器状态

连接信息:
  - 当前连接数: {client_count}/{max_connections}
  - 当前客户端: {current_client or "无"}
{resource_info}{temp_info}

服务器状态:
  - WebSocket: {ws_status} ({ws_addr})
  - 资源服务器: {resource_server_status} {f"({resource_addr})" if resource_addr else ""}
  - 流式消息: {streaming_status}
  - TTS: {tts_status}"""

            return MessageChain().message(status_msg)

        except Exception as e:
            logger.exception(f"获取状态失败: {e}")
            return MessageChain().message(f"[Live2D Adapter] 错误: 获取状态失败 - {e}")

    async def _cmd_info(self, adapter: Live2DPlatformAdapter) -> MessageChain:
        """显示详细信息"""
        try:
            if not adapter.current_client_id:
                return MessageChain().message("[Live2D Adapter] 当前没有连接的客户端")

            client_id = adapter.current_client_id
            ws_server = adapter.ws_server

            # 获取客户端信息
            if ws_server and hasattr(ws_server, "handler"):
                client_info = ws_server.handler.client_states.get(client_id, {})
            else:
                client_info = {}
            model_info = client_info.get("model", {})
            session_info = client_info.get("session", {})

            model_name = model_info.get("name", "未知")
            motion_groups = model_info.get("motionGroups", {})
            expressions = model_info.get("expressions", [])

            # 计算连接时长
            connect_time = session_info.get("connect_time")
            if connect_time:
                duration = int(time.time() - connect_time)
                duration_str = self._format_duration(duration)
            else:
                duration_str = "未知"

            # 动作组信息
            motion_info = ""
            if motion_groups:
                total_motions = sum(len(motions) for motions in motion_groups.values())
                motion_info = (
                    f"\n  - 动作组: {len(motion_groups)} 组，共 {total_motions} 个动作"
                )

            # 表情信息
            expression_info = ""
            if expressions:
                expression_info = f"\n  - 表情: {len(expressions)} 个"

            info_msg = f"""[Live2D Adapter] 客户端详细信息

客户端 ID: {client_id}
模型名称: {model_name}
连接时长: {duration_str}{motion_info}{expression_info}

提示: 使用 /live2d.test_motion <组名> 测试动作
      使用 /live2d.test_expression <表情ID> 测试表情"""

            return MessageChain().message(info_msg)

        except Exception as e:
            logger.exception(f"获取详细信息失败: {e}")
            return MessageChain().message(
                f"[Live2D Adapter] 错误: 获取详细信息失败 - {e}"
            )

    async def _cmd_list(self, adapter: Live2DPlatformAdapter) -> MessageChain:
        """列出所有连接的客户端"""
        try:
            ws_server = adapter.ws_server
            if not ws_server or not ws_server.clients:
                return MessageChain().message("[Live2D Adapter] 当前没有连接的客户端")

            client_list = []
            for client_id in ws_server.clients.keys():
                client_info = ws_server.handler.client_states.get(client_id, {})
                model_info = client_info.get("model", {})
                model_name = model_info.get("name", "未知")

                is_current = (
                    "[当前]" if client_id == adapter.current_client_id else "      "
                )
                client_list.append(f"{is_current} {client_id[:8]}... - {model_name}")

            list_msg = f"""[Live2D Adapter] 连接的客户端列表 ({len(client_list)})

""" + "\n".join(client_list)

            return MessageChain().message(list_msg)

        except Exception as e:
            logger.exception(f"获取客户端列表失败: {e}")
            return MessageChain().message(
                f"[Live2D Adapter] 错误: 获取客户端列表失败 - {e}"
            )

    async def _cmd_resources(self, adapter: Live2DPlatformAdapter) -> MessageChain:
        """显示资源信息"""
        try:
            if not adapter.resource_manager:
                return MessageChain().message("[Live2D Adapter] 资源管理器未启用")

            rm = adapter.resource_manager
            resources = rm.resources

            if not resources:
                return MessageChain().message("[Live2D Adapter] 当前没有存储的资源")

            # 按类型统计
            type_stats = {}
            total_size = 0
            for resource in resources.values():
                kind = resource.kind
                type_stats[kind] = type_stats.get(kind, 0) + 1
                total_size += resource.size

            stats_lines = [
                f"  - {kind}: {count} 个" for kind, count in type_stats.items()
            ]

            resource_msg = (
                f"""[Live2D Adapter] 资源统计

总计: {len(resources)} 个文件，{self._format_bytes(total_size)}

按类型:
"""
                + "\n".join(stats_lines)
                + f"""

配额: {len(resources)}/{rm.max_total_files or 0} 文件
      {self._format_bytes(total_size)}/{self._format_bytes(rm.max_total_bytes or 0)} 空间"""
            )

            return MessageChain().message(resource_msg)

        except Exception as e:
            logger.exception(f"获取资源信息失败: {e}")
            return MessageChain().message(
                f"[Live2D Adapter] 错误: 获取资源信息失败 - {e}"
            )

    async def _cmd_cleanup(self, adapter: Live2DPlatformAdapter) -> MessageChain:
        """手动触发清理"""
        try:
            cleaned_resources = 0
            cleaned_temp = 0

            # 清理资源
            if adapter.resource_manager:
                before = len(adapter.resource_manager.resources)
                # ResourceManager 只有 cleanup 方法
                if hasattr(adapter.resource_manager, "cleanup"):
                    adapter.resource_manager.cleanup()  # type: ignore[attr-defined]
                after = len(adapter.resource_manager.resources)
                cleaned_resources = before - after

            # 清理临时文件
            if adapter.input_converter and hasattr(
                adapter.input_converter, "get_temp_files_info"
            ):
                before_info = adapter.input_converter.get_temp_files_info()
                adapter.input_converter.cleanup_temp_files()
                after_info = adapter.input_converter.get_temp_files_info()
                cleaned_temp = before_info["count"] - after_info["count"]

            cleanup_msg = f"""[Live2D Adapter] 清理完成

  - 清理资源文件: {cleaned_resources} 个
  - 清理临时文件: {cleaned_temp} 个"""

            return MessageChain().message(cleanup_msg)

        except Exception as e:
            logger.exception(f"清理失败: {e}")
            return MessageChain().message(f"[Live2D Adapter] 错误: 清理失败 - {e}")

    async def _cmd_config(self, adapter: Live2DPlatformAdapter) -> MessageChain:
        """显示当前配置"""
        try:
            config = adapter.config_obj

            config_msg = f"""[Live2D Adapter] 适配器配置

WebSocket:
  - 地址: {config.server_host}:{config.server_port}
  - 路径: {config.ws_path}
  - 认证: {"已启用" if config.auth_token else "未启用"}
  - 最大连接: {config.max_connections}

功能:
  - 流式消息: {"已启用" if getattr(config, "enable_streaming", False) else "未启用"}
  - TTS: {"已启用" if getattr(config, "enable_tts", False) else "未启用"}
  - 资源服务器: {"已启用" if config.resource_enabled else "未启用"}

资源管理:
  - 资源目录: {config.resource_dir}
  - 资源 TTL: {self._format_duration(getattr(config, "resource_ttl_seconds", 0))}
  - 最大文件: {getattr(config, "resource_max_files", 0)}
  - 最大空间: {self._format_bytes(getattr(config, "resource_max_total_bytes", 0))}

临时文件:
  - 临时目录: {getattr(config, "temp_dir", "未知")}
  - 临时 TTL: {self._format_duration(getattr(config, "temp_ttl_seconds", 0))}
  - 最大文件: {getattr(config, "temp_max_files", 0)}"""

            return MessageChain().message(config_msg)

        except Exception as e:
            logger.exception(f"获取配置失败: {e}")
            return MessageChain().message(f"[Live2D Adapter] 错误: 获取配置失败 - {e}")

    def _register_config(self):
        if self._registered:
            return False
        try:
            target_dict = CONFIG_METADATA_2["platform_group"]["metadata"]["platform"][
                "items"
            ]
            for name in list(self._live2d_items):
                if name not in target_dict:
                    target_dict[name] = self._live2d_items[name]
        except Exception as e:
            logger.error(f"[Live2D] 注册平台元数据时出现问题: {e}", exc_info=True)
            return False
        self._registered = True
        return True

    def _unregister_config(self):
        if not self._registered:
            return False
        try:
            target_dict = CONFIG_METADATA_2["platform_group"]["metadata"]["platform"][
                "items"
            ]
            for name in list(self._live2d_items):
                if name in target_dict:
                    target_dict.pop(name, None)
        except Exception as e:
            logger.error(f"[Live2D] 清理平台元数据时出现问题: {e}", exc_info=True)
            return False
        self._registered = False
        return True

    # ──────── 桌面感知 LLM 工具 ────────

    @filter.llm_tool(name="get_desktop_windows")
    async def tool_get_desktop_windows(self, event: AstrMessageEvent) -> str:
        """获取用户桌面上所有打开的窗口列表，包含窗口标题、进程名、是否活跃等信息。
        当需要了解用户正在使用什么应用或做什么事情时调用此工具。

        """
        adapter = self._get_adapter()
        if not adapter or not adapter.current_client_id:
            return "错误：Live2D 客户端未连接"
        packet = Protocol.create_packet(Protocol.OP_DESKTOP_WINDOW_LIST)
        try:
            result = await adapter.desktop_request_mgr.request(
                adapter.ws_server, adapter.current_client_id, packet
            )
        except asyncio.TimeoutError:
            return "错误：获取窗口列表超时，桌面端未响应"
        windows = result.get("windows", [])
        if not windows:
            return "未检测到打开的窗口"
        lines = []
        for w in windows:
            active = " [活跃]" if w.get("isActive") else ""
            lines.append(
                f"- {w.get('title', '未知')} ({w.get('processName', '未知')}){active} [ID:{w.get('id', '')}]"
            )
        return "当前桌面窗口列表：\n" + "\n".join(lines)

    @filter.llm_tool(name="get_active_window")
    async def tool_get_active_window(self, event: AstrMessageEvent) -> str:
        """获取用户当前正在使用的活跃窗口信息（标题、进程名、窗口ID）。

        """
        adapter = self._get_adapter()
        if not adapter or not adapter.current_client_id:
            return "错误：Live2D 客户端未连接"
        packet = Protocol.create_packet(Protocol.OP_DESKTOP_WINDOW_ACTIVE)
        try:
            result = await adapter.desktop_request_mgr.request(
                adapter.ws_server, adapter.current_client_id, packet
            )
        except asyncio.TimeoutError:
            return "错误：获取活跃窗口超时，桌面端未响应"
        window = result.get("window")
        if not window:
            return "未检测到活跃窗口"
        return (
            f"当前活跃窗口：{window.get('title', '未知')}\n"
            f"进程：{window.get('processName', '未知')}\n"
            f"窗口ID：{window.get('id', '')}"
        )

    @filter.llm_tool(name="capture_screenshot")
    async def tool_capture_screenshot(
        self,
        event: AstrMessageEvent,
        target: str = "active",
        window_id: str = "",
    ) -> str:
        """截取用户桌面或特定窗口的屏幕截图。截图将作为图片附加到上下文供你分析。
        当需要查看用户屏幕内容、帮助用户解决问题、或对用户正在看的内容进行评论时调用。

        Args:
            target(string): 截图目标。"desktop"（全屏）、"active"（当前活跃窗口）、"window"（指定窗口）
            window_id(string): 当 target 为 "window" 时必填，窗口 ID（通过 get_desktop_windows 获取）

        """
        adapter = self._get_adapter()
        if not adapter or not adapter.current_client_id:
            return "错误：Live2D 客户端未连接"
        payload = {"target": target, "format": "jpeg", "quality": 80, "maxWidth": 1920}
        if target == "window" and window_id:
            payload["windowId"] = window_id
        packet = Protocol.create_packet(
            Protocol.OP_DESKTOP_CAPTURE_SCREENSHOT, payload
        )
        try:
            result = await adapter.desktop_request_mgr.request(
                adapter.ws_server, adapter.current_client_id, packet, timeout=30.0
            )
        except asyncio.TimeoutError:
            return "错误：截图超时，桌面端未响应"
        image_data = result.get("image", "")
        if not image_data:
            return "截图失败：未收到图像数据"
        if image_data.startswith(("http://", "https://")):
            image_comp = adapter.input_converter.convert_image({"url": image_data})
        else:
            image_comp = adapter.input_converter.convert_image({"data": image_data})
        if image_comp:
            event.message_obj.message.append(image_comp)
        window_info = result.get("window", {})
        title = window_info.get("title", "未知")
        return f"已截取屏幕截图（来源：{title}），图片已附加到上下文中，请分析图片内容。"

    async def initialize(self):
        self._register_config()

    async def terminate(self):
        self._unregister_config()


__all__ = ["Live2DAdapter", "Live2DPlatformAdapter"]
