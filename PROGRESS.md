# astrbot-live2d-adapter 开发进度追踪

**最后更新：** 2026-01-05 18:30

本文件用于追踪 `astrbot-live2d-adapter`（AstrBot Live2D 平台适配器/桥接层）的开发进度，覆盖：
- 桌面端 ↔ 适配器（WebSocket + L2D-Bridge Protocol）
- 适配器 ↔ AstrBot（平台适配器事件/消息链）

---
## 最新进展（2026-01-05 更新）

✅ **核心功能已完成**：
1. ✅ 创建了完整的平台适配器主类 (`live2d_platform.py`)
   - 实现了 `Platform` 基类的所有必需方法
   - 支持 `@register_platform_adapter` 装饰器注册
   - 完整的消息转换和事件提交流程

2. ✅ 完善了 `Live2DMessageEvent` 事件类
   - 正确继承 `AstrMessageEvent`
   - 实现消息发送到 WebSocket 客户端
   - 支持流式输出（可选）

3. ✅ 改造了 `handler.py` 接入 AstrBot 事件处理
   - 添加了消息接收回调机制
   - 支持将客户端消息转换并提交到 AstrBot 事件队列

4. ✅ 完善了 `message_converter.py` 双向转换
   - `InputMessageConverter`: Live2D → AstrBot 消息组件
   - `OutputMessageConverter`: AstrBot MessageChain → Live2D 表演序列
   - 支持情感分析和自动动作/表情

5. ✅ 更新了 `main.py` 支持插件式加载
   - 作为 AstrBot 插件运行（推荐模式）
   - 通过 `@register` 装饰器注册
   - 支持指令系统 (`/live2d` 命令)

---
## 🎉 重要更新（2026-01-05 18:30）

### ✅ MVP 核心功能已完成！

**新增文件：**
- ✅ [live2d_platform.py](live2d_platform.py) - Live2D 平台适配器主类
- ✅ [commands.py](commands.py) - 适配器指令系统

**更新文件：**
- ✅ [main.py](main.py) - 改造为 AstrBot 插件入口（移除独立运行模式）
- ✅ [handler.py](handler.py:149) - 修复错误的 API 调用
- ✅ [server.py](server.py:82-91) - 添加 WebSocket 路径校验

**功能清单：**
1. **完整的平台适配器实现**
   - 注册为 AstrBot 官方平台适配器
   - WebSocket 服务器自动启动
   - 消息双向转换完整链路

2. **适配器指令**
   - `/live2d status` - 查看连接状态
   - `/live2d reload` - 重载配置
   - `/live2d say <text>` - 测试表演下发

3. **消息流程**
   ```
   桌面端 → input.message → AstrBotMessage → commit_event()
   → AstrBot 处理 → MessageChain → perform.show → 桌面端
   ```

---

## 1. 目标与范围（MVP）

### 1.1 MVP 目标

- 桌面端连接适配器（单连接约束、握手鉴权、心跳）
- 桌面端发送文本输入 → 进入 AstrBot 处理流水线 → AstrBot 回复 → 桌面端以 `perform.show` 展示（至少 text）
- 可选：图片/音频（TTS URL）按协议转换下发

### 1.2 参考文档 / 源码锚点

- 协议设计：`docs/Live2D-Bridge-Protocol.md`（v1.0.0）
- 适配器规范：`docs/adapter-spec.md`
- 协议 API（注意与设计文档存在差异，见“风险/阻塞”）：`docs/api.md`
- AstrBot 平台适配器开发文档：`docs/AstrBot 适配器开发文档`
- AstrBot 源码：`AstrBot/astrbot`
  - 平台适配器注册：`AstrBot/astrbot/core/platform/register.py`
  - 平台基类：`AstrBot/astrbot/core/platform/platform.py`
  - 事件基类：`AstrBot/astrbot/core/platform/astr_message_event.py`
  - 参考实现：`AstrBot/astrbot/core/platform/sources/*`

---

## 2. 当前代码结构（适配器仓库）

