"""输入消息转换器 - 将 Live2D 客户端的消息转换为 AstrBot 消息对象"""

import base64
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

try:
    from astrbot.api import logger
    from astrbot.api.message_components import File, Image, Plain, Record, Video
except ImportError:
    logger = None
    Plain = Image = Record = File = Video = None


class InputMessageConverter:
    """输入消息转换器 - 将 Live2D 客户端的消息转换为 AstrBot 消息对象"""

    _TEMP_FILE_PREFIXES = (
        "live2d_img_",
        "live2d_voice_",
        "live2d_file_",
        "live2d_video_",
    )

    def __init__(
        self,
        temp_dir: str | None = None,
        *,
        temp_ttl_seconds: int | None = None,
        temp_max_total_bytes: int | None = None,
        temp_max_files: int | None = None,
        resource_manager: Any | None = None,
    ):
        """
        初始化转换器

        Args:
            temp_dir: 临时文件目录，用于存储 Base64 图片
            temp_ttl_seconds: Temporary file TTL in seconds. Set to 0/None to disable.
            temp_max_total_bytes: Total temp size quota in bytes. Set to 0/None to disable.
            temp_max_files: Max number of temp files. Set to 0/None to disable.
            resource_manager: 资源管理器（处理 rid 引用）
        """
        self.temp_dir = temp_dir or tempfile.gettempdir()
        Path(self.temp_dir).mkdir(parents=True, exist_ok=True)
        self.temp_ttl_seconds = int(temp_ttl_seconds or 0) or None
        self.temp_max_total_bytes = int(temp_max_total_bytes or 0) or None
        self.temp_max_files = int(temp_max_files or 0) or None
        self.resource_manager = resource_manager

    def get_temp_files_info(self) -> dict:
        """获取临时文件信息

        Returns:
            包含临时文件数量和总字节数的字典
        """
        return {
            'count': len(self._temp_files),
            'total_bytes': sum(self._temp_files.values())
        }

    def convert(self, content: list[dict[str, Any]]) -> tuple[list, str]:
        """
        转换输入消息

        Args:
            content: input.message 的 content 数组

        Returns:
            (消息组件列表, 纯文本字符串)
        """
        message_components = []
        text_parts = []

        for item in content:
            item_type = item.get("type")

            if item_type == "text":
                text = item.get("text", "")
                if Plain:
                    message_components.append(Plain(text))
                text_parts.append(text)

            elif item_type == "image":
                image_comp = self._convert_image(item)
                if image_comp:
                    message_components.append(image_comp)
                    text_parts.append("[图片]")

            elif item_type in {"voice", "audio", "record"}:
                voice_comp, voice_text = self._convert_voice(item)
                if voice_comp:
                    message_components.append(voice_comp)
                if voice_text:
                    text_parts.append(voice_text)

            elif item_type == "video":
                video_comp, video_text = self._convert_video(item)
                if video_comp:
                    message_components.append(video_comp)
                if video_text:
                    text_parts.append(video_text)

            elif item_type == "file":
                file_comp, file_text = self._convert_file(item)
                if file_comp:
                    message_components.append(file_comp)
                if file_text:
                    text_parts.append(file_text)

        message_str = "".join(text_parts)
        return message_components, message_str

    def _set_component_url(self, comp: Any, url: str | None) -> Any:
        """Best-effort set component.url for AstrBot pipeline compatibility.

        AstrBot's STT stage expects `Record.url` to be populated.
        """
        if not comp or not url:
            return comp
        try:
            setattr(comp, "url", url)
        except Exception:
            # Some mock components in standalone mode may be immutable.
            pass
        return comp

    def cleanup_temp_files(
        self, *, reserve_bytes: int = 0, reserve_files: int = 0
    ) -> dict[str, int]:
        """Cleanup temp files created by this adapter.

        Reserve params are used when writing a new temp file, ensuring enough room
        after cleanup.
        """
        removed = 0
        removed_bytes = 0

        if (
            self.temp_max_total_bytes is not None
            and reserve_bytes > self.temp_max_total_bytes
        ):
            raise ValueError("Temp quota too small for the incoming payload.")
        if self.temp_max_files is not None and reserve_files > self.temp_max_files:
            raise ValueError("Temp file quota too small for the incoming payload.")

        temp_root = Path(self.temp_dir)
        if not temp_root.exists():
            return {"removed": 0, "removed_bytes": 0}

        def is_owned(p: Path) -> bool:
            name = p.name
            return any(name.startswith(prefix) for prefix in self._TEMP_FILE_PREFIXES)

        files: list[Path] = []
        for p in temp_root.iterdir():
            if not p.is_file():
                continue
            if is_owned(p):
                files.append(p)

        # TTL cleanup (based on mtime)
        if self.temp_ttl_seconds:
            now = time.time()
            for p in list(files):
                try:
                    mtime = p.stat().st_mtime
                    if (now - mtime) > self.temp_ttl_seconds:
                        size = p.stat().st_size
                        p.unlink(missing_ok=True)
                        removed += 1
                        removed_bytes += size
                        files.remove(p)
                except OSError:
                    continue

        # Quota cleanup
        max_files = (
            max(self.temp_max_files - reserve_files, 0)
            if self.temp_max_files is not None
            else None
        )
        max_bytes = (
            max(self.temp_max_total_bytes - reserve_bytes, 0)
            if self.temp_max_total_bytes is not None
            else None
        )

        def safe_mtime(p: Path) -> float:
            try:
                return p.stat().st_mtime
            except OSError:
                return 0.0

        files.sort(key=safe_mtime)

        def total_bytes() -> int:
            total = 0
            for p in files:
                try:
                    total += p.stat().st_size
                except OSError:
                    continue
            return total

        if max_files is not None:
            while len(files) > max_files:
                p = files.pop(0)
                try:
                    size = p.stat().st_size
                    p.unlink(missing_ok=True)
                    removed += 1
                    removed_bytes += size
                except OSError:
                    continue

        if max_bytes is not None:
            while files and total_bytes() > max_bytes:
                p = files.pop(0)
                try:
                    size = p.stat().st_size
                    p.unlink(missing_ok=True)
                    removed += 1
                    removed_bytes += size
                except OSError:
                    continue

        return {"removed": removed, "removed_bytes": removed_bytes}

    def _convert_image(self, item: dict[str, Any]) -> Any | None:
        """转换图片消息"""
        if not Image:
            return None

        url = item.get("url")
        data = item.get("data")
        inline = item.get("inline")
        rid = item.get("rid")

        if inline and not data:
            data = inline

        if rid and self.resource_manager:
            resource_path = self.resource_manager.get_resource_path(rid)
            if resource_path and resource_path.exists():
                img = Image.fromFileSystem(str(resource_path))
                return self._set_component_url(img, str(resource_path))
            resource_payload = self.resource_manager.get_resource_payload(rid)
            if resource_payload and resource_payload.get("url"):
                img = Image.fromURL(resource_payload["url"])
                return self._set_component_url(img, resource_payload["url"])

        if data and data.startswith("data:image/"):
            # Base64 图片
            try:
                # 解析 data URI
                match = re.match(r"data:image/(\w+);base64,(.+)", data)
                if match:
                    image_format, base64_data = match.groups()
                    image_bytes = base64.b64decode(base64_data)

                    try:
                        self.cleanup_temp_files(
                            reserve_bytes=len(image_bytes),
                            reserve_files=1,
                        )
                    except Exception as e:
                        logger.error(f"清理临时文件失败: {e}")
                        return None

                    # 保存到临时文件
                    temp_file = os.path.join(
                        self.temp_dir,
                        f"live2d_img_{os.urandom(8).hex()}.{image_format}",
                    )
                    with open(temp_file, "wb") as f:
                        f.write(image_bytes)

                    img = Image.fromFileSystem(temp_file)
                    return self._set_component_url(img, os.path.abspath(temp_file))
            except Exception as e:
                logger.error(f"解析 Base64 图片失败: {e}")
                return None

        elif url:
            # URL 图片
            if url.startswith("http://") or url.startswith("https://"):
                img = Image.fromURL(url)
                return self._set_component_url(img, url)
            elif url.startswith("file:///"):
                local_path = url[8:] if os.name == "nt" else url[7:]
                img = Image.fromFileSystem(local_path)
                return self._set_component_url(img, os.path.abspath(local_path))

        return None

    def _convert_voice(self, item: dict[str, Any]) -> tuple[Any | None, str | None]:
        """转换语音消息，返回 (组件, 文本)"""
        stt_mode = item.get("sttMode", "remote")

        if stt_mode == "local":
            # 本地 STT，直接使用文本
            text = item.get("text", "")
            if Plain:
                return Plain(text), text
            return None, text

        # 远程 STT，返回音频文件路径（由 AstrBot STT 插件处理）
        url = item.get("url")
        data = item.get("data")
        inline = item.get("inline")
        rid = item.get("rid")

        if inline and not data:
            data = inline

        if rid and self.resource_manager and Record:
            resource_path = self.resource_manager.get_resource_path(rid)
            if resource_path and resource_path.exists():
                rec = Record.fromFileSystem(str(resource_path))
                rec = self._set_component_url(rec, str(resource_path))
                return rec, "[语音]"
            resource_payload = self.resource_manager.get_resource_payload(rid)
            if resource_payload and resource_payload.get("url"):
                rec = Record.fromURL(resource_payload["url"])
                rec = self._set_component_url(rec, resource_payload["url"])
                return rec, "[语音]"

        # 优先处理 Base64 音频数据
        if data and Record:
            try:
                # 解析 data URI (格式: data:audio/webm;base64,... 或 data:audio/webm;codecs=opus;base64,...)
                match = re.match(r"data:audio/([^;,]+)(?:[^,]*)?;base64,(.+)", data)
                if match:
                    # 提取主要格式（去除 codecs 等参数）
                    audio_format_raw = match.group(1)
                    base64_data = match.group(2)

                    # 映射格式到文件扩展名
                    format_map = {
                        "webm": "webm",
                        "ogg": "ogg",
                        "opus": "opus",
                        "mp4": "m4a",
                        "mpeg": "mp3",
                        "wav": "wav",
                    }
                    audio_ext = format_map.get(
                        audio_format_raw.lower(), audio_format_raw.lower()
                    )

                    audio_bytes = base64.b64decode(base64_data)

                    try:
                        self.cleanup_temp_files(
                            reserve_bytes=len(audio_bytes),
                            reserve_files=1,
                        )
                    except Exception as e:
                        logger.error(f"清理临时文件失败: {e}")
                        return None, None

                    # 保存到临时文件
                    temp_file = os.path.join(
                        self.temp_dir,
                        f"live2d_voice_{os.urandom(8).hex()}.{audio_ext}",
                    )
                    with open(temp_file, "wb") as f:
                        f.write(audio_bytes)

                    if logger:
                        logger.debug(
                            f"已保存语音文件: {temp_file}, 格式: {audio_format_raw}"
                        )
                    rec = Record.fromFileSystem(temp_file)
                    rec = self._set_component_url(rec, os.path.abspath(temp_file))
                    return rec, "[语音]"
            except Exception as e:
                logger.error(f"解析 Base64 音频失败: {e}")

        # 降级处理 URL
        if url and Record:
            if url.startswith("file:///"):
                local_path = url[8:] if os.name == "nt" else url[7:]
                rec = Record.fromFileSystem(local_path)
                rec = self._set_component_url(rec, os.path.abspath(local_path))
                return rec, "[语音]"
            if url.startswith("http://") or url.startswith("https://"):
                rec = Record.fromURL(url)
                rec = self._set_component_url(rec, url)
                return rec, "[语音]"

        return None, None

    def _convert_file(self, item: dict[str, Any]) -> tuple[Any | None, str | None]:
        """转换文件消息，返回 (组件, 文本)"""
        if not File:
            return None, None

        name = item.get("name") or item.get("filename") or "file"
        url = item.get("url")
        data = item.get("data")
        inline = item.get("inline")
        rid = item.get("rid")
        mime = item.get("mime") or item.get("contentType") or "application/octet-stream"

        if inline and not data:
            data = inline

        if rid and self.resource_manager:
            resource_path = self.resource_manager.get_resource_path(rid)
            if resource_path and resource_path.exists():
                return File(name=str(name), file=str(resource_path)), f"[文件] {name}"
            resource_payload = self.resource_manager.get_resource_payload(rid)
            if resource_payload and resource_payload.get("url"):
                return (
                    File(name=str(name), url=str(resource_payload["url"])),
                    f"[文件] {name}",
                )

        if data and isinstance(data, str) and data.startswith("data:"):
            try:
                header, b64_data = data.split(",", 1)
                if ";base64" not in header:
                    return None, None
                file_bytes = base64.b64decode(b64_data)

                try:
                    self.cleanup_temp_files(
                        reserve_bytes=len(file_bytes),
                        reserve_files=1,
                    )
                except Exception as e:
                    logger.error(f"清理临时文件失败: {e}")
                    return None, None

                suffix = ""
                try:
                    import mimetypes

                    suffix = mimetypes.guess_extension(mime) or ""
                except Exception:
                    suffix = ""

                temp_file = os.path.join(
                    self.temp_dir,
                    f"live2d_file_{os.urandom(8).hex()}{suffix}",
                )
                with open(temp_file, "wb") as f:
                    f.write(file_bytes)

                return (
                    File(name=str(name), file=os.path.abspath(temp_file)),
                    f"[文件] {name}",
                )
            except Exception as e:
                logger.error(f"解析 Base64 文件失败: {e}")
                return None, None

        if url:
            if url.startswith("file:///"):
                local_path = url[8:] if os.name == "nt" else url[7:]
                return File(
                    name=str(name), file=os.path.abspath(local_path)
                ), f"[文件] {name}"
            if url.startswith("http://") or url.startswith("https://"):
                return File(name=str(name), url=url), f"[文件] {name}"

        return None, None

    def _convert_video(self, item: dict[str, Any]) -> tuple[Any | None, str | None]:
        """转换视频消息，返回 (组件, 文本)"""
        if not Video:
            return None, None

        url = item.get("url")
        data = item.get("data")
        inline = item.get("inline")
        rid = item.get("rid")

        if inline and not data:
            data = inline

        if rid and self.resource_manager:
            resource_path = self.resource_manager.get_resource_path(rid)
            if resource_path and resource_path.exists():
                return (
                    Video.fromFileSystem(str(resource_path)),
                    "[视频]",
                )
            resource_payload = self.resource_manager.get_resource_payload(rid)
            if resource_payload and resource_payload.get("url"):
                return Video.fromURL(str(resource_payload["url"])), "[视频]"

        if data and isinstance(data, str) and data.startswith("data:video/"):
            try:
                match = re.match(r"data:video/([^;,]+)(?:[^,]*)?;base64,(.+)", data)
                if match:
                    video_format_raw = match.group(1)
                    base64_data = match.group(2)

                    format_map = {
                        "mp4": "mp4",
                        "webm": "webm",
                        "ogg": "ogv",
                        "quicktime": "mov",
                    }
                    video_ext = format_map.get(
                        video_format_raw.lower(), video_format_raw.lower()
                    )

                    video_bytes = base64.b64decode(base64_data)
                    try:
                        self.cleanup_temp_files(
                            reserve_bytes=len(video_bytes),
                            reserve_files=1,
                        )
                    except Exception as e:
                        logger.error(f"清理临时文件失败: {e}")
                        return None, None
                    temp_file = os.path.join(
                        self.temp_dir,
                        f"live2d_video_{os.urandom(8).hex()}.{video_ext}",
                    )
                    with open(temp_file, "wb") as f:
                        f.write(video_bytes)
                    return Video.fromFileSystem(temp_file), "[视频]"
            except Exception as e:
                logger.error(f"解析 Base64 视频失败: {e}")
                return None, None

        if url:
            if url.startswith("file:///"):
                local_path = url[8:] if os.name == "nt" else url[7:]
                return Video.fromFileSystem(os.path.abspath(local_path)), "[视频]"
            if url.startswith("http://") or url.startswith("https://"):
                return Video.fromURL(url), "[视频]"

        return None, None
