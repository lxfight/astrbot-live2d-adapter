"""L2D-Bridge Protocol v1.0 协议定义"""

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ErrorInfo",
    "BasePacket",
    "Protocol",
    "create_text_element",
    "create_tts_element",
    "create_image_element",
    "create_video_element",
    "create_motion_element",
    "create_expression_element",
    "create_wait_element",
]


@dataclass
class ErrorInfo:
    """错误信息"""

    code: int
    message: str


@dataclass
class BasePacket:
    """基础数据包结构"""

    op: str
    id: str
    ts: int
    payload: dict[str, Any] | None = None
    error: ErrorInfo | None = None

    @staticmethod
    def generate_id() -> str:
        """生成UUID"""
        return str(uuid.uuid4())

    @staticmethod
    def current_timestamp() -> int:
        """获取当前时间戳(毫秒)"""
        return int(time.time() * 1000)

    def to_json(self) -> str:
        """转换为JSON字符串"""
        data = {"op": self.op, "id": self.id, "ts": self.ts}
        if self.payload is not None:
            data["payload"] = self.payload
        if self.error is not None:
            data["error"] = {"code": self.error.code, "message": self.error.message}
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "BasePacket":
        """从JSON字符串解析"""
        data = json.loads(json_str)
        error = None
        if "error" in data:
            error = ErrorInfo(**data["error"])
        return cls(
            op=data["op"],
            id=data["id"],
            ts=data["ts"],
            payload=data.get("payload"),
            error=error,
        )


