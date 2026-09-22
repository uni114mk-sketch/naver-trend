"""네이버 플레이스(병원) 페이지 대표 이미지 캡처."""
from __future__ import annotations

import re
import time

PLACE_HOME = "https://m.place.naver.com/hospital/{pid}/home"
PLACE_ENTRY = "https://map.naver.com/p/entry/place/{pid}"
TITLE_RE = re.compile(r"<title>([^<]+)</title>")


def place_url(pid: str) -> str:
    return PLACE_ENTRY.format(pid=pid)


class PlaceCapturer:
    """SearchTabCollector 의 context 를 재사용해 플레이스 상단(대표 이미지 영역)을 캡처."""

    def __init__(self, context, delay_seconds: float = 2.0):
        self.context = context
        self.delay = delay_seconds

    def capture(self, pid: str, out_path: str) -> dict:
        page = self.context.new_page()
        try:
            page.set_viewport_size({"width": 480, "height": 1000})
            page.goto(PLACE_HOME.format(pid=pid), wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            page.screenshot(path=out_path, full_page=False)  # 상단 뷰포트 = 대표 이미지 + 업체명
            html_text = page.content()
            m = TITLE_RE.search(html_text)
            name = m.group(1).split(":")[0].strip() if m else ""
            return {"name": name, "screenshot": out_path, "url": place_url(pid)}
        finally:
            page.close()
            time.sleep(self.delay)
