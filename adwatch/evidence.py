"""게시글 본문·이미지 추출과 풀페이지 캡처."""
from __future__ import annotations

import io
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from PIL import Image

from .models import Evidence

BLOG_RE = re.compile(r"blog\.naver\.com/([A-Za-z0-9_\-\.]+)/(\d+)")
CAFE_RE = re.compile(r"cafe\.naver\.com/([A-Za-z0-9_\-\.]+)/(\d+)")
LOGIN_HINTS = ("로그인", "가입", "멤버만", "권한이 없습니다", "등급")
CONTENT_SELECTORS = [
    "div.se-main-container",   # 스마트에디터 ONE
    "#postViewArea",           # 구버전 블로그
    "div.ContentRenderer",     # 카페 신버전
    "#tbody",                  # 카페 구버전
    "article",
]
MAX_IMAGE_SIDE = 1200


def mobile_url(url: str) -> str:
    m = BLOG_RE.search(url)
    if m:
        return f"https://m.blog.naver.com/{m.group(1)}/{m.group(2)}"
    m = CAFE_RE.search(url)
    if m:
        return f"https://m.cafe.naver.com/{m.group(1)}/{m.group(2)}"
    return url


def parse_post_html(html_text: str) -> tuple[str, list[str], bool]:
    """(본문 텍스트, 이미지 URL 목록, 열람 가능 여부)"""
    soup = BeautifulSoup(html_text, "html.parser")
    container = None
    for sel in CONTENT_SELECTORS:
        container = soup.select_one(sel)
        if container:
            break
    if container is None:
        body_text = soup.get_text(" ", strip=True)
        accessible = not any(h in body_text[:3000] for h in LOGIN_HINTS) or len(body_text) > 3000
        return body_text[:20000], [], accessible
    text = container.get_text("\n", strip=True)
    images = []
    for img in container.find_all("img"):
        src = img.get("data-lazy-src") or img.get("data-src") or img.get("src") or ""
        if not src or src.startswith("data:") or "blank" in src or "icon" in src:
            continue
        src = re.sub(r"\?type=w\d+.*$", "?type=w966", src)  # 썸네일 -> 큰 이미지
        if src not in images:
            images.append(src)
    return text[:20000], images, True


def download_image(url: str, out_path: Path, timeout: float = 15) -> bool:
    try:
        r = requests.get(url, timeout=timeout, headers={"Referer": "https://blog.naver.com/"})
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        im.save(out_path, "JPEG", quality=85)
        return True
    except Exception:
        return False


class EvidenceCollector:
    def __init__(self, context, delay_seconds: float = 2.0, max_images: int = 6):
        self.context = context
        self.delay = delay_seconds
        self.max_images = max_images

    def collect(self, url: str, screenshot_path: Path, image_dir: Path) -> Evidence:
        page = self.context.new_page()
        try:
            page.set_viewport_size({"width": 480, "height": 1000})
            page.goto(mobile_url(url), wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            for _ in range(6):  # 지연 로딩 이미지
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(300)
            html_text = page.content()
            text, image_urls, accessible = parse_post_html(html_text)
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception as e:  # 타임아웃 등
            return Evidence(accessible=False, note=f"열람 실패: {e}")
        finally:
            page.close()
            time.sleep(self.delay)

        paths = []
        image_dir.mkdir(parents=True, exist_ok=True)
        for i, src in enumerate(image_urls[: self.max_images]):
            p = image_dir / f"{screenshot_path.stem}_img{i + 1}.jpg"
            if download_image(src, p):
                paths.append(str(p))
        return Evidence(text=text, image_paths=paths, screenshot_path=str(screenshot_path), accessible=accessible,
                        note="" if accessible else "로그인/회원 전용으로 본문 열람 불가")
