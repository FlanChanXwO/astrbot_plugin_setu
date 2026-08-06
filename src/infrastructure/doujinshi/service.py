"""随机本子 API 的响应解析与文件生成服务。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from PIL import Image
from PIL import ImageOps

from ...domain import HTTP_TIMEOUT_SECONDS


@dataclass(frozen=True)
class DoujinshiGallery:
    """可下载并封装为 PDF 的本子元数据。

    ``title`` 可在上游缺失时回退为本地标题；其余两个字段只保留 API
    实际提供的元数据，供合并转发决定是否追加对应节点。
    """

    id: int
    title: str
    page_urls: tuple[str, ...]
    upstream_title: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class GeneratedDoujinshiPdf:
    """已经落盘、可作为 AstrBot 文件消息发送的随机本子 PDF。"""

    gallery: DoujinshiGallery
    path: Path


class DoujinshiService:
    """解析 Atri 随机本子 API 的公开响应。"""

    API_URL = "https://api.atri.rodeo/v1/doujinshi/random"
    REQUEST_HEADERS = {
        "Accept": "application/json",
        "User-Agent": (
            "astrbot-plugin-setu/2.2.0 "
            "(+https://github.com/FlanChanXwO/astrbot_plugin_setu)"
        ),
        "Sec-Fetch-Dest": "empty",
    }

    def __init__(self, data_dir: Path | str) -> None:
        self._output_dir = Path(data_dir) / "doujinshi"

    async def fetch_random_pdf(
        self,
        tags: list[str] | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> GeneratedDoujinshiPdf:
        """获取随机本子并将 API 返回的全部页图封装为 PDF。"""
        normalized_tags = [tag for tag in tags or [] if tag]
        if client is not None:
            return await self._fetch_random_pdf_with_client(client, normalized_tags)

        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as managed_client:
            return await self._fetch_random_pdf_with_client(
                managed_client, normalized_tags
            )

    async def _fetch_random_pdf_with_client(
        self, client: httpx.AsyncClient, tags: list[str]
    ) -> GeneratedDoujinshiPdf:
        # 与 Atri 图片接口一致，重复 tag 参数以保留所有解析后的标签。
        response = await client.get(
            self.API_URL,
            headers=self.REQUEST_HEADERS,
            params=[("tag", tag) for tag in tags],
        )
        response.raise_for_status()
        try:
            raw_payload = response.json()
        except ValueError as exc:
            raise ValueError("随机本子 API 返回的不是有效 JSON") from exc
        if not isinstance(raw_payload, Mapping):
            raise ValueError("随机本子 API 响应格式无效")

        gallery = self.parse_gallery(raw_payload)
        output_path = self._build_output_path(gallery)
        try:
            await self._create_pdf_from_urls(
                client, gallery.page_urls, output_path, gallery.title
            )
        except BaseException:
            output_path.unlink(missing_ok=True)
            raise
        return GeneratedDoujinshiPdf(gallery=gallery, path=output_path)

    @staticmethod
    def parse_gallery(payload: Mapping[str, object]) -> DoujinshiGallery:
        """将 API 响应校验为完整的本子元数据。"""
        gallery_id = payload.get("id")
        if not isinstance(gallery_id, int) or isinstance(gallery_id, bool):
            raise ValueError("随机本子 API 响应缺少有效 ID")

        raw_title = payload.get("title")
        upstream_title = DoujinshiService._resolve_upstream_title(raw_title)
        title = DoujinshiService._resolve_title(raw_title, gallery_id)
        source_url = DoujinshiService._resolve_source_url(payload.get("url"))
        page_urls = DoujinshiService._resolve_page_urls(payload.get("pages"))
        return DoujinshiGallery(
            id=gallery_id,
            title=title,
            page_urls=tuple(page_urls),
            upstream_title=upstream_title,
            source_url=source_url,
        )

    @staticmethod
    def create_pdf(pages: list[Image.Image], output_path: Path, title: str) -> None:
        """按下载顺序将所有页图写入一个多页 PDF。"""
        if not pages:
            raise ValueError("无法从空页图列表生成 PDF")

        prepared_pages = [DoujinshiService._prepare_pdf_page(page) for page in pages]
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            first_page, *remaining_pages = prepared_pages
            first_page.save(
                output_path,
                "PDF",
                save_all=True,
                append_images=remaining_pages,
                title=title,
                resolution=72.0,
            )
        finally:
            for page in prepared_pages:
                page.close()

    async def _create_pdf_from_urls(
        self,
        client: httpx.AsyncClient,
        page_urls: tuple[str, ...],
        output_path: Path,
        title: str,
    ) -> None:
        for page_number, page_url in enumerate(page_urls, start=1):
            try:
                response = await client.get(page_url)
                response.raise_for_status()
                await asyncio.to_thread(
                    self._append_pdf_page,
                    output_path,
                    response.content,
                    title,
                    is_first_page=page_number == 1,
                )
            except (httpx.HTTPError, OSError) as exc:
                raise RuntimeError(
                    f"随机本子第 {page_number} 页下载或转换失败"
                ) from exc

    def _build_output_path(self, gallery: DoujinshiGallery) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        return self._output_dir / f"doujinshi-{gallery.id}-{uuid4().hex}.pdf"

    @staticmethod
    def _append_pdf_page(
        output_path: Path,
        page_bytes: bytes,
        title: str,
        *,
        is_first_page: bool,
    ) -> None:
        with Image.open(BytesIO(page_bytes)) as source:
            prepared_page = DoujinshiService._prepare_pdf_page(source)
        try:
            if is_first_page:
                prepared_page.save(
                    output_path,
                    "PDF",
                    title=title,
                    resolution=72.0,
                )
            else:
                prepared_page.save(output_path, "PDF", append=True)
        finally:
            prepared_page.close()

    @staticmethod
    def _prepare_pdf_page(page: Image.Image) -> Image.Image:
        normalized_page = ImageOps.exif_transpose(page)
        try:
            if (
                "A" in normalized_page.getbands()
                or "transparency" in normalized_page.info
            ):
                rgba_page = normalized_page.convert("RGBA")
                background = Image.new("RGB", rgba_page.size, "white")
                background.paste(rgba_page, mask=rgba_page.getchannel("A"))
                rgba_page.close()
                return background
            if normalized_page.mode == "RGB":
                return normalized_page.copy()
            return normalized_page.convert("RGB")
        finally:
            if normalized_page is not page:
                normalized_page.close()

    @staticmethod
    def _resolve_title(raw_title: object, gallery_id: int) -> str:
        return (
            DoujinshiService._resolve_upstream_title(raw_title)
            or f"随机本子 {gallery_id}"
        )

    @staticmethod
    def _resolve_upstream_title(raw_title: object) -> str | None:
        """提取可展示的上游标题，不把本地回退值伪装成上游元数据。"""
        if isinstance(raw_title, Mapping):
            for key in ("pretty", "english", "japanese"):
                value = raw_title.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(raw_title, str) and raw_title.strip():
            return raw_title.strip()
        return None

    @staticmethod
    def _resolve_source_url(raw_url: object) -> str | None:
        """仅保留上游提供的有效原始地址，缺失时交由发送器省略节点。"""
        if not isinstance(raw_url, str):
            return None
        source_url = raw_url.strip()
        if not source_url or not DoujinshiService._is_http_url(source_url):
            return None
        return source_url

    @staticmethod
    def _resolve_page_urls(raw_pages: object) -> list[str]:
        if not isinstance(raw_pages, list) or not raw_pages:
            raise ValueError("随机本子 API 响应不包含页图")

        page_urls: list[str] = []
        for page_number, raw_page in enumerate(raw_pages, start=1):
            if not isinstance(raw_page, Mapping):
                raise ValueError(f"随机本子第 {page_number} 页格式无效")
            raw_url = raw_page.get("url")
            if not isinstance(raw_url, str) or not DoujinshiService._is_http_url(
                raw_url
            ):
                raise ValueError(f"随机本子第 {page_number} 页缺少可下载的图片 URL")
            page_urls.append(raw_url)
        return page_urls

    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
