"""桌面感知请求-响应管理器"""

import asyncio
from typing import Any

from astrbot.api import logger

from .protocol import BasePacket


class DesktopRequestManager:
    """管理发送到桌面端的请求-响应，通过 asyncio.Future 实现异步等待"""

    def __init__(self):
        self._pending: dict[str, asyncio.Future] = {}

    def resolve(self, packet_id: str, payload: dict | None, error=None) -> bool:
        future = self._pending.pop(packet_id, None)
        if future and not future.done():
            if error:
                msg = getattr(error, "message", str(error))
                future.set_exception(RuntimeError(f"桌面端返回错误: {msg}"))
            else:
                future.set_result(payload or {})
            return True
        return False

    async def request(
        self,
        ws_server: Any,
        client_id: str,
        packet: BasePacket,
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict] = loop.create_future()
        self._pending[packet.id] = future
        try:
            await ws_server.send_to(client_id, packet)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(packet.id, None)
            logger.warning(f"[Desktop] 请求超时: op={packet.op} id={packet.id}")
            raise
        except Exception:
            self._pending.pop(packet.id, None)
            raise
