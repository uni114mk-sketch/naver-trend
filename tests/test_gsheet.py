from adwatch.gsheet import HEADERS, finding_to_row, parse_rows, report_block_formula, summary_formulas
from adwatch.models import Finding


def test_row_roundtrip():
    f = Finding(url="https://blog.naver.com/a/1", medium="blog", region="강남", keyword="강남피부과", run_date="2026-09-22",
                seq=1, clinic_name="OO피부과", violation_type="비의료인 미심의 의료광고", confidence="높음",
                summary="근거", screenshot="/x/강남_블로그_01.png", status="후보")
    row = finding_to_row(f, "https://drive.google.com/file/d/abc/view")
    assert len(row) == len(HEADERS)
    parsed = parse_rows([HEADERS, row])
    r = parsed[f.url]
    assert r["지역"] == "강남" and r["매체"] == "블로그" and r["상태"] == "후보"
    assert r["캡처"].startswith("https://drive.google.com")
    assert finding_to_row(f)[HEADERS.index("캡처")] == "강남_블로그_01.png"   # 링크 없으면 파일명


def test_parse_rows_handles_short_rows_and_blank_url():
    parsed = parse_rows([HEADERS, ["강남", "블로그"], ["강남", "카페", 1, "https://cafe.naver.com/c/1"]])
    assert list(parsed) == ["https://cafe.naver.com/c/1"]
    assert parsed["https://cafe.naver.com/c/1"]["상태"] == ""


def test_summary_formulas_shape():
    rows = summary_formulas(["강남", "잠실"])
    assert rows[1][0] == "지역" and rows[2][0] == "강남" and rows[3][0] == "잠실"
    assert rows[2][1].startswith("=COUNTIFS(전체!$A:$A,$A3")
    assert rows[4][0] == "합계"
    assert any(r and r[0] == "매체별 현황" for r in rows)


def test_report_block_formula_mentions_all_media():
    f = report_block_formula()
    assert f.startswith("=IF($B$1=")
    for label in ("블로그", "카페", "플레이스"):
        assert f"■ {label}" in f
    assert f.count("(") == f.count(")")
