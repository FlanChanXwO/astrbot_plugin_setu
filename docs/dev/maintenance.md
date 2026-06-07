# 维护规则

本文面向维护者和协作 agent，记录开发时需要遵守的仓库级规则。业务细节不要继续塞进 `AGENTS.md` 或 `CLAUDE.md`，应拆到 `docs/project/` 的对应主题文档。

## 文档同步

- 文档不是可选收尾。
- 行为、边界、入口、配置、流程、架构或维护约定变化时，必须同步更新对应文档。
- 下列变化默认需要更新文档：
  - 命令行为或参数变化
  - Plugin Pages 交互变化
  - 配置项、默认值或兼容规则变化
  - provider、sender、消息配置算法变化
  - 访问控制判定逻辑变化
  - 运势预生成或缓存策略变化
- 修改 repo-wide 维护规则或 agent 入口约定时，同步更新 `AGENTS.md` 和 `CLAUDE.md`。

## 入口与分层

入口与分层事实统一维护在 [`../project/architecture.md`](../project/architecture.md)。本文件只记录维护要求：保持 `main.py` 专注注册和路由，业务规则、平台适配和入口适配不要互相污染。

## 本地路径

- 插件运行数据路径统一通过 `StarTools.get_data_dir(self.name)` 获取。
- 不要在插件源目录下创建运行态数据。
- 从插件目录本地调试时，不应创建或使用 `<plugin>/data` 作为运行态目录。
- `tests/conftest.py` 固定 `ASTRBOT_ROOT`，阻止 AstrBot 在插件目录创建运行时数据。

## 配置维护

- 配置模型文件是 `src/shared/config/models.py`。
- 新增配置项时，以下文件必须同步更新：
  - `_conf_schema.json`
  - `src/shared/config/models.py`
  - 相关测试
- 消息配置（`MessagesConfig`）新增 key 时，同步更新默认值和占位符文档。
- sender strategy 和 provider 参数的运行时语义见源码注释和 README，不要在维护文档里复制完整字段清单。

## 代码组织

- provider 行为属于 `src/infrastructure/providers/`。
- sender 行为属于 `src/infrastructure/sending/`。
- 消息配置解析属于 `src/shared/config/`。
- 不要把 provider 日志、sender 降级或消息解析散落到命令层或领域层。

## Plugin Pages 维护

- Plugin Pages 统一入口为 `pages/dashboard/index.html`。
- 左侧导航切换"会话配置"和"访问控制"两个标签页。
- CSS 位于 `pages/dashboard/css/`（`base.css`、`components.css`、`forms.css`、`dashboard.css`、`nav.css`）。
- JS 为原生 JS（Proxy 响应式 store），无框架依赖。
- 会话配置管理会话级覆盖，API 实现位于 `src/infrastructure/astrbot/session_config_api.py`。
- 访问控制管理黑白名单，API 实现位于 `src/infrastructure/astrbot/access_control_api.py`。
- API 注册通过 `context.register_web_api(...)`。
- 移动端通过汉堡按钮展开导航侧边栏。

## 测试与检查

常用命令见 [`testing.md`](./testing.md)。涉及下列行为时，优先补回归测试：

- 配置模型新增或变更
- 消息配置 key 和占位符解析
- provider 参数和 URL 构造
- sender 降级和 HTML 卡片 fallback
- 运势预生成和缓存生命周期
- 访问控制判定和黑白名单互斥
- 命令路由和触发去重

## 仓库体积

- 插件仓库总大小不宜过大。
- 不要把大型二进制资源（字体、模型权重、样例图片）纳入仓库。
- 模板字体（`templates/res/fonts/`）当前为嵌入式资源，后续如有体量增长应改为运行时下载。

## 已移除能力

- 旧版 `safety.*` 配置仅在初始化时作为迁移来源读取一次；新数据以 `accessControl` 页面和插件数据目录为准。
- `aiohttp` 依赖已完全移除，统一使用 `httpx`。
- `use_httpx`、`tcp_connector_limit`、`tcp_connector_limit_per_host` 等旧配置项已移除。