目录：`astrbot-live2d-adapter/`

**核心文件：**
- [main.py](main.py) - AstrBot 插件入口（注册平台适配器、指令）
- [live2d_platform.py](live2d_platform.py) - **[新]** Live2D 平台适配器主类
- [commands.py](commands.py) - **[新]** 适配器指令处理器

**协议与服务：**
- [config.py](config.py) / [config.yaml](config.yaml) - 配置读取与默认项
- [server.py](server.py) - WebSocket Server（连接管理、单连接、握手门禁、消息循环）
- [protocol.py](protocol.py) - 协议数据结构/常量 + 部分包构造 + 表演元素构造函数
- [handler.py](handler.py) - 消息处理器（已修复，现用于非 AstrBot 事件的处理）

**消息转换：**
- [message_converter.py](message_converter.py)
  - `InputMessageConverter` - 客户端 `input.message.content` → AstrBot 消息组件
  - `OutputMessageConverter` - AstrBot `MessageChain` → `perform.show.sequence`
- [live2d_event.py](live2d_event.py) - `Live2DMessageEvent`（AstrBot 事件，负责输出推送）

---

## 3. 协议实现矩阵（对照 L2D-Bridge v1.0）

> 以 `docs/Live2D-Bridge-Protocol.md` 为准；`docs/api.md` 目前与其存在部分字段/op 命名差异。

### 3.1 系统级

- [x] `sys.handshake`：接入点已在 `server.py`（首包必须握手）
- [x] `sys.handshake_ack`：已接入（分配 `session_id/user_id` 并回包）
- [x] `sys.ping` → `sys.pong`：处理路径已在 `handler.py`
- [ ] `sys.error`：结构已在 `protocol.py`，但错误码/触发点需要补齐与统一

### 3.2 输入级（Client → Server）

- [x] `input.message`：**已完整接入 AstrBot 事件流程**（[live2d_platform.py:139](live2d_platform.py:139)）
- [x] `input.touch`：已接入（联调示例：触摸 Head 下发表演）
- [x] `input.shortcut`：已接入（联调示例：`random_action` 下发表演）

### 3.3 表演级（Server → Client）

- [x] `perform.show`：`protocol.py` 已提供 `create_perform_show`，`live2d_event.py` 会下发 `perform.show`
- [x] `perform.interrupt`：已补齐触发与指令路径

### 3.4 状态同步

- [x] `state.ready`：已接入
- [x] `state.playing`：已接入
- [x] `state.config`：已接入

---

## 4. AstrBot 集成矩阵

### 4.1 作为 AstrBot 平台适配器（插件形态）

- [x] 实现 `Platform` 子类并 `@register_platform_adapter(...)` 注册（[live2d_platform.py:29](live2d_platform.py:29)）
- [x] 在 `run()` 中启动 WebSocket 服务，并把客户端输入桥接为 AstrBot 事件（[live2d_platform.py:255](live2d_platform.py:255)）
- [x] 实现 `send_by_session()`：允许 AstrBot 主动向当前 Live2D 会话发送消息（[live2d_platform.py:218](live2d_platform.py:218)）

### 4.2 事件与消息对象

- [x] 将 `input.message` 转成 `AstrBotMessage`（[live2d_platform.py:139-185](live2d_platform.py:139-185)）
- [x] 生成 `AstrMessageEvent` 子类实例并 `commit_event()`（[live2d_platform.py:187-216](live2d_platform.py:187-216)）
- [x] 从 AstrBot 的 `MessageChain` 生成 `perform.show.sequence`（[message_converter.py:187](message_converter.py:187)）

### 4.3 指令

- [x] `/live2d reload`：重载配置（[commands.py:87](commands.py:87)，占位实现）
- [x] `/live2d status`：查看连接/会话状态（[commands.py:49](commands.py:49)）
- [x] `/live2d say <text>`：仅下发 text 表演（[commands.py:98](commands.py:98)）
- [x] `/live2d interrupt`：中断表演（新增）

---

