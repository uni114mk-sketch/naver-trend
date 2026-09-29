"""불법 의료광고 탐지·정리 CLI.

  python run.py collect [--region 강남 잠실] [--date 2026-09-22] [--limit 5]
  python run.py report --date 2026-09-22          # 신고용.txt / 전체.xlsx 다시 생성
  python run.py mark-reported URL [URL ...]        # 신고 완료 표시
  python run.py import-status output/2026-09-22/전체.xlsx   # 엑셀에서 편집한 상태 반영
  python run.py check-alive                        # 신고한 글이 삭제됐는지 확인
  python run.py pptx [--month 2026-09]             # 신고 기록 PPT 생성
  python run.py status

  # 팀 공유 (Google 시트 + Drive)
  python run.py sheet-init                         # 시트·Drive 폴더 생성 (최초 1회)
  python run.py sheet-push --date 2026-09-22       # 수집 결과를 시트·Drive 에 올림 (collect 가 자동으로 하지만 재시도용)
  python run.py sheet-sync                         # 시트에서 팀원이 바꾼 상태를 가져옴
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from adwatch.config import load_settings
from adwatch.db import Store
from adwatch.models import STATUS_ALIVE, STATUS_DELETED, STATUS_REPORTED
from adwatch.pipeline import LiveBackends, Pipeline


def _maybe_sync(s, store):
    if s.google_enabled:
        from adwatch.gsheet import sync_from_sheet
        print(f"시트 동기화: {sync_from_sheet(s, store)}건 갱신")


def cmd_collect(a, s, store):
    _maybe_sync(s, store)
    with LiveBackends(s) as b:
        results = Pipeline(s, store, b).run(run_date=a.date, regions=a.region, limit=a.limit)
    run_date = a.date or datetime.now().strftime("%Y-%m-%d")
    c = Counter(f.status for f in results)
    print(f"\n처리 {len(results)}건: " + ", ".join(f"{k} {v}" for k, v in c.items()))
    print(f"결과: {s.output_dir / run_date}")
    if s.google_enabled:
        _push(s, store, run_date)


def _push(s, store, run_date):
    from adwatch.gsheet import publish_run
    r = publish_run(s, store, run_date)
    print(f"시트에 {r['rows']}건 추가 → {r['sheet_url']}\n캡처 폴더 → {r['drive_url']}")


def cmd_sheet_init(a, s, store):
    from adwatch.gsheet import DriveFolder, TeamSheet, get_credentials
    creds = get_credentials(s.google_dir)
    sheet = TeamSheet(creds, s.sheet_id)
    sheet.init(list(s.regions))
    drive = DriveFolder(creds, s.drive_folder_id)
    print(f"시트: {sheet.url}\nDrive: {drive.root_url}")
    print(f"\n.env 에 아래 두 줄을 넣으세요:\nGOOGLE_SHEET_ID={sheet.sh.id}\nGOOGLE_DRIVE_FOLDER_ID={drive.root}")
    print("config.yaml 의 google.enabled 를 true 로 바꾸면 이후 collect 가 자동으로 올립니다.")


def cmd_sheet_push(a, s, store):
    _push(s, store, a.date)


def cmd_sheet_sync(a, s, store):
    from adwatch.gsheet import sync_from_sheet
    print(f"{sync_from_sheet(s, store)}건 갱신")


def cmd_report(a, s, store):
    class _NoBackends:  # 리포트만 다시 쓸 때는 네트워크 불필요
        pass
    out = Pipeline(s, store, _NoBackends()).write_reports(a.date)
    print(f"생성: {out}")


def cmd_mark(a, s, store):
    for url in a.urls:
        ok = store.mark_reported(url, a.date)
        print(("신고함 " if ok else "URL 없음 ") + url)


def cmd_import(a, s, store):
    from adwatch.report.xlsx import read_status
    n = 0
    for row in read_status(Path(a.path)):
        f = store.get(row["url"])
        if not f or not row["status"] or (row["status"] == f.status and row["result"] == f.result
                                          and row["reported_at"] == f.reported_at):
            continue
        if row["status"] == STATUS_REPORTED and not f.reported_at:
            store.mark_reported(row["url"], row["reported_at"] or None)
        store.set_status(row["url"], row["status"], row["result"])
        if row["reported_at"]:
            store.conn.execute("UPDATE findings SET reported_at=? WHERE url=?", (row["reported_at"], row["url"]))
            store.conn.commit()
        n += 1
    print(f"{n}건 상태 갱신")


def cmd_alive(a, s, store):
    from adwatch.alive import is_alive
    _maybe_sync(s, store)
    items = store.by_status(STATUS_REPORTED, STATUS_ALIVE)
    deleted, changed = 0, {}
    for f in items:
        alive = is_alive(f.url)
        store.set_alive(f.url, alive)
        if not alive:
            store.set_status(f.url, STATUS_DELETED, "삭제 확인")
            changed[f.url] = (STATUS_DELETED, "삭제 확인")
            deleted += 1
        elif f.status == STATUS_REPORTED:
            store.set_status(f.url, STATUS_ALIVE)
            changed[f.url] = (STATUS_ALIVE, "")
        print(("유지  " if alive else "삭제됨 ") + f.url)
    print(f"\n확인 {len(items)}건, 삭제됨 {deleted}건")
    if s.google_enabled and changed:
        from adwatch.gsheet import push_status_to_sheet
        print(f"시트 반영 {push_status_to_sheet(s, changed)}건")


def cmd_pptx(a, s, store):
    from adwatch.report.pptx import write_pptx
    _maybe_sync(s, store)
    month = a.month or datetime.now().strftime("%Y-%m")
    items = store.reported_in_month(month)
    out = write_pptx(s.output_dir / "records" / f"신고기록_{month}.pptx", month, items, s.pptx_per_item_slides)
    print(f"{len(items)}건 → {out}")


def cmd_status(a, s, store):
    rows = store.conn.execute("SELECT status, COUNT(*) FROM findings GROUP BY status").fetchall()
    for st, n in rows:
        print(f"{st:6s} {n}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect"); c.add_argument("--region", nargs="*"); c.add_argument("--date"); c.add_argument("--limit", type=int)
    c.set_defaults(fn=cmd_collect)
    r = sub.add_parser("report"); r.add_argument("--date", required=True); r.set_defaults(fn=cmd_report)
    m = sub.add_parser("mark-reported"); m.add_argument("urls", nargs="+"); m.add_argument("--date"); m.set_defaults(fn=cmd_mark)
    i = sub.add_parser("import-status"); i.add_argument("path"); i.set_defaults(fn=cmd_import)
    sub.add_parser("check-alive").set_defaults(fn=cmd_alive)
    x = sub.add_parser("pptx"); x.add_argument("--month"); x.set_defaults(fn=cmd_pptx)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("sheet-init").set_defaults(fn=cmd_sheet_init)
    sp = sub.add_parser("sheet-push"); sp.add_argument("--date", required=True); sp.set_defaults(fn=cmd_sheet_push)
    sub.add_parser("sheet-sync").set_defaults(fn=cmd_sheet_sync)

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    s = load_settings(a.config)
    store = Store(s.db_path)
    try:
        a.fn(a, s, store)
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
