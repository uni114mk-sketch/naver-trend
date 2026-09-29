import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_pipeline import FakeBackends  # noqa: E402

from adwatch.config import Settings
from adwatch.dashboard import build_payload, doc_id, export_dashboard, import_status, item_id
from adwatch.db import Store
from adwatch.models import STATUS_REPORTED
from adwatch.pipeline import Pipeline


def test_ids_are_path_safe_and_stable():
    d = doc_id("2026-09-22", "강남")
    assert d == doc_id("2026-09-22", "강남") and d != doc_id("2026-09-22", "잠실")
    assert all(c.isalnum() or c in "_-" for c in d)
    assert len(item_id("https://blog.naver.com/a/1")) == 20


def test_export_and_import_roundtrip(tmp_path):
    s = Settings(regions={"강남": ["강남피부과"]}, own_brand_keywords=["유앤아이"], own_blog_ids=["own"], own_cafe_ids=[],
                 media=["blog", "cafe", "place"], top_n=10, place_top_n=5, use_search_tab=True, max_images_per_post=3,
                 delay_seconds=0, model="m", effort="low", pptx_per_item_slides=True, db_path=tmp_path / "t.db", output_dir=tmp_path / "out")
    store = Store(s.db_path)
    Pipeline(s, store, FakeBackends()).run(run_date="2026-09-22")
    p = export_dashboard(store, "2026-09-22", tmp_path / "out" / "2026-09-22")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["format"] == "adwatch-dashboard/1"
    assert [g["region"] for g in data["groups"]] == ["강남"]
    items = data["groups"][0]["items"]
    assert {i["medium"] for i in items} == {"블로그", "카페", "플레이스"}      # 후보·수동확인만, 해당없음·자사 제외
    assert all(i["thumb"].startswith("data:image/jpeg;base64,") for i in items)
    assert all(i["status"] in ("후보", "수동확인") for i in items)

    # 대시보드에서 내보낸 상태 파일 반영
    url = next(i["url"] for i in items if i["medium"] == "블로그")
    status_file = tmp_path / "status.json"
    status_file.write_text(json.dumps({"items": [{"url": url, "status": "신고함", "reported_at": "2026-09-23", "result": ""},
                                                 {"url": "https://none", "status": "신고함"}]}), encoding="utf-8")
    assert import_status(store, status_file) == 1
    f = store.get(url)
    assert f.status == STATUS_REPORTED and f.reported_at == "2026-09-23"
    assert import_status(store, status_file) == 0        # 변화 없으면 0
    store.close()


def test_build_payload_without_thumbs():
    from adwatch.models import Finding
    f = Finding(url="u", medium="place", region="잠실", keyword="k", run_date="2026-09-22", seq=2, status="후보", screenshot="/nope.png")
    d = build_payload([f], "2026-09-22", with_thumbs=False)
    assert "thumb" not in d["groups"][0]["items"][0] and d["groups"][0]["items"][0]["seq"] == 2