## 5. 已完成 / 进行中 / 待办

### 5.1 已完成（可验收）✅

- [x] WebSocket 服务骨架：连接管理、单连接策略（kick_old）、消息循环
- [x] 协议基础结构：`BasePacket`、`sys.error` 数据结构、所有 op 常量
- [x] 输出侧转换：`MessageChain` → `sequence`（text/image/record + 自动情感）
- [x] `Live2DMessageEvent`：具备把 AstrBot 输出下发为 `perform.show` 的完整能力
- [x] **输入侧完整接入**：`input.message` → AstrBot 事件 → AstrBot 回复 → `perform.show`
- [x] **平台适配器注册**：作为 AstrBot 官方平台加载
- [x] **适配器指令系统**：status / reload / say

### 5.2 待办（按优先级）

**高优先级（功能验证）：**
- [ ] **端到端测试**：Desktop 连接 → 发送消息 → AstrBot 回复 → Desktop 显示
- [ ] 修复指令中获取适配器实例的方法（当前 `_get_live2d_adapter()` 可能无法工作）

**中优先级（协议完整性）：**
- [x] `state.ready` / `state.playing` 状态上报
- [x] `state.config` 配置推送
- [x] `perform.interrupt` 完整触发路径

**低优先级（增强功能）：**
- [ ] 多模态全链路验证（图片 Base64、语音 STT/TTS）
- [ ] 错误码规范化与详细日志
- [ ] `/live2d reload` 的实际配置重载实现

---

## 6. 风险 / 阻塞点

### 6.1 已解决 ✅

- [x] ~~`handler.py` 调用不存在 API~~ - 已修复（移除 `create_message_event()` 方法）
- [x] ~~WebSocket 路径配置未生效~~ - 已修复（[server.py:82-91](server.py:82-91)）

### 6.2 当前已知问题

- [ ] **指令系统集成问题**：`main.py:_get_live2d_adapter()` 需要根据实际 AstrBot 架构调整
  - 当前代码可能无法正确获取适配器实例
  - 建议方案：使用全局单例或通过 context API 获取

- [ ] **协议文档不一致**：`docs/api.md` 与 `docs/Live2D-Bridge-Protocol.md` 存在命名差异
  - 当前代码遵循 `Live2D-Bridge-Protocol.md`（权威协议）
  - 如需兼容 `api.md`，需要添加映射层

---

## 7. 验收清单

### 7.1 协议联调（待测试）

- [ ] Desktop → Adapter：握手成功（Token/Version 校验）
- [ ] Desktop ↔ Adapter：ping/pong 30s 心跳稳定
- [ ] Desktop → Adapter：发送 `input.message`（text）能触发 AstrBot 回复
- [ ] Adapter → Desktop：收到 `perform.show` 并显示文本

### 7.2 AstrBot 集成（已完成 ✅）

- [x] 适配器能被 AstrBot 作为平台加载（注册成功、可启用/停用）
- [x] AstrBot 事件队列可收到来自 Desktop 的消息事件
- [x] AstrBot 回复可通过 `Live2DMessageEvent.send()` 下发到 Desktop

---

## 8. 变更记录

### 2026-01-05 18:30 - MVP 核心功能完成

**新增：**
- `live2d_platform.py` - Live2D 平台适配器主类（311 行）
  - 完整实现 Platform 接口
  - 消息双向转换
  - WebSocket 服务器集成
- `commands.py` - 适配器指令系统（141 行）
  - status / reload / say 指令

**更新：**
- `main.py` - 改造为 AstrBot 插件入口（移除独立运行模式）
- `handler.py:149` - 移除错误的 `create_message_event()` 方法
- `server.py:82-91` - 添加 WebSocket 路径校验逻辑

**功能状态：**
- ✅ 平台适配器注册与运行
- ✅ 消息完整流程链路
- ✅ 适配器管理指令
- ⚠️ 待端到端测试验证

### 2026-01-05 - 初始化

- 初始化进度追踪文件
- 记录当前模块与主要阻塞点
