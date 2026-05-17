# Repository Guidelines

## Project Structure & Module Organization

This is an AstrBot plugin. `main.py` centralizes AstrBot command registration. `src/` has four top-level packages only: `application/` for use cases and ports; `domain/` for Setu, fortune, and access-control rules; `infrastructure/` for AstrBot adapters, providers, persistence, permissions, and sending; and `shared/` for helpers and config models. Tests live in `tests/`, WebUI pages in `pages/`, and plugin skills in `skills/`.

## Agent Skills & Tooling

Use `$skill-astrbot-dev` for AstrBot structure, decorators/hooks, lifecycle, config schema, message flow, platform adapters, and LLM tools. If docs and source disagree, trust source. Use `$github` for issues, PRs, CI, and advanced repository queries through `gh`.

## Build, Test, and Development Commands

- `python -m pip install -e ".[dev]"`: install the plugin with dev tools.
- `python -m pip install -U astrbot`: refresh the AstrBot SDK for local signatures.
- `PYTHONPATH=/path/to/data/plugins python -m pytest`: run the full test suite.
- `python -m pytest tests/domain`: run focused domain tests.
- `python -m ruff check .`: lint Python code.
- `python -m ruff format .`: format Python files.
- `python -m py_compile main.py src/**/*.py tests/**/*.py`: syntax check.

## Ruff Tooling

Ruff settings come from repository config. The project targets Python 3.10, uses 100-character lines, and sorts `astrbot` and `astrbot_plugin_setu` as first-party imports. If the parent cache is not writable, use `RUFF_CACHE_DIR=.ruff_cache`.

## Coding Style & Naming Conventions

Use 4-space indentation, type hints, and `from __future__ import annotations` in new Python modules. Use `snake_case` for modules/functions, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Handlers, hooks, and tool functions should be `async def`. Keep `main.py` focused on registration and forwarding; keep reusable orchestration in `application/`.

## Testing Guidelines

Use pytest and pytest-asyncio. Name files `test_*.py`, classes `TestFeatureName`, and methods `test_behavior`. Reuse fixtures from `tests/conftest.py` for AstrBot config, events, providers, and temp data directories. Add focused unit tests for domain and infrastructure changes.

## Commit & Pull Request Guidelines

Recent history mostly follows Conventional Commits, for example `feat(safety): ...`, `fix: ...`, `refactor: ...`, `docs: ...`, and `chore: ...`. Keep subjects imperative and scoped when useful. PRs should explain motivation, summarize core file changes, identify breaking changes, and include verification output or screenshots.

## Security & Configuration Tips

Do not commit secrets, tokens, local AstrBot runtime data, or downloaded image caches. Session overrides are runtime data; keep fixtures under `tests/`. Keep `_conf_schema.json`, `src/shared/config/models.py`, `metadata.yaml`, `requirements.txt`, and README examples in sync when adding settings or dependencies.
