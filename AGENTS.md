# AGENTS.md - 代理开发指南

本文档为在此 AstrBot Live2D 适配器仓库中工作的代理开发者提供项目配置、代码规范和最佳实践指南。

## 项目概述

AstrBot Live2D Adapter 是一个 AstrBot 平台适配器插件，通过 WebSocket 连接 Live2D 桌面应用，支持 Live2D-Bridge Protocol v1.0，实现双向消息转换和情感识别功能。

## 开发环境配置

### 依赖管理
```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 验证核心依赖
pip install websockets>=12.0 aiohttp>=3.11.18 pyyaml>=6.0 aiofiles>=23.0
```

### 运行和测试
```bash
# 作为 AstrBot 插件运行（推荐）
# 1. 将插件放入 <AstrBot>/addons/plugins/ 目录
# 2. 在 AstrBot Dashboard 中启用插件
# 3. 配置 WebSocket 参数

# 独立运行（仅用于测试）
python main.py

# 手动测试单个模块
python -m adapters.platform_adapter
python -m server.websocket_server
```

## 代码规范

### Python 版本和类型注解
- **Python 版本**: 3.9+
- **严格模式**: 使用 `from __future__ import annotations` 启用延迟求值
- **类型注解**: 所有公共 API 必须包含完整类型注解
- **Protocol 使用**: 配置类使用 `Protocol` 定义接口

```python
from __future__ import annotations
from typing import Any, Protocol
from dataclasses import dataclass

class ConfigLike(Protocol):
    @property
    def server_host(self) -> str: ...
    
    def get(self, key: str, default: Any = None) -> Any: ...

@dataclass
class ErrorInfo:
    code: int
    message: str
```

### 导入规范
```python
# 标准库导入
import asyncio
import logging
from pathlib import Path
from typing import Any

# 第三方库导入
import yaml
import websockets

# AstrBot 框架导入（使用 try-except 处理可选依赖）
try:
    from astrbot.api.event import AstrMessageEvent, MessageChain
    from astrbot.api.platform import Platform, register_platform_adapter
except ImportError as e:
    raise ImportError(f"无法导入 AstrBot 模块: {e}")

# 本地模块导入（使用相对导入）
from ..converters.input_converter import InputMessageConverter
from ..core.protocol import BasePacket
from .message_event import Live2DMessageEvent
```

### 命名约定
- **文件名**: snake_case（如 `platform_adapter.py`, `websocket_server.py`）
- **类名**: PascalCase（如 `Live2DPlatformAdapter`, `WebSocketServer`）
- **函数/变量**: snake_case（如 `convert_message`, `client_id`）
- **常量**: UPPER_SNAKE_CASE（如 `DEFAULT_PORT`, `MAX_CONNECTIONS`）
- **私有成员**: 下划线前缀（如 `_validate_config`）

### 类和函数设计规范
```python
class WebSocketServer:
    """WebSocket 服务器
    
    负责 Live2D 客户端连接管理和消息路由
    """
    
    def __init__(self, config: ConfigLike, resource_manager=None):
        """初始化服务器
        
        Args:
            config: 配置对象
            resource_manager: 资源管理器实例
        """
        self.config = config
        self.clients: dict[str, Any] = {}
    
    async def register(self, websocket, client_id: str) -> bool:
        """注册客户端连接
        
        Args:
            websocket: WebSocket 连接对象
            client_id: 客户端唯一标识
            
        Returns:
            注册是否成功
        """
        # 实现逻辑
        pass
```

### 异步编程规范
```python
# 所有网络操作使用 async/await
async def send_message(self, packet: BasePacket) -> None:
    """发送消息到客户端"""
    try:
        message = packet.to_json()
        await self.websocket.send(message)
        logger.info(f"消息已发送: {packet.id}")
    except Exception as e:
        logger.error(f"发送消息失败: {e}")
        raise

# 使用正确的异步上下文管理
async with websockets.connect(ws_url) as websocket:
    await self.register(websocket, client_id)
    await self.handle_connection(websocket)
```

### 错误处理规范
```python
import logging

logger = logging.getLogger(__name__)

class Live2DAdapterError(Exception):
    """Live2D 适配器基础异常"""
    pass

class ConfigError(Live2DAdapterError):
    """配置相关异常"""
    pass

# 异常处理模式
async def process_message(self, message: str) -> None:
    try:
        packet = BasePacket.from_json(message)
        await self.handle_packet(packet)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        await self.send_error("invalid_json", str(e))
    except Live2DAdapterError as e:
        logger.error(f"适配器错误: {e}")
        raise
    except Exception as e:
        logger.error(f"未知错误: {e}", exc_info=True)
        await self.send_error("internal_error", "内部服务器错误")
```

