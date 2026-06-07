# CLAUDE.md — astrbot_plugin_setu

本文件只保留 Claude 协作入口规则。业务细节按需阅读 `docs/project/`，开发维护规则优先阅读 `docs/dev/maintenance.md`。

## 沟通语言

必须使用中文与用户交流。

## 项目形态

- **语言**: Python 3.10+
- **框架**: AstrBot plugin system
- **架构**: DDD 分层
- **许可证**: AGPL

主要目录：

```text
src/domain/          领域实体、值对象、标签解析、访问控制
src/application/     用例、DTO、端口接口、会话配置服务
src/infrastructure/  配置、持久化、provider、sender、AstrBot 适配
src/shared/          配置模型、日志、发送缓存
pages/               Plugin Pages 前端（统一 dashboard 页面）
templates/           运势卡片 HTML 模板与字体
tests/               单元测试、集成测试与测试夹具
```

## 阅读入口

- 任何改动前先看：`docs/dev/maintenance.md`
- 需要业务背景时看：`docs/project/overview.md`
- 修改模块关系和启动分工时看：`docs/project/architecture.md`
- 修改消息配置、提示文案或占位符时看：`src/shared/config/models.py`
- 修改 provider 适配或 sender 策略时看：`src/infrastructure/providers/` 和 `src/infrastructure/sending/`

## 技能

如果当前会话可用，修改本插件时优先参考 `astrbot-dev-skill`。它对 AstrBot 命令装饰器、Plugin Pages bridge、统一会话 ID 和平台适配边界有帮助。

## 硬约束

- 不要把业务逻辑编排塞进 `main.py`；保持注册和路由专注。
- 插件运行数据必须通过 `StarTools.get_data_dir(self.name)` 获取，不要硬编码路径。
- 从插件目录本地调试时，不要创建或使用 `<plugin>/data` 作为运行态目录。
- 所有用户可见提示必须走 `MessagesConfig` / `resolve_message()`，不要在 handler 内硬编码提示文案。
- 其他领域值、平台行为和配置边界不要写进本文件，放到 `docs/project/` 或 `docs/dev/`。

## 文档纪律

- 文档是改动的一部分。代码改动导致现有说明失真时，必须在同一 patch 中更新相关 `docs/`。
- 命令行为、Plugin Pages 行为、配置语义、provider、sender、消息配置、访问控制变化时，通常需要更新文档。
- repo-wide 约束或 agent 入口说明变化时，同步更新 `AGENTS.md` 和 `CLAUDE.md`。

## 测试与检查命令

从插件目录运行：

```bash
PYTHONPATH=/path/to/data/plugins python -m pytest tests/ -v
PYTHONPATH=/path/to/data/plugins python -m pytest tests/infrastructure/test_fortune_pregeneration.py -q
RUFF_CACHE_DIR=.ruff_cache python -m ruff check .
python -m ruff format .
python -m py_compile main.py src/**/*.py tests/**/*.py
```

从 AstrBot 项目根目录运行：

```bash
uv run ruff format data/plugins/astrbot_plugin_setu
uv run ruff check data/plugins/astrbot_plugin_setu
```

## 维护

当架构、命令面、发送策略、配置路径或测试 / lint 流程变化时，同步更新 `AGENTS.md` 和 `CLAUDE.md`。

## 篇幅约束

`AGENTS.md` 和 `CLAUDE.md` 均不得超过 100 行；内容过长时拆入 `docs/dev/` 或 `docs/project/`。
