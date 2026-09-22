"""지역별 신고용.txt — 국민신문고 등에 그대로 붙여 넣는 블록."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from ..models import Finding

MEDIUM_ORDER = ["blog", "cafe", "place"]


def render_region(region: str, run_date: str, items: list[Finding]) -> str:
    by_medium: dict[str, list[Finding]] = defaultdict(list)
    for f in items:
        by_medium[f.medium].append(f)
    lines = [f"# {region} ({run_date} 수집분)", ""]
    total = 0
    for medium in MEDIUM_ORDER:
        group = sorted(by_medium.get(medium, []), key=lambda f: f.seq)
        if not group:
            continue
        label = group[0].medium_label
        lines.append(f"■ {label} ({len(group)}건)")
        for i, f in enumerate(group, 1):
            total += 1
            lines.append(f"{i}. {f.url}")
            if f.clinic_name:
                lines.append(f"   - 특정 병원: {f.clinic_name}")
            lines.append(f"   - 유형: {f.violation_type}" + (f" [확신도 {f.confidence}]" if f.confidence else ""))
            if f.summary:
                lines.append(f"   - 근거: {f.summary}")
            if f.screenshot:
                lines.append(f"   - 캡처: {Path(f.screenshot).name}")
        lines.append("")
    if total == 0:
        lines.append("(신고 후보 없음)")
    return "\n".join(lines).rstrip() + "\n"


def write_region_txt(out_dir: Path, region: str, run_date: str, items: list[Finding]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "신고용.txt"
    p.write_text(render_region(region, run_date, items), encoding="utf-8")
    return p
