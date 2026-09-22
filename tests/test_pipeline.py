from pathlib import Path

import pytest
from PIL import Image

from adwatch.collectors.search_tab import extract_blog_urls, extract_cafe_urls, extract_place_ids
from adwatch.config import Settings
from adwatch.db import Store
from adwatch.evidence import mobile_url, parse_post_html
from adwatch.models import Evidence, PlaceVerdict, PostVerdict, STATUS_CANDIDATE, STATUS_NONE, STATUS_OWN
from adwatch.pipeline import Pipeline
from adwatch.report.pptx import write_pptx
from adwatch.report.txt import render_region
from adwatch.report.xlsx import read_status

FIX = Path(__file__).parent / "fixtures"


def test_extract_urls_from_search_tab():
    html = (FIX / "blog_tab.html").read_text(encoding="utf-8")
    blogs = extract_blog_urls(html, 10)
    assert [b["url"] for b in blogs] == [
        "https://blog.naver.com/alpha/223000000001",
        "https://blog.naver.com/beta/223000000002",
        "https://blog.naver.com/gamma/223000000003",
    ]
    assert blogs[0]["author"] == "alpha"
    cafes = extract_cafe_urls(html, 10)
    assert {c["url"] for c in cafes} == {"https://cafe.naver.com/skincafe/12345", "https://cafe.naver.com/skincafe/12346"}
    assert extract_place_ids(html, 10) == ["1234567890", "9876543210"]


def test_parse_post_html_and_mobile_url():
    text, images, ok = parse_post_html((FIX / "blog_post.html").read_text(encoding="utf-8"))
    assert ok and "OO피부과의원" in text and "99,000원" in text
    assert images == ["https://postfiles.pstatic.net/a/img1.jpg?type=w966", "https://postfiles.pstatic.net/a/img2.jpg?type=w966"]
    assert mobile_url("https://blog.naver.com/alpha/1") == "https://m.blog.naver.com/alpha/1"
    assert mobile_url("https://cafe.naver.com/c/2") == "https://m.cafe.naver.com/c/2"


class FakeBackends:
    """네트워크 없이 파이프라인 전체를 도는 가짜 구현."""
    def __init__(self):
        self.classified = []

    def blog_urls(self, keyword, n):
        return [
            {"url": f"https://blog.naver.com/u1/{keyword}1", "author": "u1", "title": "체험단 후기"},
            {"url": f"https://blog.naver.com/u2/{keyword}2", "author": "u2", "title": "피부 팁"},
            {"url": f"https://blog.naver.com/own/{keyword}3", "author": "own", "title": "자사"},
            {"url": f"https://blog.naver.com/u4/{keyword}4", "author": "u4", "title": "자사 언급"},
        ]

    def cafe_urls(self, keyword, n):
        return [{"url": f"https://cafe.naver.com/c/{keyword}9", "author": "c", "title": "회원전용"}]

    def place_ids(self, keyword, n):
        return ["111", "222"]

    def capture_place(self, pid, out_path):
        Image.new("RGB", (100, 100), "white").save(out_path)
        return {"name": f"플레이스{pid}", "screenshot": str(out_path)}

    def collect_evidence(self, url, screenshot_path, image_dir):
        Image.new("RGB", (100, 200), "white").save(screenshot_path)
        if "cafe" in url:
            return Evidence(accessible=False, note="로그인 필요", screenshot_path=str(screenshot_path))
        text = "유앤아이의원 강남점 후기" if "/u4/" in url else "OO피부과 원내 사진, 99,000원 이벤트"
        return Evidence(text=text, screenshot_path=str(screenshot_path))

    def classify_post(self, text, image_paths, url, medium_label):
        self.classified.append(url)
        if "/u2/" in url:
            return PostVerdict(clinic_identified=False, author_type="제3자", has_review_number=False,
                               violation_type="해당없음", confidence="높음", summary="일반 피부 관리 팁")
        return PostVerdict(clinic_identified=True, clinic_name="OO피부과의원", identification_basis=["병원명", "원내 인테리어"],
                           author_type="제3자", ad_signals=["가격", "체험단"], has_review_number=False,
                           violation_type="비의료인 미심의 의료광고", confidence="높음",
                           summary="제3자 블로그가 OO피부과 원내 사진과 가격을 게시함. 심의필 없음.")

    def classify_place(self, screenshot_path, place_name, url):
        exposed = place_name.endswith("111")
        return PlaceVerdict(price_exposed=exposed, evidence_text="피코토닝 99,000원" if exposed else "",
                            clinic_name=place_name, confidence="높음",
                            summary="대표 이미지에 가격 노출" if exposed else "가격 노출 없음")


