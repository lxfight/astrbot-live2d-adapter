# AstrBot Live2D Adapter

**Live2D 桌面应用平台适配器**，支持 Live2D-Bridge Protocol v1.0

将 Live2D 桌面应用接入 AstrBot 机器人框架，实现：
- 用户通过 Live2D 桌面端与 AstrBot 进行私聊交互
- 支持文字、图片、语音等多模态消息双向传输
- Live2D 角色展示文字气泡、播放 TTS 语音、执行动作和表情

## 特性

✅ **完整的平台适配器**
- 作为 AstrBot 官方平台插件运行
- 支持 WebSocket 通讯（L2D-Bridge Protocol v1.0）
- 单连接约束、握手鉴权、心跳保活

✅ **双向消息转换**
- 桌面端输入 → AstrBot 消息链
- AstrBot 回复 → Live2D 表演序列（文字、动作、表情、TTS）

✅ **情感识别**
- 自动分析消息情感（开心、难过、生气等）
- 自动匹配 Live2D 动作和表情

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

1. 将本项目克隆到 AstrBot 插件目录：

```bash
cd <AstrBot安装目录>/addons/plugins
git clone https://github.com/your-org/astrbot-live2d-adapter.git
```

2. 安装依赖：

```bash
cd astrbot-live2d-adapter
pip install -r requirements.txt
```

3. 在 AstrBot Dashboard 中启用 Live2D 平台适配器

4. 配置平台参数（见下文）

### 方式 2：独立运行（仅用于测试）

```bash
python main.py
```

注意：独立运行模式仅提供 WebSocket 服务，无法接入 AstrBot 功能。

## 配置

在 AstrBot Dashboard 中配置 Live2D 平台适配器：

```yaml
server:
  host: "0.0.0.0"          # WebSocket 监听地址
  port: 8765               # WebSocket 端口
  path: "/ws"              # WebSocket 路径
  max_connections: 1       # 最大连接数（建议保持为 1）
  kick_old: true           # 新连接时踢掉旧连接
  auth_token: ""           # 鉴权 Token（留空则不鉴权）

# 功能开关
enable_auto_emotion: true  # 自动情感识别和动作匹配
enable_tts: false          # 是否启用 TTS（由 AstrBot TTS 插件提供）
tts_mode: "local"          # TTS 模式：local（桌面端处理）/ remote（服务端处理）
```

## 使用

### 可用指令

在 AstrBot 中使用以下指令管理 Live2D 适配器：

- `/live2d status` - 查看连接状态和会话信息
- `/live2d reload` - 重载配置（开发中）
- `/live2d say <text>` - 向 Live2D 客户端发送文本消息

### 消息流程

1. **用户输入** → Live2D 桌面端
2. **WebSocket 传输** → 适配器（`input.message`）
3. **转换** → AstrBot 消息事件
4. **处理** → AstrBot 插件系统 / LLM
5. **回复** → 适配器接收 MessageChain
6. **转换** → Live2D 表演序列（`perform.show`）
7. **WebSocket 传输** → 桌面端展示

## 开发

### 项目结构

```
astrbot-live2d-adapter/
├── main.py                  # AstrBot 插件入口
├── live2d_platform.py       # 平台适配器主类
├── live2d_event.py          # 消息事件类
├── message_converter.py     # 消息转换器（双向）
├── server.py                # WebSocket 服务器
├── handler.py               # 消息处理器
├── protocol.py              # 协议定义和数据结构
├── commands.py              # 指令处理器
├── config.py                # 配置管理
├── config.yaml              # 默认配置
├── requirements.txt         # Python 依赖
├── PROGRESS.md              # 开发进度追踪
└── README.md                # 本文件
```

### 协议

使用 **L2D-Bridge Protocol v1.0**，详见：
- [Live2D-Bridge-Protocol.md](../docs/Live2D-Bridge-Protocol.md) - 协议设计文档
- [adapter-spec.md](../docs/adapter-spec.md) - 适配器规范

### 参考文档

- [AstrBot 适配器开发文档](../docs/AstrBot%20适配器开发文档) - 平台适配器开发指南
- [PROGRESS.md](PROGRESS.md) - 详细的开发进度和功能矩阵

## 许可证

（待添加）

## 相关项目

- [AstrBot](https://github.com/AstrBotDevs/AstrBot) - 多平台机器人框架
- [astrbot-live2d-desktop](../astrbot-live2d-desktop) - Live2D 桌面端应用

## 贡献

欢迎提交 Issue 和 Pull Request！
