# 🌸 Setu 插件（astrbot_plugin_setu）

<div align="center">

<img src="https://raw.githubusercontent.com/FlanChanXwO/astrbot_plugin_setu/master/logo.png" width="400" alt="Setu 插件"/>

<br/>

<img src="https://count.getloli.com/@astrbot_plugin_setu?name=astrbot_plugin_setu&theme=rule34&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto" alt="Moe Counter">

**一个支持多平台、可自定义、带防审核机制的随机色图插件，支持多 API、HTML 卡片包装、LLM 工具调用。**

[![License: APGL](https://img.shields.io/badge/License-APGL-blue.svg)](https://opensource.org/licenses/agpl-3.0)
![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![AstrBot](https://img.shields.io/badge/AstrBot-%E2%89%A54.10.4-green)
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
        <img src="https://raw.githubusercontent.com/FlanChanXwO/astrbot_plugin_setu/master/assets/jrys_preview.png" width="400" alt="色图卡片预览3"/>
        <br/>
        <sub>基于色图驱动的今日运势</sub>
      </td>
    </tr>
  </table>
</div>

---

## ✨ 功能特性

- 🎨 **多 API 支持** - Lolicon、SexNyan、自定义 API 等
- 🖼️ **HTML 卡片包装** - 防止平台审核，支持自定义样式
- 🤖 **LLM 工具调用** - 可通过大模型自动获取色图
- 🏷️ **标签搜索** - 支持多标签、中文标签、模糊匹配
- 🔄 **多种发送模式** - 直接发送、合并转发、文件封装
- 🛡️ **防审核机制** - 图片混淆、延迟撤回、Docx 封装
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

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `api_type` | 字符串 | API 类型（lolicon/sexnyan/custom/all） | `lolicon` |
| `send_mode` | 字符串 | 发送模式（auto/image/forward） | `auto` |
| `content_mode` | 字符串 | 内容模式（sfw/r18/mix） | `sfw` |
| `max_count` | 整数 | 单次最大图片数 | `10` |
| `cache_enabled` | 布尔值 | 是否启用图片磁盘缓存 | `true` |
| `html_card_strategy` | 字符串 | HTML 卡片策略（never/fallback/always） | `fallback` |
| `auto_revoke_r18` | 布尔值 | R18 图片是否自动撤回 | `false` |
| `r18_docx_mode` | 布尔值 | R18 是否使用 Docx 封装 | `true` |
| `enable_range_download` | 布尔值 | 启用分段下载（高带宽优化） | `false` |
| `download_concurrent_limit` | 整数 | 并发下载限制 | `10` |

### 配置示例

```json
{
  "api_type": "lolicon",
  "send_mode": "auto",
  "content_mode": "mix",
  "max_count": 5,
  "cache_enabled": true,
  "html_card_strategy": "fallback",
  "auto_revoke_r18": true,
  "r18_docx_mode": false,
  "exclude_ai": false,
  "enable_range_download": false,
  "range_segments": 3,
  "range_download_threshold": 512,
  "download_concurrent_limit": 10,
  "download_timeout_seconds": 30
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
/setu_mode r18
```

- 数量范围支持中文数字
- 标签支持空格、逗号、顿号分隔
- `/setu_mode` 可切换内容模式

### LLM 工具调用

- 支持通过大模型自动调用色图工具
- 需在 AstrBot 配置好 LLM 提供商

### 高级用法

- **自定义 API**：可在配置中设置 `api_type` 为 `custom`，并填写自定义 API 地址和解析规则，实现对接任意第三方色图接口, 注意标签和分级筛选目前还是实验性阶段。
- **图片混淆**：如遇平台审核拦截，插件会自动尝试对图片进行字节级混淆重发，无需额外配置。
- **HTML 卡片策略**：`html_card_strategy` 提供三种模式：
  - `never`：从不使用 HTML 卡片，直接发送原图
  - `fallback`（默认）：发送失败时自动降级为 HTML 卡片
  - `always`：总是使用 HTML 卡片包装发送
- **自动撤回**：可通过 `auto_revoke_r18` 配置项开启 R18 图片的自动撤回，并可设置撤回延迟时间。
- **Docx 封装**：开启 `r18_docx_mode` 后，R18 图片将以 Word 文档形式发送，进一步规避平台审核。
- **磁盘缓存**：通过 `cache_enabled` 启用图片磁盘缓存，提升多次请求同一图片的响应速度。
- **多 API 策略**：支持 `all` 模式自动切换多 API，提升获取成功率。
- **标签与过滤**：支持多标签、中文标签、AI 过滤（`exclude_ai`），可灵活组合搜索条件。
- **性能优化**：
  - `enable_range_download`: 启用分段下载，将大图片分多段并行下载，适合高带宽服务器
  - `range_segments`: 分段数（推荐 2-4）
  - `range_download_threshold`: 分段下载阈值（KB），大于此值才启用分段
  - `download_concurrent_limit`: 并发下载限制，高带宽服务器可适当提高
  - `download_timeout_seconds`: 下载超时时间（秒）

更多详细配置和玩法请参考上方“配置项”表格及实际管理面板说明。

---

## 未来更新
- [ ] 更好的自定义API
- [ ] 新增一个作者自己的图库内置API，该图库的更新速度会比目前的图库API更快，并且跟随了当前版本潮流！
- [x] 一些基于色图的额外插件功能 (今日运势)
---

## 📄 开源协议

本项目基于 [APGL](LICENSE) 协议开源。

---
