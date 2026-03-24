"""今日运势核心模块。

管理运势生成、数据库持久化、图片缓存等核心功能。
参照 Java 版本 FortuneDataServiceImpl 实现。
"""

from __future__ import annotations

import asyncio
import datetime
import random
from pathlib import Path
from typing import Any

import aiofiles

from astrbot.api import logger

# 默认权重数组（对应0-7星）
DEFAULT_WEIGHTS = [0.1, 0.15, 0.2, 0.25, 0.15, 0.12, 0.07, 0.005]

# 默认运势标题（对应星级0-7）
DEFAULT_TITLES = ["凶", "末吉", "末小吉", "小吉", "中吉", "吉", "大吉", "超大吉"]

# 默认运势描述（对应星级0-7）
DEFAULT_MESSAGES = [
    "长夜再暗，火种仍在，转机终会到来。",
    "微光不灭，步步向前，黎明就在眼前。",
    "心怀希冀，顺流而行，好事悄然靠近。",
    "逆境翻篇，机遇迎面，惊喜不期而至。",
    "小吉随身，难题化易，幸运与你并肩。",
    "吉星高照，所行皆坦，所愿皆如愿。",
    "福泽深厚，大吉加身，一路花开有声。",
    "七星同耀，奇迹频现，今日万事皆成。",
]


