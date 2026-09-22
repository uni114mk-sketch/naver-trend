from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class Settings:
    regions: dict[str, list[str]]
    own_brand_keywords: list[str]
    own_blog_ids: list[str]
    own_cafe_ids: list[str]
    media: list[str]
    top_n: int
    place_top_n: int
    use_search_tab: bool
    max_images_per_post: int
    delay_seconds: float
    model: str
    effort: str
    pptx_per_item_slides: bool
    db_path: Path
    output_dir: Path
    naver_client_id: str = ""
    naver_client_secret: str = ""
    anthropic_api_key: str = ""
    raw: dict = field(default_factory=dict)

    def region_of(self, keyword: str) -> str | None:
        for region, keywords in self.regions.items():
            if keyword in keywords:
                return region
        return None


def load_settings(config_path: str | Path = "config.yaml", env_path: str | Path = ".env") -> Settings:
    load_dotenv(env_path)
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    collect = raw.get("collect", {})
    classify = raw.get("classify", {})
    report = raw.get("report", {})
    storage = raw.get("storage", {})
    own = raw.get("own_channels", {}) or {}
    return Settings(
        regions={k: list(v or []) for k, v in (raw.get("regions") or {}).items()},
        own_brand_keywords=list(raw.get("own_brand_keywords") or []),
        own_blog_ids=list(own.get("blog_ids") or []),
        own_cafe_ids=list(own.get("cafe_ids") or []),
        media=list(collect.get("media") or ["blog", "cafe", "place"]),
        top_n=int(collect.get("top_n", 30)),
        place_top_n=int(collect.get("place_top_n", 10)),
        use_search_tab=bool(collect.get("use_search_tab", True)),
        max_images_per_post=int(collect.get("max_images_per_post", 6)),
        delay_seconds=float(collect.get("delay_seconds", 2)),
        model=str(classify.get("model", "claude-opus-5")),
        effort=str(classify.get("effort", "medium")),
        pptx_per_item_slides=bool(report.get("pptx_per_item_slides", True)),
        db_path=Path(storage.get("db_path", "adwatch.db")),
        output_dir=Path(storage.get("output_dir", "output")),
        naver_client_id=os.getenv("NAVER_CLIENT_ID", ""),
        naver_client_secret=os.getenv("NAVER_CLIENT_SECRET", ""),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        raw=raw,
    )
