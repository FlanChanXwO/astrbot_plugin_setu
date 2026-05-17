from __future__ import annotations

from astrbot_plugin_setu.src.infrastructure.providers.atri import AtriProvider
from astrbot_plugin_setu.src.infrastructure.providers.lolicon import LoliconProvider


def test_lolicon_provider_rewrites_pixiv_proxy_host() -> None:
    provider = LoliconProvider(proxy="my.proxy.local")

    rewritten = provider._apply_proxy_to_urls(
        ["https://i.pximg.net/img-original/img/2024/01/01/00/00/00/1_p0.jpg"],
        provider.proxy,
        "LoliconProvider",
    )

    assert rewritten == [
        "https://my.proxy.local/img-original/img/2024/01/01/00/00/00/1_p0.jpg"
    ]


def test_atri_provider_keeps_non_pixiv_host_unchanged() -> None:
    provider = AtriProvider(proxy="my.proxy.local")

    rewritten = provider._apply_proxy_to_urls(
        ["https://cdn.example.com/image.jpg"],
        provider.proxy,
        "AtriProvider",
    )

    assert rewritten == ["https://cdn.example.com/image.jpg"]
