"""配置管理模块"""

from pathlib import Path
from typing import Any

import yaml


class Config:
    """配置管理器"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """加载配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        with open(self.config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value

    @property
    def server_host(self) -> str:
        return self.get("server.host", "0.0.0.0")

    @property
    def server_port(self) -> int:
        return self.get("server.port", 9090)

    @property
    def auth_token(self) -> str:
        return self.get("server.auth_token", "")

    @property
    def ws_path(self) -> str:
        return self.get("server.path", "/ws")

    @property
    def max_connections(self) -> int:
        return self.get("server.max_connections", 1)

    @property
    def kick_old(self) -> bool:
        return self.get("server.kick_old", True)

    @property
    def report_group_msg(self) -> bool:
        return self.get("events.report_group_msg", True)

    @property
    def report_private_msg(self) -> bool:
        return self.get("events.report_private_msg", True)

    @property
    def enable_perform(self) -> bool:
        return self.get("events.enable_perform", True)

    @property
    def http_enabled(self) -> bool:
        return self.get("http.enabled", False)

    @property
    def http_host(self) -> str:
        return self.get("http.host", "0.0.0.0")

    @property
    def http_port(self) -> int:
        return self.get("http.port", 8080)

    @property
    def http_static_dir(self) -> str:
        return self.get("http.static_dir", "../astrbot-live2d-desktop/dist")

    @property
    def resource_enabled(self) -> bool:
        return self.get("resource.enabled", True)

    @property
    def resource_host(self) -> str:
        return self.get("resource.host", self.server_host)

    @property
    def resource_port(self) -> int:
        return self.get("resource.port", 9091)

    @property
    def resource_path(self) -> str:
        return self.get("resource.path", "/resources")

    @property
    def resource_dir(self) -> str:
        return self.get("resource.dir", "./data/live2d_resources")

    @property
    def resource_base_url(self) -> str:
        base_url = self.get("resource.base_url", "")
        if base_url:
            return base_url
        return f"http://{self.resource_host}:{self.resource_port}"

    @property
    def resource_token(self) -> str:
        token = self.get("resource.token", "")
        if token:
            return token
        return self.auth_token

    @property
    def resource_max_inline_bytes(self) -> int:
        return int(self.get("resource.max_inline_bytes", 262144))
