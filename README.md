# AstrBot Live2D Adapter

**Live2D 桌面应用平台适配器**，支持 Live2D-Bridge Protocol v1.0

将 Live2D 桌面应用接入 AstrBot 机器人框架，实现：
- 用户通过 Live2D 桌面端与 AstrBot 进行私聊交互
- 支持文字、图片、语音等多模态消息双向传输
- Live2D 角色展示文字气泡、播放 TTS 语音、执行动作和表情

## 特性

✅ **完整的平台适配器**
- 作为 AstrBot 平台插件运行
- 支持 WebSocket 通讯（L2D-Bridge Protocol v1.0）
- 单连接约束、握手鉴权、心跳保活

✅ **双向消息转换**
- 桌面端输入 → AstrBot 消息链
- AstrBot 回复 → Live2D 表演序列（文字、动作、表情、TTS）

✅ **资源管理**
- 支持图片、音频、视频等大文件传输
- 自动处理 URL 引用、资源 ID 引用、Base64 内联

✅ **交互事件支持**
- 支持 input.message（文本消息）
- 支持 input.touch（触摸事件）
- 支持 input.shortcut（快捷键事件）

✅ **动作执行接口**
- 保留下发动作和表情的能力
- 其他插件可通过自定义组件控制 Live2D 动作
- 支持 motionType 提示（由其他模块实现）

✅ **流式输出支持**（可选）
- 逐块发送 LLM 生成内容
- 提升交互体验

## 技术栈

- Python 3.9+
- AstrBot 框架
- websockets（WebSocket 服务器）
- asyncio（异步 IO）

## 安装

### 方式 1：作为 AstrBot 插件（推荐）

1. 将本项目放入 AstrBot 插件目录：

```bash
cd <AstrBot安装目录>/data/plugins
# 将本仓库复制/克隆到该目录下
```

2. 在 AstrBot Dashboard 中启用 Live2D 平台适配器

3. 配置平台参数（见下文）

## 配置

在 AstrBot Dashboard 中配置 Live2D 平台适配器：

```yaml
type: "live2d"
enable: true
id: "live2d_default"

# WebSocket 配置
ws_host: "0.0.0.0"         # WebSocket 监听地址
ws_port: 9090              # WebSocket 端口
ws_path: "/astrbot/live2d" # WebSocket 路径
auth_token: ""             # 鉴权 Token（留空则不鉴权）
max_connections: 1         # 最大连接数（建议保持为 1）
kick_old: true             # 新连接时踢掉旧连接

# 功能配置
enable_tts: false          # 是否启用 TTS（由 AstrBot TTS 插件提供）
tts_mode: "local"          # TTS 模式：local（桌面端处理）/ remote（服务端处理）
enable_streaming: true     # 是否启用流式输出

# 资源服务器（图片/语音等大资源传输）
resource_enabled: true
resource_host: "0.0.0.0"
resource_port: 9091
resource_path: "/resources"
resource_dir: "./data/live2d_resources"
resource_base_url: ""      # 为空时自动使用 http://{host}:{port}
resource_token: ""         # 为空时复用 auth_token
resource_max_inline_bytes: 262144  # 256KB，超过此大小使用 URL 引用

# 临时文件管理
temp_dir: "./data/live2d_temp"
temp_ttl_seconds: 21600    # 6小时
temp_max_total_bytes: 268435456  # 256MB
temp_max_files: 5000

# 清理任务
cleanup_interval_seconds: 600  # 10分钟
```

## 使用

### 消息流程

1. **用户输入** → Live2D 桌面端
2. **WebSocket 传输** → 适配器（`input.message`）
3. **转换** → AstrBot 消息事件
4. **处理** → AstrBot 插件系统 / LLM
5. **回复** → 适配器接收 MessageChain
6. **转换** → Live2D 表演序列（`perform.show`）
7. **WebSocket 传输** → 桌面端展示

### 在其他插件中控制 Live2D 动作

其他 AstrBot 插件可以通过自定义消息组件来控制 Live2D 动作和表情：

```python
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain

# 定义自定义组件类
class Live2DMotion:
    """Live2D 动作组件"""
    def __init__(self, group: str, index: int = 0, priority: int = 2,
                 motion_type: str = None, loop: bool = False):
        self.type = "live2d_motion"
        self.group = group
        self.index = index
        self.priority = priority
        self.motion_type = motion_type  # 可选：happy, sad, angry 等
        self.loop = loop
        self.fade_in = 300
        self.fade_out = 300

class Live2DExpression:
    """Live2D 表情组件"""
    def __init__(self, expression_id: str, fade: int = 300, motion_type: str = None):
        self.type = "live2d_expression"
        self.expression_id = expression_id
        self.fade = fade
        self.motion_type = motion_type  # 可选

# 使用示例
async def my_handler(event):
    chain = MessageChain([
        Plain("你好！"),
        Live2DMotion(group="TapBody", index=0, motion_type="happy"),
        Live2DExpression(expression_id="smile")
    ])
    await event.send(chain)
```

## 项目结构

```
astrbot-live2d-adapter/
├── main.py                  # AstrBot 插件入口
├── README.md                # 项目说明
├── API.md                   # 协议文档
├── requirements.txt         # Python 依赖
├── adapters/                # 平台适配器与事件定义
│   ├── platform_adapter.py  # Live2D 平台适配器
│   └── message_event.py     # Live2D 消息事件
├── converters/              # 消息/表演序列转换
│   ├── input_converter.py   # 输入消息转换
│   └── output_converter.py  # 输出消息转换
├── core/                    # 协议与核心类型
│   ├── protocol.py          # 协议定义
│   └── config.py            # 配置类型
└── server/                  # WebSocket 服务端实现
    ├── websocket_server.py  # WebSocket 服务器
    ├── message_handler.py   # 消息处理器
    ├── resource_manager.py  # 资源管理器
    └── resource_server.py   # 资源HTTP服务器
```

## 协议

使用 **L2D-Bridge Protocol v1.0**。

协议文档：[API.md](./API.md)

## 许可证

MIT

## 相关项目

- [AstrBot](https://github.com/Soulter/AstrBot) - 多平台机器人框架
- [astrbot-live2d-desktop](https://github.com/lxfight/astrbot-live2d-desktop) - Live2D 桌面端应用

## 贡献

欢迎提交 Issue 和 Pull Request！
