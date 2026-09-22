"""신고한 URL 이 아직 살아 있는지 확인."""
from __future__ import annotations

import requests

from .evidence import mobile_url

DELETED_HINTS = ("삭제된 게시글", "존재하지 않는", "찾을 수 없습니다", "삭제되었거나", "비공개", "게시물이 없습니다")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"


def is_alive(url: str, timeout: float = 15) -> bool:
    try:
        r = requests.get(mobile_url(url), timeout=timeout, headers={"User-Agent": UA}, allow_redirects=True)
    except requests.RequestException:
        return True  # 네트워크 오류는 '유지'로 간주 (오판으로 삭제 처리하지 않음)
    if r.status_code == 404:
        return False
    head = r.text[:5000]
    return not any(h in head for h in DELETED_HINTS)
