# 配置参考

在 AstrBot 管理面板中配置以下选项。

## 基础配置

| 配置项 | 类型 | 说明 | 可选值 | 默认值 |
|--------|------|------|--------|--------|
| `api_type` | 字符串 | API 类型 | `lolicon` / `atri` / `sexnyan` / `custom` / `all` | `lolicon` |
| `send_mode` | 字符串 | 发送模式 | `auto` / `image` / `forward` | `image` |
| `content_mode` | 字符串 | 内容模式 | `sfw` / `r18` / `mix` | `sfw` |
| `max_count` | 整数 | 单次最大图片数 | 1-10 | `10` |
| `max_replenish_rounds` | 整数 | 下载暂时失败时的同 URL 确认尝试次数，也是短缺时的补图轮次 | 1-3 | `3` |
| `cache_enabled` | 布尔值 | 是否复用本地发送缓存 | `true` / `false` | `true` |
| `exclude_ai` | 布尔值 | 是否排除 AI 生成图片 | `true` / `false` | `false` |

图片 URL 已返回但下载出现连接错误、HTTP 错误或超时时，插件会先按 `max_replenish_rounds` 对同一 URL 做可观测的确认重试。仍失败时才进入后续补图轮次或返回无结果，避免 CDN/反代短暂抖动被直接当成最终失败。

## HTML 卡片与防审核配置

| 配置项 | 类型 | 说明 | 可选值 | 默认值 |
|--------|------|------|--------|--------|
| `html_card_strategy` | 字符串 | HTML 卡片策略 | `never` / `fallback` / `always` | `fallback` |
| `napcat_stream_mode` | 字符串 | NapCat 流式上传策略 | `disabled` / `fallback` / `always` | `fallback` |
| `auto_revoke_r18` | 布尔值 | R18 图片是否自动撤回 | `true` / `false` | `false` |
| `r18_docx_mode` | 布尔值 | R18 是否使用 Docx 封装 | `true` / `false` | `true` |

### HTML 卡片策略详解

| 策略 | 说明 |
|------|------|
| `never` | 从不使用 HTML 卡片，直接发送原图 |
| `fallback`（默认） | 确认发送失败时自动降级为 HTML 卡片 |
| `always` | 总是使用 HTML 卡片包装发送 |

发送接口超时或 OneBot/NapCat 类适配器未返回 message id 时，插件会把结果标记为“可能仍在送达”，不会立刻触发 NapCat 流式或 HTML 卡片 fallback，避免原图稍后送达时又重复发送降级图片。明确抛出的发送异常仍会进入原有 fallback 链路。

## 模板覆盖配置

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `provider_overrides` | template_list | 可选覆盖 Lolicon/Atri 的默认图片尺寸、代理、UID、关键词、AI 过滤等设置 |
| `custom_api_configs` | template_list | 自定义图片 API 列表 |
| `tag_alias_templates` | template_list | 标签别名映射；添加后优先于旧文本格式 `tag_alias` |
| `message_overrides` | template_list | 只在需要自定义某条提示时添加，未添加时使用内置默认提示 |

## 访问控制配置

安全配置已从 `_conf_schema.json` 移到插件 WebUI 的 Dashboard 访问控制标签页。页面支持：

- 设置 Setu/运势的用户、群组访问模式：`none` / `blacklist` / `whitelist`
- 用表格新增、编辑、删除用户/群组黑白名单
- 按功能、对象类型、名单类型筛选并搜索 ID 或备注

访问控制数据写入插件数据目录，不再写回全局配置面板。旧版 `safety.*` 配置会在初始化时导入一次，确保已有黑白名单和模式不丢失。

### 访问控制模式说明

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `none` | 不启用该维度的黑白名单检查 | 不限制该维度 |
| `blacklist` | 命中黑名单即拒绝 | 只屏蔽少数对象 |
| `whitelist` | 不在白名单即拒绝 | 仅允许特定对象 |

### 判定规则

- 用户和群组分别按各自模式独立判定；任一维度拒绝则最终拒绝。
- `setu` 与 `fortune` 的名单和模式互不影响。
- 用户白名单**不再**具有"跳过群组限制"的特权。
- 当同一用户被"拉黑"后又"信任"（或反向操作）时，会自动从对立名单移除，保持互斥。

## 性能优化配置

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `napcat_stream_mode` | NapCat/OneBot 图片传输策略 | `fallback` |
| `cache_enabled` | 是否复用发送缓存 | `true` |
| `max_replenish_rounds` | 图片 URL 短暂下载失败时的确认重试和补图轮次 | `3` |

## 配置示例

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
  "messages": {
    "message_overrides": [
      {
        "__template_key": "message",
        "message_key": "fetch_failed",
        "enabled": true,
        "text": "获取图片失败，请稍后再试"
      }
    ]
  }
}
```
