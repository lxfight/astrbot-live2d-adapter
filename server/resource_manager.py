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
        *,
        ttl_ms: int | None = None,
        max_total_bytes: int | None = None,
        max_total_files: int | None = None,
    ):
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")
        self.resource_path = "/" + resource_path.strip("/")
        self.max_inline_bytes = max_inline_bytes
        self.token = token or None
        self.ttl_ms = int(ttl_ms or 0) or None
        self.max_total_bytes = int(max_total_bytes or 0) or None
        self.max_total_files = int(max_total_files or 0) or None
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

    def cleanup(
        self, *, reserve_bytes: int = 0, reserve_files: int = 0
    ) -> dict[str, int]:
        """Cleanup resource files by TTL and quota.

        The cleanup is based on filesystem mtime so it also works across restarts.
        Reserve params are used when storing a new resource (make room first).
        """
        removed = 0
        removed_bytes = 0

        if self.max_total_bytes is not None and reserve_bytes > self.max_total_bytes:
            raise ValueError("Resource quota too small for the incoming payload.")
        if self.max_total_files is not None and reserve_files > self.max_total_files:
            raise ValueError("Resource file quota too small for the incoming payload.")

        # Drop stale metadata entries whose files are missing.
        for rid, entry in list(self.resources.items()):
            if entry.path and entry.status == "ready" and not entry.path.exists():
                self.resources.pop(rid, None)

        files: list[tuple[float, int, Path]] = []
        for p in self.storage_dir.iterdir():
            if not p.is_file():
                continue
            try:
                stat = p.stat()
            except OSError:
                continue
            files.append((stat.st_mtime, stat.st_size, p))

        files.sort(key=lambda x: x[0])

        now_ms = self._now()
        if self.ttl_ms:
            kept: list[tuple[float, int, Path]] = []
            for mtime, size, path in files:
                age_ms = now_ms - int(mtime * 1000)
                if age_ms <= self.ttl_ms:
                    kept.append((mtime, size, path))
                    continue
                try:
                    path.unlink(missing_ok=True)
                    removed += 1
                    removed_bytes += size
                except OSError:
                    kept.append((mtime, size, path))
                    continue
                self.resources.pop(path.stem, None)
            files = kept

        max_files = (
            max(self.max_total_files - reserve_files, 0)
            if self.max_total_files is not None
            else None
        )
        max_bytes = (
            max(self.max_total_bytes - reserve_bytes, 0)
            if self.max_total_bytes is not None
            else None
        )

        def total_bytes() -> int:
            return sum(size for _, size, _ in files)

        if max_files is not None:
            while len(files) > max_files:
                mtime, size, path = files.pop(0)
                try:
                    path.unlink(missing_ok=True)
                    removed += 1
                    removed_bytes += size
                except OSError:
                    files.append((mtime, size, path))
                    files.sort(key=lambda x: x[0])
                    break
                self.resources.pop(path.stem, None)

        if max_bytes is not None:
            while files and total_bytes() > max_bytes:
                mtime, size, path = files.pop(0)
                try:
                    path.unlink(missing_ok=True)
                    removed += 1
                    removed_bytes += size
                except OSError:
                    files.append((mtime, size, path))
                    files.sort(key=lambda x: x[0])
                    break
                self.resources.pop(path.stem, None)

        return {"removed": removed, "removed_bytes": removed_bytes}

    def prepare_upload(
        self, kind: str, mime: str, size: int = 0, sha256: str | None = None
    ) -> ResourceEntry:
        self.cleanup(reserve_bytes=max(size, 0), reserve_files=1)
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
        size = path.stat().st_size
        self.cleanup(reserve_bytes=size, reserve_files=1)
        rid = self._generate_id()
        filename = self._resource_filename(rid, mime)
        target = self.storage_dir / filename
        sha = hashlib.sha256()
        with path.open("rb") as src, target.open("wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                sha.update(chunk)
                dst.write(chunk)
        entry = ResourceEntry(
            rid=rid,
            kind=kind,
            mime=mime,
            size=size,
            sha256=sha.hexdigest(),
            path=target,
            status="ready",
            created_at=self._now(),
        )
        self.resources[rid] = entry
        return entry

    def build_reference_from_file(self, file_path: str, kind: str) -> dict[str, Any]:
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
        self.cleanup(reserve_bytes=len(data), reserve_files=1)
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
