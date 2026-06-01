# 测试与回归检查

## 基础命令

| 场景 | 工作目录 | 命令 |
| --- | --- | --- |
| Python 格式化 | AstrBot 根目录 | `uv run ruff format data/plugins/astrbot_plugin_setu` |
| Python lint | AstrBot 根目录 | `uv run ruff check data/plugins/astrbot_plugin_setu` |
| 全量 pytest | 插件目录 | `PYTHONPATH=/path/to/data/plugins python -m pytest tests/ -v` |
| 单文件测试 | 插件目录 | `PYTHONPATH=/path/to/data/plugins python -m pytest tests/infrastructure/test_fortune_pregeneration.py -q` |
| 编译检查 | 插件目录 | `python -m py_compile main.py src/**/*.py tests/**/*.py` |

> [!TIP]
> 如果上级缓存目录不可写，设置 `RUFF_CACHE_DIR=.ruff_cache` 后再运行 ruff。

## 分层验证矩阵

| 改动类型 | 最小检查 | 建议额外回归 | 关注点 |
| --- | --- | --- | --- |
| Python 业务逻辑 | 相关单元测试、`ruff check` | provider、sender、config model、message config | 不要只跑被改函数附近的测试。 |
| Plugin Pages | `node --check pages/*/app.js` | 手工验证 sessionConfig 页面加载、读写、重置 | 前端改动不要只看代码。 |
| 配置或迁移 | 相关配置测试 | `_conf_schema.json` 同步、`models.py` 同步、旧配置兼容 | 脏配置要能被容忍。 |
| sender / 媒体 | sender 单测、发送策略测试 | HTML 卡片降级、NapCat 流式、文件封装 | 不同平台行为差异要覆盖。 |
| 运势 / Fortune | fortune 相关单测 | 渲染、缓存、预生成、刷新命令 | 卡片渲染失败要能降级到文本。 |

## 高风险改动清单

| 改动 | 风险 | 建议 |
| --- | --- | --- |
| 命令注册或路由变化 | 破坏 AstrBot 命令解析或去重 | 补命令解析测试。 |
| sender 行为变化 | 平台吞图、媒体类型错误、fallback 丢失 | 至少覆盖直接发送和 HTML 卡片降级。 |
| 配置模型变化 | 启动失败或配置丢失 | 检查 `_conf_schema.json`、`models.py`、测试三件同步。 |
| 运势预生成逻辑 | 跨日缓存失效或卡片渲染失败 | 覆盖预生成和缓存命中路径。 |
| 消息配置变化 | 提示文案不生效或占位符渲染错误 | 覆盖所有 message key 的解析和 fallback。 |
| 访问控制判定 | 误拒或误放 | 覆盖用户/群组维度、黑白名单互斥。 |

## 回归检查清单

- [ ] `/setu` 命令在无结果时走配置提示而非硬编码文案。
- [ ] HTML 卡片 fallback 在原图发送失败时仍能触发。
- [ ] 运势卡片渲染失败时降级为纯文本。
- [ ] 会话配置读写不锁死（并发安全）。
- [ ] `tests/conftest.py` 固定的 `ASTRBOT_ROOT` 仍能阻止插件目录污染。
- [ ] 访问控制黑白名单互斥逻辑正常。
