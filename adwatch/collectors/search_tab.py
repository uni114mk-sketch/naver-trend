"""네이버 통합검색의 블로그탭 / 카페탭 / 플레이스를 Playwright 로 열어 실제 노출 순서대로 URL 을 수집.

검색 API 는 실제 탭 노출 순위와 달라서, "상위 노출 게시글" 기준을 지키려면 실제 페이지가 필요합니다.
마크업은 자주 바뀌므로 CSS 선택자 대신 페이지 안의 앵커 href 를 정규식으로 긁습니다.
"""
from __future__ import annotations

import re
import time
from urllib.parse import quote

BLOG_TAB = "https://search.naver.com/search.naver?ssc=tab.blog.all&sm=tab_jum&query={q}"
CAFE_TAB = "https://search.naver.com/search.naver?ssc=tab.cafe.all&sm=tab_jum&query={q}"
PLACE_SEARCH = "https://m.search.naver.com/search.naver?query={q}"

BLOG_URL_RE = re.compile(r"https?://(?:m\.)?blog\.naver\.com/([A-Za-z0-9_\-\.]+)/(\d+)")
CAFE_URL_RE = re.compile(r"https?://(?:m\.)?cafe\.naver\.com/([A-Za-z0-9_\-\.]+)/(\d+)")
CAFE_URL_RE2 = re.compile(r"https?://(?:m\.)?cafe\.naver\.com/ca-fe/web/cafes/([A-Za-z0-9_\-\.]+)/articles/(\d+)")
PLACE_ID_RE = re.compile(r"(?:place|hospital|entry/place)/(\d{5,})")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def extract_blog_urls(html_text: str, n: int) -> list[dict]:
    """HTML 에서 블로그 글 URL 을 노출 순서대로 중복 없이 n개."""
    seen, out = set(), []
    for m in BLOG_URL_RE.finditer(html_text):
        blog_id, log_no = m.group(1), m.group(2)
        key = (blog_id, log_no)
        if key in seen:
            continue
        seen.add(key)
        out.append({"url": f"https://blog.naver.com/{blog_id}/{log_no}", "author": blog_id, "title": ""})
        if len(out) >= n:
            break
    return out


def extract_cafe_urls(html_text: str, n: int) -> list[dict]:
    seen, out = set(), []
    for regex in (CAFE_URL_RE, CAFE_URL_RE2):
        for m in regex.finditer(html_text):
            cafe_id, art = m.group(1), m.group(2)
            if cafe_id in ("ca-fe",):
                continue
            key = (cafe_id, art)
            if key in seen:
                continue
            seen.add(key)
            out.append({"url": f"https://cafe.naver.com/{cafe_id}/{art}", "author": cafe_id, "title": ""})
    # 노출 순서를 유지하기 위해 원문 위치 기준 정렬
    out.sort(key=lambda d: html_text.find(d["url"].split("cafe.naver.com/")[1]))
    return out[:n]


def extract_place_ids(html_text: str, n: int) -> list[str]:
    seen, out = set(), []
    for m in PLACE_ID_RE.finditer(html_text):
        pid = m.group(1)
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
        if len(out) >= n:
            break
    return out


class SearchTabCollector:
    """Playwright 브라우저 하나를 열어 두고 여러 키워드를 처리. with 문으로 사용."""

    def __init__(self, delay_seconds: float = 2.0, headless: bool = True):
        self.delay = delay_seconds
        self.headless = headless
        self._pw = None
        self.browser = None
        self.context = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900},
                                                locale="ko-KR")
        return self

    def __exit__(self, *exc):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self._pw:
            self._pw.stop()

    def _html(self, url: str, scrolls: int = 3) -> str:
        page = self.context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)
            for _ in range(scrolls):  # 지연 로딩되는 하단 결과까지
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(700)
            return page.content()
        finally:
            page.close()
            time.sleep(self.delay)

    def blog(self, keyword: str, n: int) -> list[dict]:
        return extract_blog_urls(self._html(BLOG_TAB.format(q=quote(keyword))), n)

    def cafe(self, keyword: str, n: int) -> list[dict]:
        return extract_cafe_urls(self._html(CAFE_TAB.format(q=quote(keyword))), n)

    def place_ids(self, keyword: str, n: int) -> list[str]:
        return extract_place_ids(self._html(PLACE_SEARCH.format(q=quote(keyword)), scrolls=1), n)
