"""gspread 를 가짜 객체로 바꿔 TeamSheet 코드 경로(초기화·추가·읽기·상태 갱신)를 통과시키는 스모크 테스트."""
import types

import gspread
import pytest

from adwatch.gsheet import HEADERS, TeamSheet
from adwatch.models import Finding


class FakeWS:
    def __init__(self, title, sid):
        self.title, self.id, self.rows = title, sid, []
        self.calls = []
    def row_values(self, i): return self.rows[i - 1] if len(self.rows) >= i else []
    def col_values(self, c): return [r[c - 1] if len(r) >= c else "" for r in self.rows]
    def update(self, values, range_name=None, raw=True, **kw):
        self.calls.append(("update", range_name))
        start = int(range_name[1:]) - 1 if range_name and range_name[1:].isdigit() else 0
        for i, v in enumerate(values):
            while len(self.rows) <= start + i:
                self.rows.append([])
            self.rows[start + i] = list(v)
        return {}
    def append_rows(self, values, **kw): self.rows += [list(v) for v in values]
    def get_all_values(self): return self.rows
    def find(self, q, in_column=None):
        for i, r in enumerate(self.rows, 1):
            if len(r) >= in_column and r[in_column - 1] == q:
                return types.SimpleNamespace(row=i)
        return None
    def update_cell(self, r, c, v):
        row = self.rows[r - 1]
        row += [""] * (c - len(row)); row[c - 1] = v
    def freeze(self, **kw): pass
    def format(self, *a, **kw): pass
    def add_validation(self, *a, **kw): self.calls.append(("validation", a[0]))
    def clear(self): self.rows = []


class FakeSheet:
    def __init__(self):
        self._ws = {}; self.url = "https://docs.google.com/spreadsheets/d/FAKE"; self.id = "FAKE"; self.batches = []
    def worksheet(self, t):
        if t not in self._ws: raise gspread.exceptions.WorksheetNotFound(t)
        return self._ws[t]
    def add_worksheet(self, title, rows, cols, index=None):
        self._ws[title] = FakeWS(title, len(self._ws)); return self._ws[title]
    def worksheets(self): return list(self._ws.values())
    def del_worksheet(self, ws): self._ws.pop(ws.title)
    def batch_update(self, body): self.batches.append(body)


@pytest.fixture
def sheet(monkeypatch):
    fake = FakeSheet()
    monkeypatch.setattr(gspread, "authorize", lambda creds: types.SimpleNamespace(open_by_key=lambda k: fake, create=lambda t: fake))
    return TeamSheet(creds=None, spreadsheet_id="FAKE")


def test_init_append_read_update(sheet):
    sheet.init(["강남", "잠실"])
    ws = sheet.sh.worksheet("전체")
    assert ws.rows[0] == HEADERS
    assert sheet.sh.worksheet("요약").rows[2][0] == "강남"
    assert sheet.sh.worksheet("신고용").rows[3][0].startswith("=IF($B$1=")
    assert any("addConditionalFormatRule" in r for b in sheet.sh.batches for r in b["requests"])

    f = Finding(url="https://blog.naver.com/a/1", medium="blog", region="강남", keyword="k", run_date="2026-09-22", seq=1, status="후보")
    assert sheet.append_findings([f], {"https://blog.naver.com/a/1": "https://drive/x"}) == 1
    assert sheet.append_findings([f]) == 0                      # 중복 추가 안 함
    assert sheet.read_all()["https://blog.naver.com/a/1"]["캡처"] == "https://drive/x"
    assert sheet.update_status("https://blog.naver.com/a/1", "삭제됨", "삭제 확인")
    assert sheet.read_all()["https://blog.naver.com/a/1"]["상태"] == "삭제됨"
    assert not sheet.update_status("https://none", "x")
