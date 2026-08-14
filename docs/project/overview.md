# 项目概览

## 插件定位

`astrbot_plugin_setu` 是一个面向 AstrBot 的随机图片插件。它的核心职责是提供稳定的多源图片获取、平台适配发送和访问控制：

- 管理多 API 图片供应商（Lolicon、Atri、SexNyan、自定义）
- 按标签、数量、内容模式获取图片
- 适配不同平台发送策略（图片直接发送/合并转发、随机本子 PDF/ZIP 文件、HTML 卡片、NapCat 流式、Docx 封装）
- 管理会话级配置覆盖和 Setu/Fortune 访问控制
- 提供运势卡片生成和预缓存
- 为 AstrBot 的 AI agent 提供图片获取和配置管理工具

## 为什么保持这个定位

这个插件在 v1.x 阶段经历过几类问题：

- 图片获取、发送策略、防审核和访问控制逻辑混在一起
- 配置散落在多处，WebUI 改了不生效
- 一个 provider 改动影响整个发送链路

v2.0 的目标是把容易回归的部分保护起来：

1. **图片获取稳定**
   - 多 provider 统一端口
   - provider 诊断日志
   - 代理和 URL 改写
2. **发送可靠**
   - 多策略自动降级
   - HTML 卡片 fallback
   - NapCat 流式上传
   - 磁盘缓存和并发下载
3. **访问控制独立**
   - Setu 和 Fortune 独立管控
   - 用户/群组双维度
   - WebUI 管理页
4. **消息配置统一**
   - 所有提示文案走 `MessagesConfig`
   - 支持占位符渲染
   - 不再硬编码提示

## 当前能力边界

### 插件负责

- 多 API 图片获取（Lolicon、Atri、SexNyan、自定义、多 API 轮询）
- 标签搜索和别名映射
- 多平台图片发送和防审核降级
- 会话级配置覆盖
- Setu/Fortune 访问控制（黑白名单管理）
- 运势卡片生成和预缓存
- LLM 工具调用

### 插件不再负责

- 旧版 `aiohttp` 依赖（已迁移到 `httpx`）
- 旧版 `safety.*` 配置直接管理（已迁移到 Dashboard 访问控制标签页）
- 旧版硬编码提示文案（已迁移到 `MessagesConfig`）

## 当前用户入口

插件当前通过三类入口使用：

1. 聊天命令
   - `/setu` 系列命令
   - `/session_config` 系列命令
   - 运势相关命令
   - 黑白名单管理命令
2. AI tools
   - `get_setu_image`
   - `get_session_config` / `set_session_config` / `clear_session_config`
   - `get_today_fortune` / `refresh_my_fortune` / `refresh_group_fortune` / `refresh_all_fortune`
3. Plugin Pages
   - `dashboard` 统一管理页
   - Dashboard 内含会话配置和访问控制两个标签页

## 当前实现取向

1. 把"可靠发送"放在第一优先级——多策略降级、HTML 卡片 fallback、NapCat 流式。
2. 把"提示可配置"收敛到 `MessagesConfig`——不再硬编码，支持占位符。
3. 把"访问控制"前移到独立 WebUI 页面——双维度独立判定，数据不回写全局配置。

## 为什么保留 DDD 分层

这里继续保留 DDD 分层，因为这个插件天然有多类变化频率完全不同的东西：

- 领域规则：标签解析、访问控制策略、运势等级、消息配置
- 用例编排：获取图片、发送图片、刷新运势、管理名单
- 基础设施细节：AstrBot 命令适配、provider HTTP 调用、sender 平台差异、SQLite/JSON 持久化
- 外部接口：聊天命令、Web API、LLM tools、Plugin Pages

如果把这些混在一起，最直接的后果是：

- provider 差异反向侵入获取逻辑
- sender 平台差异反向侵入命令层
- 消息配置散落在各个 handler

当前分层结构的价值在于：

- `domain` 保护稳定语义（标签解析、访问控制、运势等级）
- `application` 收口用例（获取图片、发送图片、运势管理）
- `infrastructure` 吞掉 AstrBot / 平台 / 存储 / provider 差异
- `shared` 承载配置模型和通用工具

## 对维护者最重要的事实

本页只保留定位与取舍，不维护细节清单。修改前按主题查对应章节：

- 启动、分层、配置职责：[`architecture.md`](./architecture.md)
- 命令和配置详情：README
