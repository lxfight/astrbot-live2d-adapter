"""资源 HTTP 服务"""

from __future__ import annotations

import logging
from aiohttp import web

from .resource_manager import ResourceManager

logger = logging.getLogger(__name__)


class ResourceServer:
    """资源 HTTP 服务（用于上传/下载）"""

    def __init__(
        self,
        manager: ResourceManager,
        host: str,
        port: int,
        resource_path: str = "/resources",
        token: str | None = None,
    ):
        self.manager = manager
        self.host = host
        self.port = port
        self.resource_path = "/" + resource_path.strip("/")
        self.token = token or None
        self.app: web.Application | None = None
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None

    def _check_auth(self, request: web.Request) -> bool:
        if not self.token:
            return True
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            if header.removeprefix("Bearer ").strip() == self.token:
                return True
        if request.query.get("token") == self.token:
            return True
        return False

    async def handle_get(self, request: web.Request) -> web.StreamResponse:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized")
        rid = request.match_info.get("rid")
        entry = self.manager.get_resource(rid)
        if not entry or not entry.path or not entry.path.exists():
            return web.Response(status=404, text="Not Found")
        return web.FileResponse(entry.path)

    async def handle_put(self, request: web.Request) -> web.StreamResponse:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized")
        rid = request.match_info.get("rid")
        entry = self.manager.get_resource(rid)
        if not entry or not entry.path:
            return web.Response(status=404, text="Not Found")
        data = await request.read()
        entry.path.write_bytes(data)
        entry.size = len(data)
        entry.status = "ready"
        return web.json_response({"rid": rid, "size": entry.size})

    async def handle_delete(self, request: web.Request) -> web.StreamResponse:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized")
        rid = request.match_info.get("rid")
        if not self.manager.release(rid):
            return web.Response(status=404, text="Not Found")
        return web.json_response({"rid": rid, "released": True})

    async def start(self) -> None:
        self.app = web.Application()
        self.app.router.add_route(
            "GET", f"{self.resource_path}/{{rid}}", self.handle_get
        )
        self.app.router.add_route(
            "PUT", f"{self.resource_path}/{{rid}}", self.handle_put
        )
        self.app.router.add_route(
            "DELETE", f"{self.resource_path}/{{rid}}", self.handle_delete
        )

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        logger.info(
            f"[Live2D] 资源服务已启动: http://{self.host}:{self.port}{self.resource_path}"
        )

    async def stop(self) -> None:
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        logger.info("[Live2D] 资源服务已停止")