class Protocol:
    """协议辅助类 - L2D-Bridge Protocol v1.0"""

    # 系统级指令
    OP_HANDSHAKE = "sys.handshake"
    OP_HANDSHAKE_ACK = "sys.handshake_ack"
    OP_PING = "sys.ping"
    OP_PONG = "sys.pong"
    OP_ERROR = "sys.error"

    # 用户输入指令
    OP_INPUT_MESSAGE = "input.message"
    OP_INPUT_TOUCH = "input.touch"
    OP_INPUT_SHORTCUT = "input.shortcut"

    # 表演控制指令
    OP_PERFORM_SHOW = "perform.show"
    OP_PERFORM_INTERRUPT = "perform.interrupt"

    # 状态同步指令
    OP_STATE_READY = "state.ready"
    OP_STATE_PLAYING = "state.playing"
    OP_STATE_CONFIG = "state.config"
    OP_RESOURCE_PREPARE = "resource.prepare"
    OP_RESOURCE_COMMIT = "resource.commit"
    OP_RESOURCE_GET = "resource.get"
    OP_RESOURCE_RELEASE = "resource.release"
    OP_RESOURCE_PROGRESS = "resource.progress"

    # 模型控制指令
    OP_MODEL_LIST = "model.list"
    OP_MODEL_LOAD = "model.load"
    OP_MODEL_UNLOAD = "model.unload"
    OP_MODEL_STATE = "model.state"
    OP_MODEL_SET_EXPRESSION = "model.setExpression"
    OP_MODEL_PLAY_MOTION = "model.playMotion"
    OP_MODEL_SET_PARAMETER = "model.setParameter"
    OP_MODEL_LOOK_AT = "model.lookAt"
    OP_MODEL_SPEAK = "model.speak"
    OP_MODEL_STOP = "model.stop"

    # 桌面控制指令
    OP_DESKTOP_WINDOW_SHOW = "desktop.window.show"
    OP_DESKTOP_WINDOW_HIDE = "desktop.window.hide"
    OP_DESKTOP_WINDOW_MOVE = "desktop.window.move"
    OP_DESKTOP_WINDOW_RESIZE = "desktop.window.resize"
    OP_DESKTOP_WINDOW_SET_OPACITY = "desktop.window.setOpacity"
    OP_DESKTOP_WINDOW_SET_TOPMOST = "desktop.window.setTopmost"
    OP_DESKTOP_WINDOW_SET_CLICK_THROUGH = "desktop.window.setClickThrough"
    OP_DESKTOP_TRAY_NOTIFY = "desktop.tray.notify"
    OP_DESKTOP_OPEN_URL = "desktop.openUrl"
    OP_DESKTOP_CAPTURE_SCREENSHOT = "desktop.capture.screenshot"

    # 错误码 - 系统错误
    ERROR_AUTH_FAILED = 4001
    ERROR_VERSION_MISMATCH = 4002
    ERROR_INVALID_PAYLOAD = 4003
    ERROR_CONNECTION_FULL = 4004
    ERROR_SESSION_NOT_EXIST = 4005
    ERROR_RESOURCE_NOT_FOUND = 4006

    # 错误码 - 业务错误
    ERROR_TTS_FAILED = 5001
    ERROR_STT_FAILED = 5002
    ERROR_PERFORM_FAILED = 5003
    ERROR_UNSUPPORTED_TYPE = 5004
    ERROR_FILE_UPLOAD_FAILED = 5005
    ERROR_RESOURCE_IO = 5006

    @staticmethod
    def create_packet(
        op: str, payload: dict[str, Any] | None = None, packet_id: str | None = None
    ) -> BasePacket:
        """创建数据包"""
        return BasePacket(
            op=op,
            id=packet_id or BasePacket.generate_id(),
            ts=BasePacket.current_timestamp(),
            payload=payload,
        )

    @staticmethod
    def create_error_packet(
        code: int, message: str, packet_id: str | None = None
    ) -> BasePacket:
        """创建错误数据包"""
        return BasePacket(
            op=Protocol.OP_ERROR,
            id=packet_id or BasePacket.generate_id(),
            ts=BasePacket.current_timestamp(),
            error=ErrorInfo(code=code, message=message),
        )

    @staticmethod
    def create_handshake_ack(
        request_id: str,
        session_id: str,
        user_id: str,
        features: list[str] | None = None,
        capabilities: list[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> BasePacket:
        """创建握手确认包"""
        if features is None:
            features = ["message_chain", "tts_url", "multi_modal", "voice_input"]
        if capabilities is None:
            capabilities = [
                "input.message",
                "input.touch",
                "input.shortcut",
                "perform.show",
                "perform.interrupt",
                "resource.prepare",
                "resource.commit",
                "resource.get",
                "resource.release",
                "resource.progress",
                "state.ready",
                "state.playing",
                "state.config",
            ]
        if config is None:
            config = {
                "maxMessageLength": 5000,
                "supportedImageFormats": ["jpg", "png", "gif", "webp"],
                "supportedAudioFormats": ["mp3", "wav", "ogg"],
                "supportedVideoFormats": ["mp4", "webm", "mov"],
                "ttsProvider": "astrbot-tts",
                "sttProvider": "astrbot-stt",
            }

        return BasePacket(
            op=Protocol.OP_HANDSHAKE_ACK,
            id=request_id,
            ts=BasePacket.current_timestamp(),
            payload={
                "version": "1.0.0",
                "serverTime": BasePacket.current_timestamp(),
                "features": features,
                "capabilities": capabilities,
                "config": config,
                "session": {"sessionId": session_id, "userId": user_id},
            },
        )

    @staticmethod
    def create_perform_show(
        sequence: list[dict[str, Any]],
        interrupt: bool = True,
        packet_id: str | None = None,
    ) -> BasePacket:
        """创建表演序列指令 (perform.show)"""
        return Protocol.create_packet(
            Protocol.OP_PERFORM_SHOW,
            payload={"interrupt": interrupt, "sequence": sequence},
            packet_id=packet_id,
        )

    @staticmethod
    def create_perform_interrupt(packet_id: str | None = None) -> BasePacket:
        """创建中断表演指令"""
        return Protocol.create_packet(
            Protocol.OP_PERFORM_INTERRUPT, packet_id=packet_id
        )

    @staticmethod
    def create_state_ready(client_id: str, packet_id: str | None = None) -> BasePacket:
        """创建状态就绪事件"""
        return Protocol.create_packet(
            Protocol.OP_STATE_READY,
            payload={"clientId": client_id},
            packet_id=packet_id,
        )

    @staticmethod
    def create_state_playing(
        is_playing: bool, packet_id: str | None = None
    ) -> BasePacket:
        """创建播放状态事件"""
        return Protocol.create_packet(
            Protocol.OP_STATE_PLAYING,
            payload={"isPlaying": is_playing},
            packet_id=packet_id,
        )

    @staticmethod
    def create_state_config(
        payload: dict[str, Any], packet_id: str | None = None
    ) -> BasePacket:
        """创建配置状态事件"""
        return Protocol.create_packet(
            Protocol.OP_STATE_CONFIG, payload=payload, packet_id=packet_id
        )


# 表演元素构建辅助函数
def create_text_element(
    content: str,
    duration: int = 0,
    position: str = "center",
    style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """创建文字气泡元素"""
    element = {
        "type": "text",
        "content": content,
        "duration": duration,
        "position": position,
    }
    if style:
        element["style"] = style
    return element


def create_tts_element(
    text: str,
    url: str | None = None,
    rid: str | None = None,
    inline: str | None = None,
    tts_mode: str = "remote",
    voice: str | None = None,
    volume: float = 1.0,
    speed: float = 1.0,
) -> dict[str, Any]:
    """创建TTS语音元素"""
    element = {"type": "tts", "text": text, "volume": volume, "speed": speed}
    if url:
        element["url"] = url
        element["ttsMode"] = "remote"
    if rid:
        element["rid"] = rid
        element["ttsMode"] = "remote"
    if inline:
        element["inline"] = inline
        element["ttsMode"] = "remote"
    elif tts_mode == "local" and voice:
        element["ttsMode"] = "local"
        element["voice"] = voice
    return element


def create_image_element(
    url: str | None = None,
    duration: int = 5000,
    position: str = "center",
    size: dict[str, int] | None = None,
    rid: str | None = None,
    inline: str | None = None,
) -> dict[str, Any]:
    """创建图片展示元素"""
    element = {"type": "image", "duration": duration, "position": position}
    if url:
        element["url"] = url
    if rid:
        element["rid"] = rid
    if inline:
        element["inline"] = inline
    if size:
        element["size"] = size
    return element


def create_video_element(
    url: str | None = None,
    duration: int = 0,
    position: str = "center",
    size: dict[str, int] | None = None,
    rid: str | None = None,
    inline: str | None = None,
    autoplay: bool = True,
    loop: bool = False,
) -> dict[str, Any]:
    """创建视频元素"""
    element = {
        "type": "video",
        "duration": duration,
        "position": position,
        "autoplay": autoplay,
        "loop": loop,
    }
    if url:
        element["url"] = url
    if rid:
        element["rid"] = rid
    if inline:
        element["inline"] = inline
    if size:
        element["size"] = size
    return element


def create_motion_element(
    group: str,
    index: int = 0,
    priority: int = 2,
    loop: bool = False,
    fade_in: int = 300,
    fade_out: int = 300,
) -> dict[str, Any]:
    """创建动作元素"""
    return {
        "type": "motion",
        "group": group,
        "index": index,
        "priority": priority,
        "loop": loop,
        "fadeIn": fade_in,
        "fadeOut": fade_out,
    }


def create_expression_element(expression_id: str, fade: int = 300) -> dict[str, Any]:
    """创建表情元素"""
    return {"type": "expression", "id": expression_id, "fade": fade}


def create_wait_element(duration: int) -> dict[str, Any]:
    """创建等待元素"""
    return {"type": "wait", "duration": duration}
