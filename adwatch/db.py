from __future__ import annotations

import sqlite3
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

from .models import Finding, STATUS_REPORTED

_COLUMNS = [f.name for f in fields(Finding)]


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        cols = ", ".join(f"{c} TEXT" if c != "seq" else "seq INTEGER" for c in _COLUMNS if c != "url")
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS findings (url TEXT PRIMARY KEY, {cols}, "
            "alive TEXT DEFAULT '', alive_checked_at TEXT DEFAULT '')"
        )
        self.conn.commit()

    def known_urls(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT url FROM findings")}

    def upsert(self, f: Finding) -> None:
        d = asdict(f)
        keys = ", ".join(d)
        marks = ", ".join("?" for _ in d)
        updates = ", ".join(f"{k}=excluded.{k}" for k in d if k != "url")
        self.conn.execute(
            f"INSERT INTO findings ({keys}) VALUES ({marks}) ON CONFLICT(url) DO UPDATE SET {updates}",
            list(d.values()),
        )
        self.conn.commit()

    def get(self, url: str) -> Finding | None:
        row = self.conn.execute("SELECT * FROM findings WHERE url=?", (url,)).fetchone()
        return _to_finding(row) if row else None

    def by_run(self, run_date: str) -> list[Finding]:
        rows = self.conn.execute(
            "SELECT * FROM findings WHERE run_date=? ORDER BY region, medium, seq", (run_date,)
        )
        return [_to_finding(r) for r in rows]

    def by_status(self, *statuses: str) -> list[Finding]:
        marks = ", ".join("?" for _ in statuses)
        rows = self.conn.execute(
            f"SELECT * FROM findings WHERE status IN ({marks}) ORDER BY region, medium, reported_at, seq",
            statuses,
        )
        return [_to_finding(r) for r in rows]

    def reported_in_month(self, month: str) -> list[Finding]:
        """month = 'YYYY-MM'. 신고함/삭제됨/유지됨 모두 포함 (신고 이력)."""
        rows = self.conn.execute(
            "SELECT * FROM findings WHERE reported_at LIKE ? ORDER BY region, medium, reported_at, seq",
            (f"{month}%",),
        )
        return [_to_finding(r) for r in rows]

    def mark_reported(self, url: str, when: str | None = None) -> bool:
        when = when or datetime.now().strftime("%Y-%m-%d")
        cur = self.conn.execute(
            "UPDATE findings SET status=?, reported_at=? WHERE url=?", (STATUS_REPORTED, when, url)
        )
        self.conn.commit()
        return cur.rowcount > 0

    def set_status(self, url: str, status: str, result: str = "") -> bool:
        cur = self.conn.execute(
            "UPDATE findings SET status=?, result=CASE WHEN ?='' THEN result ELSE ? END WHERE url=?",
            (status, result, result, url),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def set_alive(self, url: str, alive: bool) -> None:
        self.conn.execute(
            "UPDATE findings SET alive=?, alive_checked_at=? WHERE url=?",
            ("Y" if alive else "N", datetime.now().strftime("%Y-%m-%d"), url),
        )
        self.conn.commit()

    def next_seq(self, run_date: str, region: str, medium: str) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM findings WHERE run_date=? AND region=? AND medium=?",
            (run_date, region, medium),
        ).fetchone()
        return int(row[0]) + 1

    def close(self) -> None:
        self.conn.close()


def _to_finding(row: sqlite3.Row) -> Finding:
    data = {c: row[c] for c in _COLUMNS}
    data["seq"] = int(data["seq"] or 0)
    return Finding(**{k: (v if v is not None else "") for k, v in data.items()})
