"""팀 대시보드(웹 페이지)와 주고받는 JSON.

export_dashboard : 수집 회차의 신고 후보를 dashboard_날짜.json 으로 (캡처는 축소 JPEG 를 base64 로 포함)
import_status    : 대시보드에서 내보낸 status_날짜.json 의 상태·신고일·처리 결과를 DB 에 반영
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

from PIL import Image

from .db import Store
from .models import STATUS_REPORTED, Finding

THUMB_WIDTH = 720        # 대시보드 캡처 폭 (px)
THUMB_MAX_HEIGHT = 6000  # 이보다 긴 풀페이지 캡처는 위쪽만
THUMB_QUALITY = 62


def _hash(s: str, n: int = 16) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]


def doc_id(run_date: str, region: str) -> str:
    """대시보드 저장소 문서 id. 경로 문자 제약 때문에 지역명은 해시로."""
    return f"{run_date}_{_hash(region, 10)}"


def item_id(url: str) -> str:
    return _hash(url, 20)


def thumbnail_data_url(path: str | Path) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        if h > THUMB_MAX_HEIGHT:
            im = im.crop((0, 0, w, THUMB_MAX_HEIGHT))
            w, h = im.size
        if w > THUMB_WIDTH:
            im = im.resize((THUMB_WIDTH, int(h * THUMB_WIDTH / w)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=THUMB_QUALITY, optimize=True)
    return "data:image/jpeg;base64," + base64.standard_b64encode(buf.getvalue()).decode()


def build_payload(items: list[Finding], run_date: str, with_thumbs: bool = True) -> dict:
    groups: dict[str, dict] = {}
    for f in items:
        g = groups.setdefault(f.region, {"doc_id": doc_id(run_date, f.region), "region": f.region, "run_date": run_date, "items": []})
        it = {
            "id": item_id(f.url), "url": f.url, "medium": f.medium_label, "seq": f.seq, "clinic": f.clinic_name,
            "violation": f.violation_type, "confidence": f.confidence, "summary": f.summary, "basis": f.basis,
            "keyword": f.keyword, "author": f.author, "title": f.title, "status": f.status,
        }
        if with_thumbs and f.screenshot and Path(f.screenshot).exists():
            try:
                it["thumb"] = thumbnail_data_url(f.screenshot)
            except Exception:
                pass
        g["items"].append(it)
    return {"format": "adwatch-dashboard/1", "run_date": run_date, "exported_at": datetime.now().isoformat(timespec="seconds"),
            "groups": list(groups.values())}


def export_dashboard(store: Store, run_date: str, out_dir: Path, with_thumbs: bool = True) -> Path:
    items = [f for f in store.by_run(run_date) if f.is_reportable]
    payload = build_payload(items, run_date, with_thumbs)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"dashboard_{run_date}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


def import_status(store: Store, path: Path) -> int:
    """대시보드 '상태 내보내기' 파일 반영. 반환: 갱신 건수"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    n = 0
    for row in data.get("items", []):
        f = store.get(row.get("url", ""))
        if not f:
            continue
        status, reported_at, result = row.get("status", ""), row.get("reported_at", ""), row.get("result", "")
        if status == STATUS_REPORTED and not reported_at:
            reported_at = datetime.now().strftime("%Y-%m-%d")
        if not status or (status, reported_at, result) == (f.status, f.reported_at, f.result):
            continue
        store.set_status(f.url, status, result)
        if reported_at:
            store.conn.execute("UPDATE findings SET reported_at=? WHERE url=?", (reported_at, f.url))
            store.conn.commit()
        n += 1
    return n
