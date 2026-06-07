from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from astrbot_plugin_setu.src.domain.fortune import (
    FortuneGenerationRequest,
    FortuneRecord,
)
from astrbot_plugin_setu.src.infrastructure.astrbot.commands import (
    fortune as fortune_cmd,
)
from astrbot_plugin_setu.src.infrastructure.astrbot.commands.fortune import (
    FortuneCommandHandler,
)
from astrbot_plugin_setu.src.infrastructure.persistence.sqlite_fortune_repository import (
    SQLiteFortuneRepo,
)


class MemoryFortuneRepo:
    def __init__(
        self, active_requests: list[FortuneGenerationRequest], cache_dir: Path
    ) -> None:
        self.active_requests = active_requests
        self.cache_dir = cache_dir
        self.records: dict[tuple[str, str], FortuneRecord] = {}
        self.cached_images: dict[tuple[str, str], bytes] = {}
        self.cached_paths: dict[tuple[str, str], Path] = {}

    async def get_today_fortune(
        self, request: FortuneGenerationRequest
    ) -> FortuneRecord | None:
        return self.records.get((request.user_id, request.date_str))

    async def save_fortune(self, record: FortuneRecord) -> bool:
        self.records[(record.user_id, record.date_str)] = record
        return True

    async def delete_fortune(self, user_id: str, date_str: str) -> bool:
        self.records.pop((user_id, date_str), None)
        return True

    async def delete_group_fortunes(self, group_id: str, date_str: str) -> int:
        return 0

    async def delete_all_fortunes(self, date_str: str) -> int:
        return 0

    async def get_active_users(self, days: int = 3) -> list[str]:
        return [request.user_id for request in self.active_requests]

    async def get_active_fortune_requests(
        self, days: int = 3, date_str: str | None = None
    ) -> list[FortuneGenerationRequest]:
        target_date = date_str or date.today().isoformat()
        return [
            FortuneGenerationRequest(
                user_id=request.user_id,
                username=request.username,
                date_str=target_date,
                group_id=request.group_id,
            )
            for request in self.active_requests
        ]

    async def get_cached_image_path(self, user_id: str, date_str: str) -> Path | None:
        return self.cached_paths.get((user_id, date_str))

    async def save_cached_image(
        self, user_id: str, date_str: str, image_data: bytes, img_url: str | None
    ) -> Path:
        self.cached_images[(user_id, date_str)] = image_data
        record = self.records[(user_id, date_str)]
        self.records[(user_id, date_str)] = record.with_image_cache(img_url)
        path = self.cache_dir / f"{user_id}_{date_str}.jpg"
        path.write_bytes(image_data)
        self.cached_paths[(user_id, date_str)] = path
        return path

    async def delete_cached_image(self, user_id: str, date_str: str) -> bool:
        self.cached_images.pop((user_id, date_str), None)
        path = self.cached_paths.pop((user_id, date_str), None)
        if path:
            path.unlink(missing_ok=True)
        return True

    async def cleanup_expired_cache(self, date_str: str) -> int:
        return 0


class MemoryAccessControlRepo:
    def __init__(
        self,
        *,
        blocked_users: set[str] | None = None,
        blocked_groups: set[str] | None = None,
    ) -> None:
        self.blocked_users = blocked_users or set()
        self.blocked_groups = blocked_groups or set()

    def get_modes(self) -> dict[str, str]:
        return {
            "fortune_user_access_control_mode": "blacklist",
            "fortune_group_access_control_mode": "blacklist",
        }

    async def is_fortune_user_blocked(self, user_id: str) -> bool:
        return user_id in self.blocked_users

    async def is_fortune_user_whitelisted(self, user_id: str) -> bool:
        return True

    async def is_fortune_group_blocked(self, group_id: str) -> bool:
        return group_id in self.blocked_groups

    async def is_fortune_group_whitelisted(self, group_id: str) -> bool:
        return True


def patch_runtime(monkeypatch, repo: MemoryFortuneRepo, access_repo=None) -> None:
    monkeypatch.setattr(
        fortune_cmd,
        "get_config",
        lambda: SimpleNamespace(
            fortune=SimpleNamespace(enabled=True, auto_refresh=True),
            fortune_user_access_control_mode="blacklist",
            fortune_group_access_control_mode="blacklist",
        ),
    )
    monkeypatch.setattr(fortune_cmd, "get_fortune_repo", lambda: repo)
    monkeypatch.setattr(
        fortune_cmd,
        "get_access_control_repo",
        lambda: access_repo or MemoryAccessControlRepo(),
    )


@pytest.mark.asyncio
async def test_pregenerate_active_fortune_images_writes_rendered_cache(
    monkeypatch, tmp_path: Path
) -> None:
    today = date.today().isoformat()
    repo = MemoryFortuneRepo(
        [
            FortuneGenerationRequest(
                user_id="user-1",
                username="测试用户",
                date_str="2026-05-17",
                group_id="group-1",
            )
        ],
        tmp_path,
    )
    handler = FortuneCommandHandler()

    async def fake_background_image() -> tuple[bytes, str]:
        return b"background", "https://example.com/bg.jpg"

    async def fake_render_to_image(*args, **kwargs) -> bytes:
        return b"rendered-card"

    patch_runtime(monkeypatch, repo)
    monkeypatch.setattr(handler, "_get_fortune_background_image", fake_background_image)
    monkeypatch.setattr(handler._renderer, "render_to_image", fake_render_to_image)

    cached_count = await handler.pregenerate_active_fortune_images()

    assert cached_count == 1
    assert repo.cached_images[("user-1", today)] == b"rendered-card"
    record = repo.records[("user-1", today)]
    assert record.username == "测试用户"
    assert record.group_id == "group-1"
    assert record.image_cached is True
    assert record.img_url == "https://example.com/bg.jpg"


