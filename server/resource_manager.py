"""资源管理器 - 处理资源存储与引用"""

from __future__ import annotations

import base64
import hashlib
import mimetypes
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote


@dataclass
class ResourceEntry:
    """资源条目"""

    rid: str
    kind: str
    mime: str
    size: int
    sha256: str | None
    path: Path | None
    status: str
    created_at: int


class ResourceManager:
    """资源管理器"""

    def __init__(
        self,
        storage_dir: str,
        base_url: str,
        resource_path: str = "/resources",
        max_inline_bytes: int = 262144,
        token: str | None = None,
    ):
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")
        self.resource_path = "/" + resource_path.strip("/")
        self.max_inline_bytes = max_inline_bytes
        self.token = token or None
        self.resources: dict[str, ResourceEntry] = {}

    def _now(self) -> int:
        return int(time.time() * 1000)

    def _generate_id(self) -> str:
        return str(uuid.uuid4())

    def _guess_mime(self, file_path: str) -> str:
        mime, _ = mimetypes.guess_type(file_path)
        return mime or "application/octet-stream"

    def _calc_sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _resource_filename(self, rid: str, mime: str | None = None) -> str:
        ext = ""
        if mime:
            ext = mimetypes.guess_extension(mime) or ""
        return f"{rid}{ext}"

    def _build_inline_data(self, data: bytes, mime: str) -> str:
        encoded = base64.b64encode(data).decode("utf-8")
        return f"data:{mime};base64,{encoded}"

    def _build_url(self, rid: str) -> str:
        base = f"{self.base_url}{self.resource_path}/{rid}"
        if self.token:
            return f"{base}?token={quote(self.token)}"
        return base

    def prepare_upload(
        self, kind: str, mime: str, size: int = 0, sha256: str | None = None
    ) -> ResourceEntry:
        rid = self._generate_id()
        filename = self._resource_filename(rid, mime)
        path = self.storage_dir / filename
        entry = ResourceEntry(
            rid=rid,
            kind=kind,
            mime=mime,
            size=size,
            sha256=sha256,
            path=path,
            status="pending",
            created_at=self._now(),
        )
        self.resources[rid] = entry
        return entry

    def commit_upload(self, rid: str, size: int | None = None) -> ResourceEntry | None:
        entry = self.resources.get(rid)
        if not entry:
            return None
        if size is not None:
            entry.size = size
        entry.status = "ready"
        return entry

    def register_file(
        self, file_path: str, kind: str, mime: str | None = None
    ) -> ResourceEntry:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(file_path)
        mime = mime or self._guess_mime(file_path)
        data = path.read_bytes()
        rid = self._generate_id()
        filename = self._resource_filename(rid, mime)
        target = self.storage_dir / filename
        target.write_bytes(data)
        entry = ResourceEntry(
            rid=rid,
            kind=kind,
            mime=mime,
            size=len(data),
            sha256=self._calc_sha256(data),
            path=target,
            status="ready",
            created_at=self._now(),
        )
        self.resources[rid] = entry
        return entry

    def build_reference_from_file(
        self, file_path: str, kind: str
    ) -> dict[str, Any]:
        path = Path(file_path)
        mime = self._guess_mime(file_path)
        size = path.stat().st_size
        if size <= self.max_inline_bytes:
            data = path.read_bytes()
            return {
                "inline": self._build_inline_data(data, mime),
                "mime": mime,
                "size": size,
                "sha256": self._calc_sha256(data),
            }
        entry = self.register_file(file_path, kind, mime=mime)
        return {
            "rid": entry.rid,
            "url": self._build_url(entry.rid),
            "mime": entry.mime,
            "size": entry.size,
            "sha256": entry.sha256,
        }

    def build_reference_from_bytes(
        self, data: bytes, kind: str, mime: str
    ) -> dict[str, Any]:
        if len(data) <= self.max_inline_bytes:
            return {
                "inline": self._build_inline_data(data, mime),
                "mime": mime,
                "size": len(data),
                "sha256": self._calc_sha256(data),
            }
        rid = self._generate_id()
        filename = self._resource_filename(rid, mime)
        target = self.storage_dir / filename
        target.write_bytes(data)
        entry = ResourceEntry(
            rid=rid,
            kind=kind,
            mime=mime,
            size=len(data),
            sha256=self._calc_sha256(data),
            path=target,
            status="ready",
            created_at=self._now(),
        )
        self.resources[rid] = entry
        return {
            "rid": entry.rid,
            "url": self._build_url(entry.rid),
            "mime": entry.mime,
            "size": entry.size,
            "sha256": entry.sha256,
        }

    def get_resource(self, rid: str) -> ResourceEntry | None:
        return self.resources.get(rid)

    def get_resource_payload(self, rid: str) -> dict[str, Any] | None:
        entry = self.get_resource(rid)
        if not entry:
            return None
        payload = {
            "rid": entry.rid,
            "kind": entry.kind,
            "mime": entry.mime,
            "size": entry.size,
            "sha256": entry.sha256,
        }
        if entry.status == "ready":
            payload["url"] = self._build_url(entry.rid)
        return payload

    def get_resource_path(self, rid: str) -> Path | None:
        entry = self.get_resource(rid)
        if not entry:
            return None
        return entry.path

    def release(self, rid: str) -> bool:
        entry = self.resources.pop(rid, None)
        if not entry:
            return False
        if entry.path and entry.path.exists():
            try:
                entry.path.unlink()
            except OSError:
                return False
        return True

    def build_upload_url(self, rid: str) -> str:
        return self._build_url(rid)
