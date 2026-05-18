# AGENTS.md - astrbot_plugin_setu

AstrBot plugin for Setu image delivery, session overrides, access control, and
fortune cards backed by image providers.

## Communication Language

Must communicate with the user in Chinese (中文). Keep engineering updates concise
and grounded in local code.

## Project Overview

- **Language**: Python 3.10+ compatible code style with `from __future__ import annotations`
- **Framework**: AstrBot v4.24.x plugin system
- **Architecture**: DDD-style layered `src/` package
- **Runtime features**: random image fetching, provider proxy rewrite, send-mode fallback,
  Setu/Fortune access control, per-session config overrides, Fortune card rendering
- **Current release focus**: v2.0.2 restores Fortune daily pre-rendered image cache and
  prevents AstrBot core test runtime data from being written under the plugin directory

## Required Skills

Use `$skill-astrbot-dev` for AstrBot plugin structure, decorators/hooks, lifecycle,
config schema, message flow, platform adapters, HTML rendering, and LLM tools. If
docs and source disagree, trust source.

Use `$github` for issues, PRs, CI runs, and advanced repository queries through
`gh`.

## Directory Structure

```text
main.py                         # AstrBot Star entrypoint and command registration
metadata.yaml                   # Plugin metadata and release version
_conf_schema.json               # AstrBot config UI schema
CHANGELOG.md                    # Release changelog
README.md                       # User-facing usage docs
AGENTS.md                       # Agent-facing repository guide
src/
  application/
    ports/                      # Repository/provider interfaces
    session_config/             # Session override DTOs, keys, service
    setu/                       # Setu use cases and DTOs
    settings.py                 # Config snapshot access for application layer
  domain/
    access_control/             # Access policy and decision service
    fortune/                    # Fortune entities, generation service, value objects
    setu/                       # Setu request/tag domain objects
  infrastructure/
    astrbot/                    # AstrBot adapters, command handlers, renderer, Web API
    persistence/                # JSON/SQLite repositories
    providers/                  # Lolicon, Atri, custom, multi-provider adapters
    sending/                    # Image sender, strategies, NapCat stream upload
  shared/
    config/                     # Pydantic config models and message defaults
    logging.py                  # Plugin logger wrapper
    send_cache.py               # Stable send cache before adapter delivery
pages/
  sessionConfig/                # WebUI page for session overrides
templates/
  fortune.html                  # Legacy-compatible Fortune card template
  res/fonts/                    # Embedded Fortune card fonts
tests/                          # pytest + pytest-asyncio tests
skills/                         # Plugin-specific Codex/AstrBot skills
```

## Key Conventions

### Main Entry

`main.py` should stay focused on AstrBot registration, singleton initialization,
and forwarding into infrastructure command handlers. Keep reusable orchestration in
`application/` or `infrastructure/` modules.

Command handlers must be `async def` and yield AstrBot results. Prefer
`event.plain_result(...)` and `event.chain_result(...)`; do not assume every event
has `event.result(...)`.

### Setu Flow

Setu fetching is routed through `GetSetuImagesUseCase`, provider ports, and
`ImageSender`. Empty payloads should not carry hardcoded use-case notices; command
handlers resolve configurable messages instead.

Provider behavior belongs in `src/infrastructure/providers/`. Pixiv proxy rewrite
and provider diagnostics should stay observable through structured logs.

### Fortune Flow

`FortuneCommandHandler` owns AstrBot-specific Fortune behavior. `FortuneService`
owns domain generation and repository-backed record lifecycle only.

Fortune card rendering is image-first:

- `fortune_command` gets or creates today's `FortuneRecord`
- `_render_fortune_image()` reuses cached card bytes when present
- otherwise it fetches a background image, renders `templates/fortune.html`, and
  saves the rendered card through `FortuneService.update_image_cache()`
- fallback to plain text is allowed only when background fetching or rendering fails

`fortune.auto_refresh` means recently active users should be handled after day
rollover. v2.0.2 behavior is to pre-generate records and cache rendered card images,
not just write database rows.

