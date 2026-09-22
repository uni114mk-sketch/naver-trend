"""네이버 검색 API (블로그 / 카페글 / 지역). https://developers.naver.com/docs/serviceapi/search/"""
from __future__ import annotations

import html
import re

import requests

BASE = "https://openapi.naver.com/v1/search"
TAG_RE = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return html.unescape(TAG_RE.sub("", s or "")).strip()


class NaverSearchAPI:
    def __init__(self, client_id: str, client_secret: str, timeout: float = 15):
        if not client_id or not client_secret:
            raise ValueError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 .env 에 없습니다.")
        self.headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
        self.timeout = timeout

    def _get(self, kind: str, query: str, display: int, start: int = 1, sort: str = "sim") -> list[dict]:
        r = requests.get(
            f"{BASE}/{kind}.json",
            params={"query": query, "display": display, "start": start, "sort": sort},
            headers=self.headers,
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json().get("items", [])

    def blog(self, query: str, n: int = 30) -> list[dict]:
        """[{url, title, author}] 정확도순 상위 n개 (최대 100)."""
        out = []
        for start in range(1, min(n, 100) + 1, 100):
            for it in self._get("blog", query, min(100, n - len(out)), start):
                out.append({"url": it["link"], "title": _clean(it["title"]), "author": it.get("bloggername", "")})
                if len(out) >= n:
                    return out
        return out

    def cafe(self, query: str, n: int = 30) -> list[dict]:
        out = []
        for it in self._get("cafearticle", query, min(100, n)):
            out.append({"url": it["link"], "title": _clean(it["title"]), "author": it.get("cafename", "")})
            if len(out) >= n:
                break
        return out

    def local(self, query: str, n: int = 5) -> list[dict]:
        """지역 검색 (display 최대 5). [{name, address, link}]"""
        out = []
        for it in self._get("local", query, min(5, n)):
            out.append({
                "name": _clean(it["title"]),
                "address": it.get("roadAddress") or it.get("address", ""),
                "link": it.get("link", ""),
            })
        return out