@pytest.mark.asyncio
async def test_pregenerate_active_fortune_images_skips_existing_cache(
    monkeypatch, tmp_path: Path
) -> None:
    today = date.today().isoformat()
    repo = MemoryFortuneRepo(
        [
            FortuneGenerationRequest(
                user_id="user-1",
                username="测试用户",
                date_str="2026-05-17",
                group_id="group-1",
            )
        ],
        tmp_path,
    )
    cached_path = tmp_path / f"user-1_{today}.jpg"
    cached_path.write_bytes(b"cached-card")
    repo.cached_paths[("user-1", today)] = cached_path
    handler = FortuneCommandHandler()
    render_call_count = 0

    async def fake_render_to_image(*args, **kwargs) -> bytes:
        nonlocal render_call_count
        render_call_count += 1
        return b"rendered-card"

    patch_runtime(monkeypatch, repo)
    monkeypatch.setattr(handler._renderer, "render_to_image", fake_render_to_image)

    cached_count = await handler.pregenerate_active_fortune_images()

    assert cached_count == 0
    assert render_call_count == 0
    assert repo.cached_images == {}


@pytest.mark.asyncio
async def test_pregenerate_active_fortune_images_continues_after_record_error(
    monkeypatch, tmp_path: Path
) -> None:
    today = date.today().isoformat()
    repo = MemoryFortuneRepo(
        [
            FortuneGenerationRequest("bad-user", "坏数据", "2026-05-17"),
            FortuneGenerationRequest("good-user", "测试用户", "2026-05-17"),
        ],
        tmp_path,
    )
    handler = FortuneCommandHandler()

    async def fake_background_image() -> tuple[bytes, str]:
        return b"background", "https://example.com/bg.jpg"

    async def fake_render_to_image(fortune, *args, **kwargs) -> bytes:
        if fortune["username"] == "坏数据":
            raise RuntimeError("boom")
        return b"rendered-card"

    patch_runtime(monkeypatch, repo)
    monkeypatch.setattr(handler, "_get_fortune_background_image", fake_background_image)
    monkeypatch.setattr(handler._renderer, "render_to_image", fake_render_to_image)

    cached_count = await handler.pregenerate_active_fortune_images()

    assert cached_count == 1
    assert ("bad-user", today) not in repo.cached_images
    assert repo.cached_images[("good-user", today)] == b"rendered-card"


@pytest.mark.asyncio
async def test_pregenerate_active_fortune_images_respects_auto_refresh(
    monkeypatch, tmp_path: Path
) -> None:
    repo = MemoryFortuneRepo(
        [FortuneGenerationRequest("user-1", "测试用户", "2026-05-17")],
        tmp_path,
    )
    handler = FortuneCommandHandler()

    monkeypatch.setattr(
        fortune_cmd,
        "get_config",
        lambda: SimpleNamespace(
            fortune=SimpleNamespace(enabled=True, auto_refresh=False)
        ),
    )
    monkeypatch.setattr(fortune_cmd, "get_fortune_repo", lambda: repo)

    assert await handler.pregenerate_active_fortune_images() == 0
    assert repo.records == {}
    assert repo.cached_images == {}


@pytest.mark.asyncio
async def test_pregenerate_active_fortune_images_filters_access_control(
    monkeypatch, tmp_path: Path
) -> None:
    today = date.today().isoformat()
    repo = MemoryFortuneRepo(
        [
            FortuneGenerationRequest("blocked-user", "禁用用户", "2026-05-17"),
            FortuneGenerationRequest(
                "blocked-group-user", "禁用群用户", "2026-05-17", "group-blocked"
            ),
            FortuneGenerationRequest(
                "allowed-user", "正常用户", "2026-05-17", "group-ok"
            ),
        ],
        tmp_path,
    )
    access_repo = MemoryAccessControlRepo(
        blocked_users={"blocked-user"}, blocked_groups={"group-blocked"}
    )
    handler = FortuneCommandHandler()

    async def fake_background_image() -> tuple[bytes, str]:
        return b"background", "https://example.com/bg.jpg"

    async def fake_render_to_image(*args, **kwargs) -> bytes:
        return b"rendered-card"

    patch_runtime(monkeypatch, repo, access_repo)
    monkeypatch.setattr(handler, "_get_fortune_background_image", fake_background_image)
    monkeypatch.setattr(handler._renderer, "render_to_image", fake_render_to_image)

    cached_count = await handler.pregenerate_active_fortune_images()

    assert cached_count == 1
    assert set(repo.cached_images) == {("allowed-user", today)}


@pytest.mark.asyncio
async def test_sqlite_repo_builds_active_generation_requests(temp_data_dir) -> None:
    today = date.today().isoformat()
    target_date = "2099-01-02"
    repo = SQLiteFortuneRepo(temp_data_dir / "fortune")
    await repo.initialize()
    await repo.save_fortune(
        FortuneRecord.create_new(
            user_id="user-1",
            username="测试用户",
            date_str=today,
            title="大吉",
            star_count=6,
            description="今日顺利",
            extra_message="",
            theme_color="theme-red",
            group_id="group-1",
        )
    )

    requests = await repo.get_active_fortune_requests(days=3, date_str=target_date)

    assert requests == [
        FortuneGenerationRequest(
            user_id="user-1",
            username="测试用户",
            date_str=target_date,
            group_id="group-1",
        )
    ]
