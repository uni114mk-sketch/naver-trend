"""수집 결과를 대시보드 페이지의 results/<지역id> 문서 형식으로 변환.
채팅(Claude Code)에서 ArtifactData 로 그대로 올리면 팀 대시보드 탭에 나타난다."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .db import Store
from .models import STATUS_CANDIDATE, STATUS_MANUAL, STATUS_OWN


def region_id(region: str) -> str:
    return hashlib.sha1(region.encode("utf-8")).hexdigest()[:10]


def build_doc(store: Store, run_date: str, region: str, keywords: list[str], by: str = "claude-code") -> dict:
    doc = {"run_at": run_date + " " + datetime.now().strftime("%H:%M"), "by": by, "keywords": keywords,
           "blog": [], "cafe": [], "place": [], "own_skipped": 0, "errors": []}
    for f in store.by_run(run_date):
        if f.region != region:
            continue
        if f.status == STATUS_OWN:
            doc["own_skipped"] += 1
            continue
        if f.status not in (STATUS_CANDIDATE, STATUS_MANUAL):
            continue
        clinics = [f.clinic_name] if f.clinic_name else []
        row = {"url": f.url, "title": f.title, "desc": f.summary, "keyword": f.keyword, "rank": f.seq, "clinics": clinics, "author": f.author}
        if f.medium == "place":
            row["address"] = ""
            row["clinics"] = [f.clinic_name or f.title]
            doc["place"].append(row)
        else:
            doc[f.medium].append(row)
    return doc


def write_doc(store: Store, run_date: str, region: str, keywords: list[str], out_dir: Path, by: str = "claude-code") -> Path:
    doc = build_doc(store, run_date, region, keywords, by)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"dashboard_{region}.json"
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return p
