"""输出消息转换器 - 将 AstrBot 的 MessageChain 转换为 Live2D 表演序列"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from astrbot.api.event import MessageChain as MessageChainType
else:
    MessageChainType = Any

try:
    from astrbot.api.message_components import (
        At,
        AtAll,
        Face,
        File,
        Forward,
        Image,
        Json,
        Node,
        Nodes,
        Plain,
        Poke,
        Record,
        Reply,
        Video,
        WechatEmoji,
    )
except ImportError:
    (
        At,
        AtAll,
        Face,
        File,
        Forward,
        Image,
        Json,
        Node,
        Nodes,
        Plain,
        Poke,
        Record,
        Reply,
        Video,
        WechatEmoji,
    ) = (None,) * 15

from ..core.protocol import (
    create_expression_element,
    create_image_element,
    create_motion_element,
    create_text_element,
    create_tts_element,
    create_video_element,
)


class OutputMessageConverter:
    """输出消息转换器 - 将 AstrBot 的 MessageChain 转换为 Live2D 表演序列"""

    def __init__(
        self,
        enable_auto_emotion: bool = False,
        enable_tts: bool = True,
        tts_mode: str = "remote",
        resource_manager: Any | None = None,
        resource_config: dict[str, Any] | None = None,
    ):
        """
        初始化转换器

        Args:
            enable_auto_emotion: 已弃用，保留仅为兼容性
            enable_tts: 是否启用 TTS
            tts_mode: TTS 模式 (remote/local)
            resource_manager: 资源管理器（处理本地文件转资源）
            resource_config: 资源配置（inline 限制等）
        """
        self.enable_auto_emotion = enable_auto_emotion  # 保留以兼容旧代码
        self.enable_tts = enable_tts
        self.tts_mode = tts_mode
        self.resource_manager = resource_manager
        self.resource_config = resource_config or {}

    def convert(
        self, message_chain: MessageChainType, tts_url: str | None = None
    ) -> list[dict[str, Any]]:
        """
        转换 MessageChain 为表演序列

        Args:
            message_chain: AstrBot 消息链
            tts_url: TTS 音频 URL（如果已生成）

        Returns:
            表演序列数组
        """
        if not message_chain or not message_chain.chain:
            return []

        sequence = []
        full_text = ""

        for component in message_chain.chain:
            if Plain and isinstance(component, Plain):
                text = component.text
                full_text += text

                # 添加文字气泡
                sequence.append(
                    create_text_element(
                        content=text,
                        duration=0,  # 0 表示持续显示
                        position="center",
                    )
                )

                # 如果启用了 TTS 且提供了 TTS URL
                if self.enable_tts and tts_url:
                    tts_element = self._build_tts_element(text=text, url=tts_url)
                    if tts_element:
                        sequence.append(tts_element)
                elif self.enable_tts and self.tts_mode == "local":
                    sequence.append(
                        create_tts_element(
                            text=text, tts_mode="local", voice="zh-CN-XiaoxiaoNeural"
                        )
                    )

            elif Image and isinstance(component, Image):
                # 添加图片展示
                image_element = self._build_image_element(component)
                if image_element:
                    sequence.append(image_element)

            elif Record and isinstance(component, Record):
                # 音频直接作为 TTS 播放
                audio_element = self._build_audio_element(component)
                if audio_element:
                    sequence.append(audio_element)

            elif Video and isinstance(component, Video):
                video_element = self._build_video_element(component)
                if video_element:
                    sequence.append(video_element)
                    full_text += "[视频]"

            elif File and isinstance(component, File):
                file_element = self._build_file_text_element(component)
                if file_element:
                    sequence.append(file_element)
                    file_name = getattr(component, "name", "") or "file"
                    full_text += f"[文件:{file_name}]"

            # 自定义 Live2D 组件支持：Live2DMotion 和 Live2DExpression
            elif hasattr(component, "type"):
                if component.type == "live2d_motion":
                    # 支持通过自定义组件下发动作
                    motion_elem = self._build_motion_from_component(component)
                    if motion_elem:
                        sequence.append(motion_elem)
                elif component.type == "live2d_expression":
                    # 支持通过自定义组件下发表情
                    expression_elem = self._build_expression_from_component(component)
                    if expression_elem:
                        sequence.append(expression_elem)
                else:
                    # 其他组件转为文本
                    fallback_text = self._format_component_text(component)
                    if fallback_text:
                        full_text += fallback_text
                        sequence.append(
                            create_text_element(
                                content=fallback_text,
                                duration=0,
                                position="center",
                            )
                        )

        return sequence

    def _build_motion_from_component(self, component: Any) -> dict[str, Any] | None:
        """从自定义 Live2DMotion 组件构建动作元素

        组件属性:
            - group: str - 动作组名
            - index: int - 动作索引（默认 0）
            - priority: int - 优先级（默认 2）
            - loop: bool - 是否循环（默认 False）
            - fade_in: int - 淡入时间ms（默认 300）
            - fade_out: int - 淡出时间ms（默认 300）
            - motion_type: str - 动作类型（可选，如 happy, sad）
        """
        group = getattr(component, "group", None)
        if not group:
            return None

        motion_elem = create_motion_element(
            group=group,
            index=getattr(component, "index", 0),
            priority=getattr(component, "priority", 2),
            loop=getattr(component, "loop", False),
            fade_in=getattr(component, "fade_in", 300),
            fade_out=getattr(component, "fade_out", 300),
        )

        # 支持 motionType（由其他模块提供）
        motion_type = getattr(component, "motion_type", None)
        if motion_type:
            motion_elem["motionType"] = motion_type

        return motion_elem

    def _build_expression_from_component(self, component: Any) -> dict[str, Any] | None:
        """从自定义 Live2DExpression 组件构建表情元素

        组件属性:
            - expression_id: str - 表情ID
            - fade: int - 淡入淡出时间ms（默认 300）
            - motion_type: str - 动作类型（可选）
        """
        expression_id = getattr(component, "expression_id", None) or getattr(component, "id", None)
        if expression_id is None:
            return None

        expression_elem = create_expression_element(
            expression_id=expression_id,
            fade=getattr(component, "fade", 300),
        )

        # 支持 motionType
        motion_type = getattr(component, "motion_type", None)
        if motion_type:
            expression_elem["motionType"] = motion_type

        return expression_elem

    def _get_image_url(self, image: Any) -> str | None:
        """获取图片 URL"""
        if hasattr(image, "file"):
            file_path = image.file
            if file_path.startswith("http://") or file_path.startswith("https://"):
                return file_path
            if file_path.startswith("file://"):
                local_path = file_path.replace("file:///", "", 1)
                return local_path
            elif os.path.isfile(file_path):
                return file_path
        return None

    def _get_audio_url(self, record: Any) -> str | None:
        """获取音频 URL"""
        if hasattr(record, "file"):
            file_path = record.file
            if file_path.startswith("http://") or file_path.startswith("https://"):
                return file_path
            if file_path.startswith("file://"):
                local_path = file_path.replace("file:///", "", 1)
                return local_path
            elif os.path.isfile(file_path):
                return file_path
        return None

    def _get_video_url(self, video: Any) -> str | None:
        """获取视频 URL"""
        if hasattr(video, "file"):
            file_path = video.file
            if file_path.startswith("http://") or file_path.startswith("https://"):
                return file_path
            if file_path.startswith("file://"):
                local_path = file_path.replace("file:///", "", 1)
                return local_path
            if os.path.isfile(file_path):
                return file_path
        return None

    def _build_resource_element(
        self, file_path: str, kind: str
    ) -> dict[str, Any] | None:
        if not file_path:
            return None
        if file_path.startswith("http://") or file_path.startswith("https://"):
            return {"url": file_path}
        if not os.path.isfile(file_path):
            return None
        if not self.resource_manager:
            file_url = (
                f"file:///{file_path}" if os.name == "nt" else f"file://{file_path}"
            )
            return {"url": file_url}
        try:
            return self.resource_manager.build_reference_from_file(file_path, kind)
        except Exception:
            file_url = (
                f"file:///{file_path}" if os.name == "nt" else f"file://{file_path}"
            )
            return {"url": file_url}

    def _build_image_element(self, image: Any) -> dict[str, Any] | None:
        image_path = self._get_image_url(image)
        resource_ref = (
            self._build_resource_element(image_path, "image") if image_path else None
        )
        if not resource_ref:
            return None
        return create_image_element(
            url=resource_ref.get("url"),
            rid=resource_ref.get("rid"),
            inline=resource_ref.get("inline"),
            duration=5000,
            position="center",
        )

    def _build_audio_element(self, record: Any) -> dict[str, Any] | None:
        audio_path = self._get_audio_url(record)
        resource_ref = (
            self._build_resource_element(audio_path, "audio") if audio_path else None
        )
        if not resource_ref:
            return None
        return create_tts_element(
            text="",
            url=resource_ref.get("url"),
            rid=resource_ref.get("rid"),
            inline=resource_ref.get("inline"),
            tts_mode="remote",
        )

    def _build_video_element(self, video: Any) -> dict[str, Any] | None:
        video_path = self._get_video_url(video)
        resource_ref = (
            self._build_resource_element(video_path, "video") if video_path else None
        )
        if not resource_ref:
            return None
        return create_video_element(
            url=resource_ref.get("url"),
            rid=resource_ref.get("rid"),
            inline=resource_ref.get("inline"),
            duration=0,
            position="center",
            autoplay=True,
            loop=False,
        )

    def _build_file_text_element(self, file: Any) -> dict[str, Any] | None:
        name = getattr(file, "name", "") or "file"
        file_path = getattr(file, "file_", "") or ""
        file_url = getattr(file, "url", "") or ""

        source = file_url or file_path
        if not source:
            return create_text_element(
                content=f"[file] {name}", duration=0, position="center"
            )

        ref = self._build_resource_element(source, "file")
        if not ref:
            return create_text_element(
                content=f"[file] {name}", duration=0, position="center"
            )

        if ref.get("url"):
            return create_text_element(
                content=f"[file] {name}: {ref.get('url')}",
                duration=0,
                position="center",
            )
        if ref.get("rid"):
            return create_text_element(
                content=f"[file] {name}: rid={ref.get('rid')}",
                duration=0,
                position="center",
            )
        return create_text_element(
            content=f"[file] {name}", duration=0, position="center"
        )

    def _build_tts_element(self, text: str, url: str) -> dict[str, Any] | None:
        resource_ref = self._build_resource_element(url, "audio")
        if not resource_ref:
            return None
        return create_tts_element(
            text=text,
            url=resource_ref.get("url"),
            rid=resource_ref.get("rid"),
            inline=resource_ref.get("inline"),
            tts_mode="remote",
        )

    def _format_component_text(self, component: Any) -> str | None:
        if AtAll and isinstance(component, AtAll):
            return "@all"
        if At and isinstance(component, At):
            name = component.name or str(component.qq)
            return f"@{name}"
        if Reply and isinstance(component, Reply):
            if component.message_str:
                return f"[reply] {component.message_str}"
            if component.text:
                return f"[reply] {component.text}"
            return "[reply]"
        if Face and isinstance(component, Face):
            face_id = getattr(component, "id", "")
            return f"[face:{face_id}]" if face_id else "[face]"
        if Poke and isinstance(component, Poke):
            return "[poke]"
        if File and isinstance(component, File):
            name = getattr(component, "name", "") or "file"
            return f"[file] {name}"
        if Video and isinstance(component, Video):
            return "[video]"
        if Forward and isinstance(component, Forward):
            return "[forward]"
        if Node and isinstance(component, Node):
            return "[forward]"
        if Nodes and isinstance(component, Nodes):
            return "[forward]"
        if Json and isinstance(component, Json):
            return "[json]"
        if WechatEmoji and isinstance(component, WechatEmoji):
            return "[emoji]"
        if hasattr(component, "type"):
            return f"[{component.type}]"
        return None

    def convert_streaming(self, text_chunk: str) -> list[dict[str, Any]]:
        """
        转换流式文本为简单的表演序列（用于伪流式输出）

        Args:
            text_chunk: 文本片段

        Returns:
            表演序列数组
        """
        if not text_chunk:
            return []

        return [create_text_element(content=text_chunk, duration=0, position="center")]
