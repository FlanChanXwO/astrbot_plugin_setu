# 🌸 Setu 插件（astrbot_plugin_setu）

<div align="center">

<img src="https://raw.githubusercontent.com/FlanChanXwO/astrbot_plugin_setu/master/logo.png" width="400" alt="Setu 插件"/>

<br/>

<img src="https://count.getloli.com/@astrbot_plugin_setu?name=astrbot_plugin_setu&theme=rule34&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto" alt="Moe Counter">

**一个支持多平台、可自定义、带防审核机制的随机色图插件，支持多 API、会话级配置、LLM 工具调用。**

[![License: APGL](https://img.shields.io/badge/License-APGL-blue.svg)](https://opensource.org/licenses/agpl-3.0)
![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![AstrBot](https://img.shields.io/badge/AstrBot-%E2%89%A54.24.0-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)

</div>

本插件完全开源免费，欢迎 Issue 和 PR。

---

## 📸 预览

<div align="center">
  <table>
    <tr>
      <td align="center">
        <img src="https://raw.githubusercontent.com/FlanChanXwO/astrbot_plugin_setu/master/assets/img_ob_preview.png" width="400" alt="色图卡片预览1"/>
        <br/>
        <sub>HTML 卡片包装提高成功率</sub>
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/FlanChanXwO/astrbot_plugin_setu/master/assets/merge_send_preview.png" width="400" alt="色图卡片预览2"/>
        <br/>
        <sub>多图合并转发</sub>
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/FlanChanXwO/astrbot_plugin_setu/master/assets/tag_search_preview.png" width="400" alt="色图卡片预览3"/>
        <br/>
        <sub>自定义标签搜索</sub>
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/FlanChanXwO/astrbot_plugin_setu/master/assets/jrys_preview.png" width="400" alt="今日运势卡片预览"/>
        <br/>
        <sub>基于色图驱动的今日运势</sub>
      </td>
    </tr>
  </table>
</div>

---

## ✨ 功能特性

- 🎨 **多 API 支持** - Lolicon、SexNyan、自定义 API 等
- 🧩 **分层架构** - `application` / `domain` / `infrastructure` / `shared` 清晰分离
- 🖼️ **HTML 卡片包装** - 防止平台审核，支持自定义样式
- 🤖 **LLM 工具调用** - 可通过大模型自动获取色图
- 🏷️ **标签搜索** - 支持多标签、中文标签、模糊匹配
- 🔄 **多种发送模式** - 直接发送、合并转发、文件封装
- 🛡️ **防审核机制** - HTML 卡片 fallback、NapCat 流式上传、延迟撤回、Docx 封装
- ⚡ **性能优化** - 并发下载、磁盘缓存、自动补图、httpx、分段下载
- 🌐 **多平台适配** - 兼容 AstrBot 支持的所有平台

---

## 📦 安装

### 方式一：通过 AstrBot 插件市场安装（推荐）

在 AstrBot 管理面板中搜索 `astrbot_plugin_setu` 并安装。

### 方式二：手动安装

1. 克隆本仓库到 AstrBot 的插件目录：
   ```bash
   cd AstrBot/data/plugins
   git clone https://github.com/FlanChanXwO/astrbot_plugin_setu.git
   ```
2. 重启 AstrBot 或重载插件

---

## 🛠️ 配置项

在 AstrBot 管理面板中配置以下选项：

### 基础配置

| 配置项 | 类型 | 说明 | 可选值 | 默认值 |
|--------|------|------|--------|--------|
| `api_type` | 字符串 | API 类型 | `lolicon` / `atri` / `sexnyan` / `custom` / `all` | `lolicon` |
| `send_mode` | 字符串 | 发送模式 | `auto` / `image` / `forward` | `auto` |
| `content_mode` | 字符串 | 内容模式 | `sfw` / `r18` / `mix` | `sfw` |
| `max_count` | 整数 | 单次最大图片数 | 1-20 | `10` |
| `cache_enabled` | 布尔值 | 是否复用本地发送缓存 | `true` / `false` | `true` |
| `exclude_ai` | 布尔值 | 是否排除 AI 生成图片 | `true` / `false` | `false` |

### HTML 卡片与防审核配置

| 配置项 | 类型 | 说明 | 可选值 | 默认值 |
|--------|------|------|--------|--------|
| `html_card_strategy` | 字符串 | HTML 卡片策略 | `never` / `fallback` / `always` | `fallback` |
| `napcat_stream_mode` | 字符串 | NapCat 流式上传策略 | `disabled` / `fallback` / `always` | `fallback` |
| `auto_revoke_r18` | 布尔值 | R18 图片是否自动撤回 | `true` / `false` | `false` |
| `r18_docx_mode` | 布尔值 | R18 是否使用 Docx 封装 | `true` / `false` | `true` |

### 性能优化配置

| 配置项 | 类型 | 说明 | 可选值 | 默认值 |
|--------|------|------|--------|--------|
| `enable_range_download` | 布尔值 | 启用分段下载（高带宽优化） | `true` / `false` | `false` |
| `range_segments` | 整数 | 分段下载段数 | 2-8 | `3` |
| `range_download_threshold` | 整数 | 分段下载阈值（KB） | > 0 | `512` |
| `download_concurrent_limit` | 整数 | 并发下载限制 | 1-50 | `10` |
| `download_timeout_seconds` | 整数 | 下载超时时间（秒） | 5-300 | `30` |

### 访问控制配置（2.0.0）

> 安全配置统一位于 `safety` 下，且 `setu` / `fortune` 完全独立。

| 配置项 | 类型 | 说明 | 可选值 | 默认值 |
|--------|------|------|--------|--------|
| `setu_user_access_control_mode` | 字符串 | 色图-用户访问控制模式 | `none` / `blacklist` / `whitelist` | `none` |
| `setu_group_access_control_mode` | 字符串 | 色图-群组访问控制模式 | `none` / `blacklist` / `whitelist` | `none` |
| `setu_blocked_users` | 列表 | 色图用户黑名单 | 字符串数组 | `[]` |
| `setu_whitelist_users` | 列表 | 色图用户白名单 | 字符串数组 | `[]` |
| `setu_blocked_groups` | 列表 | 色图群组黑名单 | 字符串数组 | `[]` |
| `setu_whitelist_groups` | 列表 | 色图群组白名单 | 字符串数组 | `[]` |
| `fortune_user_access_control_mode` | 字符串 | 运势-用户访问控制模式 | `none` / `blacklist` / `whitelist` | `none` |
| `fortune_group_access_control_mode` | 字符串 | 运势-群组访问控制模式 | `none` / `blacklist` / `whitelist` | `none` |
| `fortune_blocked_users` | 列表 | 运势用户黑名单 | 字符串数组 | `[]` |
| `fortune_whitelist_users` | 列表 | 运势用户白名单 | 字符串数组 | `[]` |
| `fortune_blocked_groups` | 列表 | 运势群组黑名单 | 字符串数组 | `[]` |
| `fortune_whitelist_groups` | 列表 | 运势群组白名单 | 字符串数组 | `[]` |

#### 访问控制模式说明

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `none` | 不启用该维度的黑白名单检查 | 不限制该维度 |
| `blacklist` | 命中黑名单即拒绝 | 只屏蔽少数对象 |
| `whitelist` | 不在白名单即拒绝 | 仅允许特定对象 |

#### 判定规则（当前实现）

- 用户和群组分别按各自模式独立判定；任一维度拒绝则最终拒绝。
- `setu` 与 `fortune` 的名单和模式互不影响。
- 用户白名单**不再**具有“跳过群组限制”的特权。
- 当同一用户被“拉黑”后又“信任”（或反向操作）时，会自动从对立名单移除，保持互斥。

#### 兼容迁移（旧键 -> 新键）

- `safety.setu_access_control_mode` -> `safety.setu_user_access_control_mode` + `safety.setu_group_access_control_mode`
- `safety.fortune_access_control_mode` -> `safety.fortune_user_access_control_mode` + `safety.fortune_group_access_control_mode`

> 旧键当前仍兼容读取，但 `v2.0.0` 起主实现已完全转到新键。

### 配置示例

```json
{
  "setu_general": {
    "api_type": "lolicon",
    "content_mode": "mix",
    "max_count": 5
  },
  "delivery": {
    "send_mode": "auto",
    "auto_revoke_r18": true,
    "r18_docx_mode": false
  },
  "performance": {
    "enable_range_download": false,
    "range_segments": 3,
    "range_download_threshold": 512,
    "download_concurrent_limit": 10,
    "download_timeout_seconds": 30
  },
  "safety": {
    "setu_user_access_control_mode": "blacklist",
    "setu_group_access_control_mode": "none",
    "setu_blocked_users": [],
    "setu_whitelist_users": [],
    "setu_blocked_groups": [],
    "setu_whitelist_groups": [],
    "fortune_user_access_control_mode": "none",
    "fortune_group_access_control_mode": "whitelist",
    "fortune_blocked_users": [],
    "fortune_whitelist_users": [],
    "fortune_blocked_groups": [],
    "fortune_whitelist_groups": []
  }
}
```

---

## 📝 使用方法

### 基础命令

发送以下任一指令即可获取色图：

```
来一份色图
来三份白丝瑟图
来9份白丝 萝莉色图
来二份白丝，萝莉色图
来一份白丝,萝莉色图
/setu 白丝 萝莉
/setu 3 白丝
/setu 4 白丝 萝莉
/session_config set setu.content_mode r18
```

- 数量范围支持中文数字
- 标签支持空格、逗号、顿号分隔
- `/session_config` 统一管理当前会话的覆盖配置

### v2.0.0 更新摘要

- 运势管理命令收敛为更少的统一入口，旧命令保留兼容别名
- provider / sender / fallback 日志补全，方便定位“有 URL 但发不出去”或“provider 无结果”的问题
- 反代配置读取、provider 重建、插件配置来源修正，减少 WebUI 改配置后不生效的问题

### 会话配置命令（管理员设置）

会话覆盖配置会写入插件数据目录下的 `session_overrides.json`，不会修改全局 WebUI 配置。
也可以在插件 WebUI 的 `sessionConfig` 页面集中管理所有群聊/私聊会话覆盖。

```
/session_config get
/session_config get setu.content_mode
/session_config get json
/session_config set setu.content_mode r18
/session_config set setu.r18_docx true
/session_config set setu.auto_revoke false
/session_config set setu.send_mode forward
/session_config set fortune.tags 白丝,猫耳
/session_config clear setu.send_mode
/session_config clear
```

可用配置项：`setu.content_mode`、`setu.r18_docx`、`setu.auto_revoke`、`setu.send_mode`、`fortune.tags`、`fortune.content_mode`。

### 黑白名单管理命令（管理员）

通过以下命令可动态管理黑白名单（配置会自动持久化）。

#### 色图用户黑白名单

| 命令 | 说明 | 示例 |
|------|------|------|
| `/拉黑色图用户 @用户` | 将用户加入色图黑名单（必须AT） | `/拉黑色图用户 @小明` |
| `/解除色图拉黑 @用户` | 将用户从色图黑名单移除（必须AT） | `/解除色图拉黑 @小明` |
| `/信任色图用户 @用户` | 将用户加入色图白名单（必须AT） | `/信任色图用户 @小明` |
| `/取消色图信任 @用户` | 将用户从色图白名单移除（必须AT） | `/取消色图信任 @小明` |

#### 运势用户黑白名单

| 命令 | 说明 | 示例 |
|------|------|------|
| `/运势用户 拉黑 @用户` | 将用户加入运势黑名单（必须AT） | `/运势用户 拉黑 @小明` |
| `/运势用户 解黑 @用户` | 将用户从运势黑名单移除（必须AT） | `/运势用户 解黑 @小明` |
| `/运势用户 信任 @用户` | 将用户加入运势白名单（必须AT） | `/运势用户 信任 @小明` |
| `/运势用户 取消信任 @用户` | 将用户从运势白名单移除（必须AT） | `/运势用户 取消信任 @小明` |

#### 群组功能开关

| 命令 | 说明 | 示例 |
|------|------|------|
| `/开启色图` | 在本群开启色图功能（移出色图群组黑名单） | `/开启色图` |
| `/关闭色图` | 在本群关闭色图功能（加入色图群组黑名单） | `/关闭色图` |
| `/运势开关 开` | 在本群开启运势功能（移出运势群组黑名单） | `/运势开关 开` |
| `/运势开关 关` | 在本群关闭运势功能（加入运势群组黑名单） | `/运势开关 关` |

#### 运势刷新

| 命令 | 说明 | 示例 |
|------|------|------|
| `/运势刷新` | 刷新自己的今日运势 | `/运势刷新` |
| `/运势刷新 本群` | 刷新当前群今日运势 | `/运势刷新 本群` |
| `/运势刷新 全局` | 刷新全局今日运势 | `/运势刷新 全局` |

**注意：**
- 以上命令仅限管理员或超级管理员使用。
- 用户类命令必须通过 `@` 指定目标用户，不支持直接输入用户 ID。
- 群组命令仅作用于当前群。
- 白名单/黑名单会自动保持互斥（同一功能下不会同时存在）。
- 旧命令 `/开启运势`、`/关闭运势`、`/拉黑运势用户`、`/解除运势拉黑`、`/信任运势用户`、`/取消运势信任`、`/刷新今日运势`、`/刷新本群今日运势`、`/刷新全局今日运势` 仍可继续使用。

#### 安全配置示例（`safety`）

```json
{
  "setu_user_access_control_mode": "blacklist",
  "setu_group_access_control_mode": "none",
  "setu_blocked_users": ["10001"],
  "setu_whitelist_users": [],
  "setu_blocked_groups": ["20001"],
  "setu_whitelist_groups": [],
  "fortune_user_access_control_mode": "none",
  "fortune_group_access_control_mode": "whitelist",
  "fortune_blocked_users": [],
  "fortune_whitelist_users": ["10002"],
  "fortune_blocked_groups": [],
  "fortune_whitelist_groups": ["20002"]
}
```

### LLM 工具调用

- 支持通过大模型自动调用色图工具
- 需在 AstrBot 配置好 LLM 提供商

#### 可用 LLM 工具清单（完整）

> 说明：以下工具名为插件内部注册名。权限类工具在非管理员场景会返回权限不足提示。
> 文档中的"超级管理员"即常见简称"超管"。

##### Setu 工具

| 工具名 | 作用 | 参数 | 权限 |
|---|---|---|---|
| `get_setu_image` | 获取并发送随机图片 | `count: integer`（数量）, `tags: string[]`（标签） | 普通用户可用 |

##### 会话配置工具

| 工具名 | 作用 | 参数 | 权限 |
|---|---|---|---|
| `get_session_config` | 查看当前会话全部配置或单个 key 的生效值 | `key?: string` | 普通用户可用 |
| `set_session_config` | 设置当前会话一个覆盖配置 | `key: string`, `value: string` | 管理员/超级管理员 |
| `clear_session_config` | 清除当前会话一个覆盖配置，或清空全部覆盖 | `key?: string` | 管理员/超级管理员 |

##### 今日运势工具

| 工具名 | 作用 | 参数 | 权限 |
|---|---|---|---|
| `get_today_fortune` | 获取并发送今日运势（含运势图） | 无 | 普通用户可用 |
| `refresh_my_fortune` | 刷新"我的"今日运势 | 无 | 管理员 |
| `refresh_group_fortune` | 刷新当前群今日运势 | 无 | 管理员 |
| `refresh_all_fortune` | 刷新全局今日运势 | 无 | 超级管理员 |

##### 调用建议

- 需要"仅查看状态"时优先调用 `get_session_config`。
- 需要会话级覆写时使用 `set_session_config`；希望回到全局配置时使用 `clear_session_config`。
- 对于发送类工具，插件会直接把结果发送到当前会话，工具返回文本用于说明执行结果。

### 高级用法

| 功能 | 说明 | 配置方式 |
|------|------|----------|
| **自定义 API** | 设置 `api_type` 为 `custom`，填写自定义 API 地址和解析规则，实现对接任意第三方色图接口 | 配置面板 |
| **NapCat 流式上传** | 通过 `napcat_stream_mode` 控制本地图片文件的流式上传，默认普通发送失败后自动重试 | 配置面板 |
| **发送缓存** | 图片先落盘再发送；`cache_enabled` 控制是否复用未过期的本地文件，降低 original 大图内存压力 | 配置面板 |
| **多 API 策略** | 支持 `all` 模式自动切换多 API，提升获取成功率 | 设置 `api_type` 为 `all` |
| **标签与过滤** | 支持多标签、中文标签、AI 过滤（`exclude_ai`），可灵活组合搜索条件 | 配置面板 |

#### HTML 卡片策略详解

| 策略 | 说明 |
|------|------|
| `never` | 从不使用 HTML 卡片，直接发送原图 |
| `fallback`（默认） | 发送失败时自动降级为 HTML 卡片 |
| `always` | 总是使用 HTML 卡片包装发送 |

#### 性能优化参数说明

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `napcat_stream_mode` | NapCat/OneBot 图片传输策略：`fallback` 先普通发送，失败后流式上传；`always` 发送前先流式上传；`disabled` 不使用流式上传 | `fallback` |
| `cache_enabled` | 是否复用发送缓存。即使关闭复用，运行时仍会优先落盘发送，避免大图长期停留在内存中 | `true` |
| `enable_range_download` | 启用分段下载，将大图片分多段并行下载，适合高带宽服务器 | `false`（一般）/ `true`（高带宽） |
| `range_segments` | 分段数 | 2-4 |
| `range_download_threshold` | 分段下载阈值（KB），大于此值才启用分段 | 512 |
| `download_concurrent_limit` | 并发下载限制，高带宽服务器可适当提高 | 10 |
| `download_timeout_seconds` | 下载超时时间（秒） | 30 |

---

## 未来更新
- [ ] 更好的自定义 API
- [ ] 更细粒度的 provider 健康检查与降级策略
- [ ] 继续补全 WebUI 配置与诊断能力
---

## 📄 开源协议

 本项目基于 [AGPL](LICENSE) 协议开源。