### 日志规范
```python
import logging

logger = logging.getLogger(__name__)

# 使用不同日志级别
logger.debug("调试信息: 客户端连接详情", extra={"client_id": client_id})
logger.info("普通信息: 客户端已连接")
logger.warning("警告信息: 连接数接近上限")
logger.error("错误信息: 连接处理失败", exc_info=True)

# 结构化日志
logger.info(
    "处理用户消息",
    extra={
        "client_id": client_id,
        "message_type": message_type,
        "content_length": len(content)
    }
)
```

### 配置管理规范
```python
class Config:
    """配置管理器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = Path(config_path)
        self.config: dict[str, Any] = {}
        self.load()
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取嵌套配置项
        
        支持 'server.host' 点分隔路径
        """
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value
    
    @property
    def server_port(self) -> int:
        """服务器端口配置"""
        return self.get("server.port", 9090)
```

## 项目架构

### 目录结构
```
astrbot-live2d-adapter/
├── main.py                    # AstrBot 插件入口
├── requirements.txt           # Python 依赖
├── config.yaml              # 默认配置文件
├── adapters/                # 平台适配器
│   ├── __init__.py
│   ├── platform_adapter.py  # 主适配器类
│   └── message_event.py     # 消息事件类
├── converters/              # 消息转换器
│   ├── __init__.py
│   ├── input_converter.py   # 输入消息转换
│   ├── output_converter.py  # 输出消息转换
│   └── emotion_analyzer.py  # 情感分析器
├── core/                    # 核心模块
│   ├── __init__.py
│   ├── protocol.py         # 协议定义
│   └── config.py           # 配置管理
├── server/                 # 服务器模块
│   ├── __init__.py
│   ├── websocket_server.py # WebSocket 服务
│   ├── message_handler.py # 消息处理器
│   ├── resource_manager.py # 资源管理
│   └── resource_server.py  # HTTP 资源服务
└── commands/               # 指令处理
    ├── __init__.py
    └── live2d_commands.py # Live2D 指令
```

### 协议实现
```python
# 使用 dataclass 定义协议结构
@dataclass
class BasePacket:
    op: str
    id: str
    ts: int
    payload: dict[str, Any] | None = None
    error: ErrorInfo | None = None
    
    def to_json(self) -> str:
        """序列化为 JSON"""
        
    @classmethod
    def from_json(cls, json_str: str) -> "BasePacket":
        """从 JSON 反序列化"""
```

## 测试指南

### 单元测试
```python
# 测试文件命名: test_*.py
# 位置: tests/ 目录或与源文件同目录

import pytest
from unittest.mock import AsyncMock, patch

from ..core.protocol import BasePacket
from ..server.websocket_server import WebSocketServer

class TestWebSocketServer:
    def setup_method(self):
        """每个测试方法前执行"""
        self.config = ConfigLike()
        self.server = WebSocketServer(self.config)
    
    async def test_register_client(self):
        """测试客户端注册"""
        # 测试实现
        pass
```

### 手动测试
```bash
# 测试 WebSocket 连接
# 1. 启动服务器
python main.py

# 2. 使用 WebSocket 客户端测试
wscat -c ws://localhost:9090/ws

# 3. 发送测试消息
{"op": "sys.handshake", "id": "test", "ts": 1234567890, "payload": {}}
```

## 开发注意事项

### AstrBot 集成
- 插件必须继承 `Star` 类
- 使用 `@register` 装饰器注册插件
- 使用 `@register_platform_adapter` 注册平台适配器
- 所有 AstrBot 导入需要 try-except 保护

### WebSocket 协议
- 严格遵循 Live2D-Bridge Protocol v1.0
- 使用 JSON 格式，UTF-8 编码
- 所有数据包包含 `op`, `id`, `ts` 字段
- 错误响应包含 `error` 对象

### 资源管理
- 图片文件支持 Base64 内联和 rid 引用
- 使用 `ResourceManager` 统一管理资源
- 临时文件使用 `tempfile` 模块处理
- 及时清理临时文件和缓存

### 性能考虑
- 使用连接池管理 WebSocket 连接
- 异步处理所有 I/O 操作
- 合理设置连接数限制（建议 1）
- 使用消息队列缓冲高频消息

## 调试技巧

### 日志配置
```python
# 开启调试日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 模块特定日志
logger = logging.getLogger("astrbot-live2d-adapter")
logger.setLevel(logging.DEBUG)
```

### 网络调试
```bash
# 监听 WebSocket 流量
tcpdump -i lo port 9090

# 使用浏览器开发者工具
# Network -> WS 标签页查看消息流
```

## 常见问题解决

### 导入错误
```python
# 确保 AstrBot 模块可导入
export PYTHONPATH="${PYTHONPATH}:/path/to/astrbot"

# 作为插件运行时相对路径问题
from ..core.config import Config  # ✅ 正确
from core.config import Config     # ❌ 错误
```

### 连接问题
- 检查防火墙设置
- 确认端口未被占用
- 验证 auth_token 配置
- 查看服务器日志排查错误

### 配置问题
- 配置文件使用 UTF-8 编码
- YAML 格式注意缩进
- 使用绝对路径指定资源目录