### Message Configuration

All user-facing prompts should go through `MessagesConfig` / `MessageTextConfig`
and `resolve_message()`. Avoid handler-local hardcoded fallback dictionaries; use a
minimal generic fallback only when config is unavailable.

When adding a message key, keep these files in sync:

- `_conf_schema.json`
- `src/shared/config/models.py`
- focused tests under `tests/infrastructure/` or `tests/shared/`

### Runtime Data

Do not write runtime files into the plugin source directory. Use
`StarTools.get_data_dir(self.name)` in plugin runtime and temp pytest directories in
tests.

`tests/conftest.py` pins `ASTRBOT_ROOT` before importing `astrbot.core`, because
AstrBot defaults its root to `os.getcwd()` and otherwise creates
`data/cmd_config.json` and `data/t2i_templates/` under the plugin checkout.

Never commit local runtime artifacts such as:

- `data/`
- `assets/*.png` generated during manual checks
- downloaded image caches
- local AstrBot runtime config

### WebUI

WebUI pages live under `pages/<page_name>/index.html`. The current session config
page uses plain JS and AstrBot's injected bridge. APIs are registered through
`context.register_web_api(...)` from `src/infrastructure/astrbot/session_config_api.py`.

### GitHub Actions

Workflow files must live under `.github/workflows/`. Do not add workflow files under
`.github/workflow/`; GitHub Actions will not load that path.

## Build, Test, and Development Commands

```bash
python -m pip install -e ".[dev]"
python -m pip install -U astrbot
PYTHONPATH=/path/to/data/plugins python -m pytest
PYTHONPATH=/path/to/data/plugins python -m pytest tests/infrastructure/test_fortune_pregeneration.py -q
RUFF_CACHE_DIR=.ruff_cache python -m ruff check .
python -m ruff format .
python -m py_compile main.py src/**/*.py tests/**/*.py
```

If parent cache directories are not writable, set `RUFF_CACHE_DIR=.ruff_cache`.

## Testing Guidelines

Use pytest and pytest-asyncio. Name files `test_*.py`, classes `TestFeatureName`,
and methods `test_behavior`.

Reuse fixtures from `tests/conftest.py` for AstrBot config, events, providers, and
temporary data directories. Add focused tests when touching:

- provider behavior and URL rewriting
- sender fallback logic
- message config keys and placeholder rendering
- Fortune record/cache lifecycle
- SQLite migrations or repository queries
- `main.py` command routing and trigger de-duplication

## Code Rules

- Use 4-space indentation and type hints.
- Use `snake_case` for functions/modules, `PascalCase` for classes, and
  `UPPER_SNAKE_CASE` for constants.
- New Python modules should start with a module docstring when useful, then
  `from __future__ import annotations`.
- Logger formatting should use `%s` placeholders, not `{}` interpolation.
- Keep comments rare and useful; explain non-obvious behavior, not line-by-line actions.
- Do not add external dependencies without updating `requirements.txt` and documenting why.

## Release Rules

Use semantic versioning and keep release files synchronized:

- Patch bump: fixes, compatibility adjustments, tests/tooling corrections
- Minor bump: new user-facing features, new config fields, new APIs or WebUI features
- Major bump: breaking config/data/API changes or migrations requiring manual action

For every release bump:

- update `metadata.yaml` `version:`
- add a new top `CHANGELOG.md` section
- keep `_conf_schema.json`, `src/shared/config/models.py`, README examples, and tests
  synchronized when config changes

## Commit and PR Guidelines

Recent history follows Conventional Commits, for example `fix(fortune): ...`,
`feat(safety): ...`, `refactor: ...`, `docs: ...`, and `chore: ...`.

Keep PRs focused. Include:

- motivation and user-visible behavior
- core files changed
- tests or checks run
- migration notes if config, database, or runtime data behavior changes

Do not include unrelated working-tree changes, generated caches, local AstrBot data,
or downloaded images in commits.