class FortuneCore:
    """今日运势核心类。"""

    def __init__(self, data_dir: Path, config: dict[str, Any]):
        self.data_dir = data_dir
        self.config = config
        self.db_path = data_dir / "fortune.db"
        self.cache_dir = data_dir / "cache"
        self._db_lock = asyncio.Lock()
        self._cache_lock = asyncio.Lock()
        self._db_inited = False
        self._last_cleanup_date: str | None = None

    async def initialize(self) -> None:
        """初始化数据库和缓存目录。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        await self._init_db()
        # 启动时清理过期缓存
        await self._cleanup_expired_cache()
        # 启动定时清理任务
        asyncio.create_task(self._scheduled_cleanup())

    async def _scheduled_cleanup(self) -> None:
        """定时任务，每天凌晨执行：清理缓存 + 预生成活跃用户运势。"""
        while True:
            try:
                # 计算到明天凌晨的时间
                now = datetime.datetime.now()
                tomorrow = now + datetime.timedelta(days=1)
                midnight = datetime.datetime.combine(tomorrow.date(), datetime.time.min)
                wait_seconds = (midnight - now).total_seconds()

                logger.debug("[fortune] Scheduled tasks in %.0f seconds", wait_seconds)
                await asyncio.sleep(wait_seconds)

                # 执行清理
                await self._cleanup_expired_cache()
                # 执行预生成
                await self._pregenerate_active_users()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("[fortune] Scheduled tasks failed: %s", exc)
                await asyncio.sleep(3600)  # 出错后1小时再试

    async def _pregenerate_active_users(self) -> int:
        """预生成活跃用户的今日运势。

        只为3天内有查看记录的用户预生成，避免滥用。
        如果今天已有运势则不覆盖。

        返回:
            预生成的用户数量
        """
        import aiosqlite

        today_str = datetime.date.today().isoformat()
        # 计算3天前的日期
        three_days_ago = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()

        pregenerated = 0

        try:
            async with self._db_lock:
                async with aiosqlite.connect(str(self.db_path)) as db:
                    # 查询3天内有查看记录的用户（且今天还没有运势）
                    cursor = await db.execute(
                        """
                        SELECT DISTINCT user_id FROM fortune_data
                        WHERE last_view_date >= ?
                        AND user_id NOT IN (
                            SELECT user_id FROM fortune_data WHERE date_str = ?
                        )
                        """,
                        (three_days_ago, today_str),
                    )
                    active_users = await cursor.fetchall()

                    if not active_users:
                        logger.debug("[fortune] No active users to pregenerate")
                        return 0

                    logger.info(
                        "[fortune] Pregenerating fortunes for %d active users",
                        len(active_users),
                    )

                    # 为每个活跃用户预生成运势
                    for (user_id,) in active_users:
                        try:
                            # 再次检查今天是否已有运势（避免并发竞争）
                            check_cursor = await db.execute(
                                "SELECT 1 FROM fortune_data WHERE user_id = ? AND date_str = ?",
                                (user_id, today_str),
                            )
                            if await check_cursor.fetchone():
                                # 已有运势，跳过
                                continue

                            # 生成运势
                            fortune = self._generate_fortune(user_id, "指挥官", today_str)

                            # 保存到数据库（使用 INSERT OR IGNORE 避免覆盖）
                            await db.execute(
                                "INSERT INTO fortune_data "
                                "(user_id, date_str, title, stars, desc_text, extra, theme, image_cached, img_url, last_view_date) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (
                                    user_id,
                                    today_str,
                                    fortune["title"],
                                    fortune["star_count"],
                                    fortune["description"],
                                    fortune["extra_message"],
                                    fortune["theme_color"],
                                    0,
                                    None,
                                    today_str,  # 预生成时设置 last_view_date，保持活跃状态
                                ),
                            )
                            pregenerated += 1
                        except Exception as exc:
                            logger.warning(
                                "[fortune] Failed to pregenerate for user %s: %s", user_id, exc
                            )

                    await db.commit()

            if pregenerated > 0:
                logger.info(
                    "[fortune] Pregenerated %d/%d fortunes for active users",
                    pregenerated,
                    len(active_users),
                )

        except Exception as exc:
            logger.error("[fortune] Pregeneration failed: %s", exc)

        return pregenerated

    async def _init_db(self) -> None:
        """初始化数据库表。"""
        import aiosqlite

        async with self._db_lock:
            async with aiosqlite.connect(str(self.db_path)) as db:
                # 创建表（如果不存在）
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS fortune_data (
                        user_id   TEXT NOT NULL,
                        date_str  TEXT NOT NULL,
                        title     TEXT NOT NULL,
                        stars     INTEGER NOT NULL,
                        desc_text TEXT NOT NULL,
                        extra     TEXT NOT NULL,
                        theme     TEXT NOT NULL,
                        image_cached INTEGER DEFAULT 0,
                        img_url   TEXT,
                        last_view_date TEXT,
                        PRIMARY KEY (user_id, date_str)
                    )
                    """
                )
                await db.commit()

                # 检查并添加缺失的列（版本迁移）
                await self._migrate_db(db)

                self._db_inited = True
        logger.info("[fortune] Database initialized")

    @staticmethod
    async def _migrate_db(db) -> None:
        """数据库版本迁移：添加缺失的列。"""
        # 获取表中所有列
        cursor = await db.execute("PRAGMA table_info(fortune_data)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        # 检查并添加 img_url 列
        if "img_url" not in column_names:
            logger.info("[fortune] Migrating database: adding img_url column")
            await db.execute("ALTER TABLE fortune_data ADD COLUMN img_url TEXT")
            await db.commit()
            logger.info("[fortune] Migration completed")

        # 检查并添加 last_view_date 列（用于预生成机制）
        if "last_view_date" not in column_names:
            logger.info("[fortune] Migrating database: adding last_view_date column")
            await db.execute("ALTER TABLE fortune_data ADD COLUMN last_view_date TEXT")
            await db.commit()
            logger.info("[fortune] Migration completed")

    @staticmethod
    def _get_weights() -> list[float]:
        """获取权重配置（固定值）。"""
        return DEFAULT_WEIGHTS

    @staticmethod
    def _get_titles() -> list[str]:
        """获取标题配置（固定值）。"""
        return DEFAULT_TITLES

    @staticmethod
    def _get_messages() -> list[str]:
        """获取描述文案配置（固定值）。"""
        return DEFAULT_MESSAGES

    @staticmethod
    def _get_extra_message() -> str:
        """获取额外消息配置（固定为空）。"""
        return ""

    def _calculate_luck(self) -> int:
        """根据权重计算运势星级。

        返回:
            星级 0-7
        """
        weights = self._get_weights()
        total_weight = sum(weights)
        random_value = random.random() * total_weight
        current_weight = 0

        for i, w in enumerate(weights):
            current_weight += w
            if random_value <= current_weight:
                return i
        return 0

    def _get_theme_color(self, star_num: int) -> str:
        """根据星级获取主题颜色。

        Java版本:
        - 7, 6星 -> theme-red
        - 5, 4星 -> theme-gold
        - 1, 0星 -> theme-gray
        - 其他 -> theme-blue
        """
        if star_num in (7, 6):
            return "theme-red"
        elif star_num in (5, 4):
            return "theme-gold"
        elif star_num in (1, 0):
            return "theme-gray"
        else:
            return "theme-blue"

    def _generate_fortune(
        self, user_id: str, username: str, date_str: str, need_new: bool = True
    ) -> dict[str, Any]:
        """生成运势数据。

        参数:
            user_id: 用户ID
            username: 用户名
            date_str: 日期字符串
            need_new: 是否生成新的运势（刷新时使用）

        返回:
            运势数据字典
        """
        # 计算星级
        star_num = self._calculate_luck()

        # 获取配置
        titles = self._get_titles()
        messages = self._get_messages()
        extra = self._get_extra_message()

        # 获取对应星级的标题和描述
        title = titles[min(star_num, len(titles) - 1)]
        desc = messages[min(star_num, len(messages) - 1)]
        theme = self._get_theme_color(star_num)

        return {
            "user_id": user_id,
            "username": username or "指挥官",
            "date_str": date_str,
            "title": title,
            "star_count": star_num,
            "max_stars": 7,
            "description": desc,
            "extra_message": extra,
            "theme_color": theme,
            "image_cached": False,
            "img_url": None,
        }

    def _get_cache_path(self, user_id: str, date_str: str) -> Path:
        """获取用户图片缓存路径。"""
        return self.cache_dir / f"{user_id}_{date_str}.jpg"

    async def _cleanup_expired_cache(self) -> int:
        """清理过期的缓存文件（非今天的）。

        使用 _last_cleanup_date 避免同一天重复清理。
        """
        today = datetime.date.today().isoformat()

        # 检查是否已经清理过今天
        if self._last_cleanup_date == today:
            return 0

        removed = 0
        removed_size = 0

        try:
            async with self._cache_lock:
                for file_path in self.cache_dir.iterdir():
                    if not file_path.is_file():
                        continue

                    # 解析文件名中的日期 (格式: {user_id}_{date}.jpg)
                    try:
                        # 提取日期部分，假设格式为 user_id_YYYY-MM-DD.jpg
                        file_name = file_path.stem  # 去掉 .jpg
                        parts = file_name.rsplit("_", 1)  # 从右边分割，得到 [user_id, date]

                        if len(parts) >= 2:
                            file_date = parts[-1]
                            # 验证日期格式
                            if file_date != today:
                                # 非今天的缓存，删除
                                file_size = file_path.stat().st_size
                                file_path.unlink()
                                removed += 1
                                removed_size += file_size
                        else:
                            # 无法解析的文件名，也删除
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            removed += 1
                            removed_size += file_size
                    except (OSError, ValueError):
                        # 删除异常文件
                        try:
                            file_size = file_path.stat().st_size
                            file_path.unlink()
                            removed += 1
                            removed_size += file_size
                        except OSError:
                            pass

            # 更新最后清理日期
            if removed > 0:
                logger.info(
                    "[fortune] Cleaned up %d expired cache files (%.2f MB)",
                    removed,
                    removed_size / 1024 / 1024,
                )
            else:
                logger.debug("[fortune] No expired cache files to clean")

            self._last_cleanup_date = today

        except OSError as exc:
            logger.warning("[fortune] Failed to cleanup cache: %s", exc)

        return removed

    async def get_today_fortune(
        self, user_id: str, username: str
    ) -> dict[str, Any] | None:
        """获取今日运势。

        如果 auto_refresh 为 false，会保留前一天的运势直到第二天。
        每次获取都会更新 last_view_date。

        返回:
            运势数据字典
        """
        import aiosqlite

        today_str = datetime.date.today().isoformat()

        # 先检查并清理过期缓存（每天只执行一次）
        await self._cleanup_expired_cache()

        async with self._db_lock:
            async with aiosqlite.connect(str(self.db_path)) as db:
                # 查询现有记录（包括 last_view_date）
                cursor = await db.execute(
                    "SELECT title, stars, desc_text, extra, theme, image_cached, img_url, date_str, last_view_date "
                    "FROM fortune_data WHERE user_id = ?",
                    (user_id,),
                )
                row = await cursor.fetchone()

                if row:
                    # 有记录，检查是否是今天
                    record_date = row[7]
                    is_today = record_date == today_str

                    if is_today:
                        # 今天已有运势，更新最后查看日期并返回
                        await db.execute(
                            "UPDATE fortune_data SET last_view_date = ? WHERE user_id = ? AND date_str = ?",
                            (today_str, user_id, today_str),
                        )
                        await db.commit()
                        return {
                            "user_id": user_id,
                            "username": username,
                            "date_str": today_str,
                            "title": row[0],
                            "star_count": row[1],
                            "max_stars": 7,
                            "description": row[2],
                            "extra_message": row[3],
                            "theme_color": row[4],
                            "image_cached": bool(row[5]),
                            "img_url": row[6],
                        }
                    else:
                        # 不是今天的记录，检查是否自动刷新
                        auto_refresh = self.config.get("auto_refresh", True)
                        if not auto_refresh:
                            # 不自动刷新，返回旧数据（但显示今天的日期）
                            # 同时更新最后查看日期（基于旧记录）
                            await db.execute(
                                "UPDATE fortune_data SET last_view_date = ? WHERE user_id = ? AND date_str = ?",
                                (today_str, user_id, record_date),
                            )
                            await db.commit()
                            return {
                                "user_id": user_id,
                                "username": username,
                                "date_str": today_str,
                                "title": row[0],
                                "star_count": row[1],
                                "max_stars": 7,
                                "description": row[2],
                                "extra_message": row[3],
                                "theme_color": row[4],
                                "image_cached": bool(row[5]),
                                "img_url": row[6],
                            }
                        # 需要重新生成

                # 生成新运势
                fortune = self._generate_fortune(user_id, username, today_str)

                # 保存到数据库（包含 last_view_date）
                await db.execute(
                    "INSERT OR REPLACE INTO fortune_data "
                    "(user_id, date_str, title, stars, desc_text, extra, theme, image_cached, img_url, last_view_date) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        user_id,
                        today_str,
                        fortune["title"],
                        fortune["star_count"],
                        fortune["description"],
                        fortune["extra_message"],
                        fortune["theme_color"],
                        0,
                        None,
                        today_str,  # 首次生成时设置 last_view_date
                    ),
                )
                await db.commit()

                return fortune

    async def update_fortune_image_cache(
        self, user_id: str, date_str: str, image_data: bytes, img_url: str | None = None
    ) -> Path:
        """更新运势图片缓存。"""
        cache_path = self._get_cache_path(user_id, date_str)

        async with self._cache_lock:
            async with aiofiles.open(cache_path, "wb") as f:
                await f.write(image_data)

        # 更新数据库标记
        import aiosqlite

        async with self._db_lock:
            async with aiosqlite.connect(str(self.db_path)) as db:
                await db.execute(
                    "UPDATE fortune_data SET image_cached = 1, img_url = ? "
                    "WHERE user_id = ? AND date_str = ?",
                    (img_url, user_id, date_str),
                )
                await db.commit()

        return cache_path

    async def get_cached_image(self, user_id: str, date_str: str) -> bytes | None:
        """获取缓存的图片数据。"""
        cache_path = self._get_cache_path(user_id, date_str)

        try:
            async with self._cache_lock:
                if cache_path.exists():
                    async with aiofiles.open(cache_path, "rb") as f:
                        return await f.read()
        except OSError:
            pass
        return None

    async def refresh_fortune(self, user_id: str, username: str) -> dict[str, Any]:
        """刷新用户今日运势（生成新的）。"""
        import aiosqlite

        date_str = datetime.date.today().isoformat()

        # 生成新运势
        fortune = self._generate_fortune(user_id, username, date_str)

        # 更新数据库（包含 last_view_date）
        async with self._db_lock:
            async with aiosqlite.connect(str(self.db_path)) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO fortune_data "
                    "(user_id, date_str, title, stars, desc_text, extra, theme, image_cached, img_url, last_view_date) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        user_id,
                        date_str,
                        fortune["title"],
                        fortune["star_count"],
                        fortune["description"],
                        fortune["extra_message"],
                        fortune["theme_color"],
                        0,
                        None,
                        date_str,  # 刷新时更新 last_view_date
                    ),
                )
                await db.commit()

        # 删除旧缓存
        cache_path = self._get_cache_path(user_id, date_str)
        try:
            cache_path.unlink(missing_ok=True)
        except OSError:
            pass

        return fortune

    async def refresh_group_fortune(self, group_id: str) -> int:
        """刷新指定群的所有今日运势。

        返回:
            被刷新的记录数量
        """
        import aiosqlite

        date_str = datetime.date.today().isoformat()

        async with self._db_lock:
            async with aiosqlite.connect(str(self.db_path)) as db:
                # 获取今天的所有记录
                cursor = await db.execute(
                    "SELECT user_id FROM fortune_data WHERE date_str = ?",
                    (date_str,),
                )
                rows = await cursor.fetchall()

                # 删除这些记录
                await db.execute(
                    "DELETE FROM fortune_data WHERE date_str = ?",
                    (date_str,),
                )
                await db.commit()

        # 清理缓存文件
        async with self._cache_lock:
            for file_path in self.cache_dir.iterdir():
                if file_path.is_file() and date_str in file_path.name:
                    try:
                        file_path.unlink()
                    except OSError:
                        pass

        logger.info("[fortune] Refreshed %d fortunes for date %s", len(rows), date_str)
        return len(rows)

    async def refresh_all_fortune(self) -> int:
        """刷新全局今日运势。

        返回:
            被删除的记录数量
        """
        import aiosqlite

        date_str = datetime.date.today().isoformat()

        async with self._db_lock:
            async with aiosqlite.connect(str(self.db_path)) as db:
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM fortune_data WHERE date_str = ?",
                    (date_str,),
                )
                row = await cursor.fetchone()
                count = row[0] if row else 0

                await db.execute(
                    "DELETE FROM fortune_data WHERE date_str = ?",
                    (date_str,),
                )
                await db.commit()

        # 清理所有今天的缓存文件
        async with self._cache_lock:
            for file_path in self.cache_dir.iterdir():
                if file_path.is_file() and date_str in file_path.name:
                    try:
                        file_path.unlink()
                    except OSError:
                        pass

        logger.info("[fortune] Refreshed all %d fortunes for date %s", count, date_str)
        return count

    def format_stars(self, count: int, max_count: int = 7) -> str:
        """格式化星级显示。"""
        filled = "★" * count
        empty = "☆" * (max_count - count)
        return filled + empty
