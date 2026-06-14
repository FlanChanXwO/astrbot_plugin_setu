# Plugin Pages 管理界面

插件通过 Plugin Pages 提供统一管理界面，可在 AstrBot 管理面板中访问。所有功能集中在一个 `pages/dashboard/` 页面中，通过左侧导航栏切换子标签页。

## 访问方式

在 AstrBot 管理面板的插件页面中找到 `astrbot_plugin_setu` 的 dashboard 入口。

## 会话配置标签页

管理会话级配置覆盖。

### 功能

- 查看所有会话的覆盖配置
- 为指定群聊/私聊设置覆盖配置
- 清除指定会话的覆盖配置
- 支持的覆盖项：`setu.content_mode`、`setu.r18_docx`、`setu.auto_revoke_scope`、`setu.send_mode`、`fortune.tags`、`fortune.content_mode`

### 布局

- 左侧会话列表：选择或新建会话
- 右侧编辑器：会话字段 + 配置覆盖卡片（每个 key 显示全局值、生效值和覆盖开关）

## 访问控制标签页

管理 Setu 和 Fortune 的访问控制。

### 功能

- 设置 Setu/运势的用户、群组访问模式：`none` / `blacklist` / `whitelist`
- 用表格新增、编辑、删除用户/群组黑白名单
- 按功能、对象类型、名单类型筛选并搜索 ID 或备注

### 布局

- 顶部模式选择：4 个下拉框分别控制 Setu 用户/群组和运势用户/群组的访问模式
- 中间表单：新增/编辑记录
- 底部表格：记录列表，支持筛选和搜索

## 技术实现

- 前端位于 `pages/dashboard/`，统一入口 `index.html`
- CSS 分为 `base.css`、`components.css`、`forms.css`、`dashboard.css`、`nav.css`
- JS 为原生 JS（Proxy 响应式 store），无框架依赖
- 侧边导航：桌面端固定左侧，移动端通过汉堡按钮展开
- Dashboard 运行在 AstrBot Plugin Pages iframe 内，依赖 `/api/plugin/page/bridge-sdk.js` 提供的 `window.AstrBotPluginPage`
- `index.html` 会在 `app.js` 前显式加载 bridge SDK；`app.js` 仍会动态等待 bridge 注入，避免 iframe 注入时序导致页面不可用
- 会话配置 API：`session-config`（GET/POST），实现位于 `src/infrastructure/astrbot/session_config_api.py`
- 访问控制 API：`access-control`（GET/POST），实现位于 `src/infrastructure/astrbot/access_control_api.py`
- 数据持久化到插件数据目录
- 旧版 `safety.*` 配置仅在初始化时导入一次

## 运行时约束

- 支持目标是 AstrBot 管理面板中的 Plugin Pages iframe，不保证直接用 `file://` 打开 `pages/dashboard/index.html`
- bridge 未注入或不是从 AstrBot Plugin Pages 打开时，页面会保留可见布局并弹出错误提示
- 开发环境可访问 `/api/plugin/page/content/astrbot_plugin_setu/dashboard/` 验证页面加载、标签切换、会话配置和访问控制接口

## 不负责

Plugin Pages 当前不负责：

- 新建订阅或图片请求
- 直接修改 AstrBot 全局配置
