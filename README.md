# AstrBot Live2D Adapter

AstrBot 的 Live2D 平台适配器插件，负责桌面端与 AstrBot 间的协议桥接。  
支持文本/图片/语音输入、表演序列回传、资源服务与桌面能力调用。

## 快速入口

- 一键安装与云服务器教程：[`docs/TUTORIAL.zh-CN.md`](./docs/TUTORIAL.zh-CN.md)
- 协议文档：[`docs/API.md`](./docs/API.md)
- 管理命令：[`docs/COMMANDS.md`](./docs/COMMANDS.md)

## 安装

在 **AstrBot 插件市场** 搜索并安装 `astrbot_plugin_live2d_adapter`，启用后在平台适配器处添加一个live2d 适配器，并配置`auth_token`

## 能力概览

- `input.message` / `input.touch` / `input.shortcut` 双向事件桥接
- 消息链转换为 Live2D 表演序列（文字、动作、表情、TTS）
- WebSocket 握手鉴权、心跳保活、单连接约束
- 资源管理（inline / URL / resource id）与自动清理
- 桌面工具声明与远程调用（窗口/截图等）

## 架构流程

1. 桌面端发起 `sys.handshake`（含 token）
2. 适配器完成鉴权并建立会话
3. 桌面输入事件转换为 AstrBot 消息事件
4. AstrBot 回复转换为 `perform.show` 回推给桌面端
5. 大资源通过资源服务端口分流传输

## 推荐配置（安全默认）

```yaml
type: "live2d"
enable: true
id: "live2d_default"

ws_host: "127.0.0.1"
ws_port: 9090
ws_path: "/astrbot/live2d"
auth_token: ""              # 强制鉴权；留空自动生成随机密钥
max_connections: 1
kick_old: true

resource_enabled: true
resource_host: "127.0.0.1"
resource_port: 9091
resource_path: "/resources"
resource_dir: "live2d_resources"
resource_token: ""          # 为空时复用 auth_token
```

### 认证密钥说明

- `auth_token` 现为强制。
- 若配置为空，插件会自动生成随机密钥并保存到：
  `data/plugin_data/astrbot-live2d-adapter/live2d_auth_token.txt`
- 请将该值填入桌面端「设置 -> 连接配置 -> 认证令牌」。

## 云服务器部署要点

若桌面端通过公网连接服务器，请至少完成以下步骤：

1. 将 `ws_host`/`resource_host` 调整为可监听地址（如 `0.0.0.0`）
2. 云安全组放行 TCP `9090`、`9091`
3. 主机防火墙同步放行同端口
4. **务必设置来源 IP 白名单**
5. 使用强随机 token，建议配合 WSS/反向代理

详细命令示例见：[`docs/TUTORIAL.zh-CN.md`](./docs/TUTORIAL.zh-CN.md)

## 服务器安全基线（建议）

- 使用 32 位以上随机认证密钥，并定期轮换
- 不对公网暴露不必要端口
- 限制来源 IP，避免全网可连
- 关注连接失败、异常流量、资源占用日志
- 生产环境优先使用 TLS（WSS）

## 常用管理命令

- `/live2d status`：查看连接、资源与服务状态
- `/live2d info`：查看当前客户端信息
- `/live2d list`：查看客户端列表
- `/live2d resources`：查看资源占用
- `/live2d cleanup`：手动清理资源（管理员）
- `/live2d config`：查看当前配置（管理员）

完整说明见：[`docs/COMMANDS.md`](./docs/COMMANDS.md)

## 与其他插件联动

适配器保留动作/表情注入通道，其他插件可通过自定义消息组件输出 `live2d_motion` / `live2d_expression`，驱动桌面端模型表现。

## 项目结构

```text
astrbot-live2d-adapter/
├─ main.py                  # AstrBot 插件入口
├─ adapters/                # 平台适配与消息事件
├─ converters/              # 输入/输出转换器
├─ core/                    # 协议与配置类型
├─ server/                  # WebSocket 与资源服务实现
└─ docs/
   ├─ API.md
   ├─ COMMANDS.md
   └─ TUTORIAL.zh-CN.md
```

## 相关项目

- [AstrBot](https://github.com/Soulter/AstrBot)
- [astrbot-live2d-desktop](https://github.com/lxfight/astrbot-live2d-desktop)

## License

MIT