@pytest.fixture
def env(tmp_path):
    s = Settings(regions={"강남": ["강남피부과"], "잠실": ["잠실피부과"]}, own_brand_keywords=["유앤아이의원", "유앤아이"],
                 own_blog_ids=["own"], own_cafe_ids=[], media=["blog", "cafe", "place"], top_n=10, place_top_n=5,
                 use_search_tab=True, max_images_per_post=3, delay_seconds=0, model="m", effort="low",
                 pptx_per_item_slides=True, db_path=tmp_path / "t.db", output_dir=tmp_path / "out")
    store = Store(s.db_path)
    yield s, store, tmp_path
    store.close()


def test_full_run_outputs(env):
    s, store, tmp = env
    b = FakeBackends()
    results = Pipeline(s, store, b).run(run_date="2026-09-22", regions=["강남"])
    by = {f.url: f for f in results}
    assert by["https://blog.naver.com/u1/강남피부과1"].status == STATUS_CANDIDATE
    assert by["https://blog.naver.com/u2/강남피부과2"].status == STATUS_NONE
    assert by["https://blog.naver.com/own/강남피부과3"].status == STATUS_OWN          # 자사 채널
    assert by["https://blog.naver.com/u4/강남피부과4"].status == STATUS_OWN          # 자사 브랜드 언급 → 판정 호출 안 함
    assert "https://blog.naver.com/u4/강남피부과4" not in b.classified
    assert by["https://cafe.naver.com/c/강남피부과9"].status == "수동확인"
    assert by["https://map.naver.com/p/entry/place/111"].status == STATUS_CANDIDATE
    assert by["https://map.naver.com/p/entry/place/222"].status == STATUS_NONE

    run_dir = tmp / "out" / "2026-09-22"
    assert (run_dir / "강남" / "강남_블로그_01.png").exists()
    assert (run_dir / "강남" / "강남_카페_01.png").exists()
    assert (run_dir / "강남" / "강남_플레이스_01.png").exists()
    assert not (run_dir / "강남" / "강남_블로그_02.png").exists()   # 후보 아닌 건은 번호를 먹지 않음
    assert (run_dir / "강남" / "_기타").is_dir()
    txt = (run_dir / "강남" / "신고용.txt").read_text(encoding="utf-8")
    assert txt.startswith("# 강남 (2026-09-22 수집분)")
    assert "■ 블로그 (1건)" in txt and "■ 카페 (1건)" in txt and "■ 플레이스 (1건)" in txt
    assert "강남_블로그_01.png" in txt and "OO피부과의원" in txt
    assert (run_dir / "전체.xlsx").exists()
    rows = read_status(run_dir / "전체.xlsx")
    assert {r["url"] for r in rows} >= {"https://blog.naver.com/u1/강남피부과1", "https://map.naver.com/p/entry/place/111"}

    # 재실행 시 이미 본 URL 은 건너뜀
    again = Pipeline(s, store, b).run(run_date="2026-09-23", regions=["강남"])
    assert again == []


def test_mark_reported_and_pptx(env):
    s, store, tmp = env
    Pipeline(s, store, FakeBackends()).run(run_date="2026-09-22", regions=["강남"])
    assert store.mark_reported("https://blog.naver.com/u1/강남피부과1", "2026-09-23")
    assert store.mark_reported("https://map.naver.com/p/entry/place/111", "2026-09-23")
    items = store.reported_in_month("2026-09")
    assert len(items) == 2
    out = write_pptx(tmp / "records" / "신고기록_2026-09.pptx", "2026-09", items, True)
    from pptx import Presentation
    prs = Presentation(str(out))
    assert len(prs.slides) == 1 + 1 + 2   # 표지 + 지역 요약 + 건별 2장
    assert store.reported_in_month("2026-10") == []


def test_render_region_empty():
    assert "(신고 후보 없음)" in render_region("잠실", "2026-09-22", [])
