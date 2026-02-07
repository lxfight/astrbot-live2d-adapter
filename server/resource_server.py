"""资源 HTTP 服务"""

from __future__ import annotations

import hashlib

from aiohttp import web
from astrbot.api import logger

from .resource_manager import ResourceManager


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
        if not rid:
            return web.Response(status=400, text="Missing rid")
        entry = self.manager.get_resource(rid)
        if not entry or not entry.path or not entry.path.exists():
            return web.Response(status=404, text="Not Found")
        return web.FileResponse(entry.path)

    async def handle_put(self, request: web.Request) -> web.StreamResponse:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized")
        rid = request.match_info.get("rid")
        if not rid:
            return web.Response(status=400, text="Missing rid")
        entry = self.manager.get_resource(rid)
        if not entry or not entry.path:
            return web.Response(status=404, text="Not Found")
        expected = request.content_length
        if expected is not None:
            try:
                self.manager.cleanup(reserve_bytes=int(expected), reserve_files=0)
            except ValueError as e:
                return web.Response(status=413, text=str(e))

        sha = hashlib.sha256()
        size = 0
        try:
            with entry.path.open("wb") as f:
                async for chunk in request.content.iter_chunked(1024 * 1024):
                    size += len(chunk)
                    sha.update(chunk)
                    f.write(chunk)
        except Exception as e:
            entry.status = "error"
            return web.Response(status=500, text=f"Write failed: {e!s}")

        digest = sha.hexdigest()
        if entry.sha256 and entry.sha256 != digest:
            entry.status = "error"
            try:
                entry.path.unlink(missing_ok=True)
            except OSError:
                pass
            return web.Response(status=400, text="SHA256 mismatch")

        entry.sha256 = digest
        entry.size = size
        entry.status = "ready"
        self.manager.commit_upload(rid, size=size)
        try:
            self.manager.cleanup()
        except Exception:
            pass

        return web.json_response({"rid": rid, "size": entry.size, "sha256": digest})

    async def handle_delete(self, request: web.Request) -> web.StreamResponse:
        if not self._check_auth(request):
            return web.Response(status=401, text="Unauthorized")
        rid = request.match_info.get("rid")
        if not rid:
            return web.Response(status=400, text="Missing rid")
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
