"""팀 공유 Google 시트 + Drive 연동.

시트 구성
  전체   : 후보 한 건 = 한 행. 팀원은 상태(드롭다운)·신고일·처리 결과·담당자·메모만 편집
  요약   : 지역 × 상태 건수, 매체별, 월별 신고 건수 (수식)
  신고용 : B1 에서 지역 선택 → 복사용 블록 자동 생성 (수식)

인증: 공유 Google 계정으로 OAuth (google/credentials.json → google/token.json 생성)
      또는 서비스 계정 (google/service_account.json). README 참고.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from .models import (
    MEDIUM_LABEL, STATUS_ALIVE, STATUS_CANDIDATE, STATUS_DELETED, STATUS_MANUAL, STATUS_NONE, STATUS_OWN,
    STATUS_REPORTED, Finding,
)

log = logging.getLogger("adwatch.gsheet")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
HEADERS = ["지역", "매체", "번호", "URL", "특정 병원", "위반 유형", "확신도", "근거", "캡처",
           "상태", "신고일", "처리 결과", "담당자", "메모", "키워드", "수집일", "작성자"]
COL = {h: i for i, h in enumerate(HEADERS)}          # 0-based
STATUS_CHOICES = [STATUS_CANDIDATE, STATUS_MANUAL, STATUS_REPORTED, STATUS_DELETED, STATUS_ALIVE, STATUS_NONE, STATUS_OWN]
STATUS_COLORS = {  # 조건부 서식 (배경색)
    STATUS_CANDIDATE: (1.0, 0.95, 0.80), STATUS_MANUAL: (1.0, 0.90, 0.90), STATUS_REPORTED: (0.85, 0.92, 1.0),
    STATUS_DELETED: (0.85, 0.95, 0.85), STATUS_ALIVE: (0.95, 0.95, 0.95),
}
EDITABLE = ["상태", "신고일", "처리 결과", "담당자", "메모"]   # 시트 → DB 로 가져오는 열


# ---------- 인증 ----------
def get_credentials(google_dir: str | Path = "google"):
    """service_account.json 이 있으면 서비스 계정, 아니면 OAuth(브라우저 로그인 1회, token.json 저장)."""
    google_dir = Path(google_dir)
    sa = google_dir / "service_account.json"
    if sa.exists():
        from google.oauth2.service_account import Credentials
        return Credentials.from_service_account_file(str(sa), scopes=SCOPES)
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    token, client = google_dir / "token.json", google_dir / "credentials.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not client.exists():
            raise FileNotFoundError(f"{client} 가 없습니다. README 의 'Google 연동' 순서대로 OAuth 클라이언트를 만들어 넣으세요.")
        creds = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES).run_local_server(port=0)
    token.write_text(creds.to_json(), encoding="utf-8")
    return creds


# ---------- 순수 함수 (테스트 대상) ----------
def finding_to_row(f: Finding, capture_link: str = "") -> list:
    cap = capture_link or (Path(f.screenshot).name if f.screenshot else "")
    return [f.region, f.medium_label, f.seq or "", f.url, f.clinic_name, f.violation_type, f.confidence, f.summary,
            cap, f.status, f.reported_at, f.result, "", "", f.keyword, f.run_date, f.author]


def parse_rows(values: list[list]) -> dict[str, dict]:
    """전체 탭 값 → {url: {열이름: 값}}. 헤더 행이 첫 줄이라고 가정."""
    if not values:
        return {}
    header = [str(h).strip() for h in values[0]]
    out = {}
    for r in values[1:]:
        r = list(r) + [""] * (len(header) - len(r))
        row = {h: str(r[i]).strip() for i, h in enumerate(header)}
        if row.get("URL"):
            out[row["URL"]] = row
    return out


def summary_formulas(regions: list[str]) -> list[list]:
    """요약 탭 내용. 전체 탭을 참조하는 COUNTIFS 수식."""
    rows = [["지역별 현황"], ["지역"] + STATUS_CHOICES + ["합계"]]
    for i, region in enumerate(regions, start=3):
        rows.append([region] + [f'=COUNTIFS(전체!$A:$A,$A{i},전체!$J:$J,{_col_letter(j)}$2)' for j in range(1, len(STATUS_CHOICES) + 1)]
                    + [f'=COUNTIF(전체!$A:$A,$A{i})'])
    n = len(regions) + 2
    rows.append(["합계"] + [f'=SUM({_col_letter(j)}3:{_col_letter(j)}{n})' for j in range(1, len(STATUS_CHOICES) + 2)])
    rows += [[], ["매체별 현황"], ["매체", "후보", "신고함", "삭제됨"]]
    for label in MEDIUM_LABEL.values():
        rows.append([label] + [f'=COUNTIFS(전체!$B:$B,"{label}",전체!$J:$J,"{s}")' for s in (STATUS_CANDIDATE, STATUS_REPORTED, STATUS_DELETED)])
    rows += [[], ["월별 신고 건수 (신고일 기준)"], ["월", "신고 건수", "삭제 확인"]]
    start = n + 9
    for k in range(12):
        r = start + k
        rows.append([f'=IF({k}=0,TEXT(TODAY(),"yyyy-mm"),TEXT(EDATE(DATE(LEFT(A{start},4),MID(A{start},6,2),1),-{k}),"yyyy-mm"))',
                     f'=COUNTIFS(전체!$K:$K,A{r}&"*")',
                     f'=COUNTIFS(전체!$K:$K,A{r}&"*",전체!$J:$J,"{STATUS_DELETED}")'])
    return rows


def report_block_formula() -> str:
    """신고용 탭: B1 = 지역. 후보·수동확인 상태인 건을 매체별로 묶어 복사용 텍스트 생성."""
    cond = '(전체!$A$2:$A=$B$1)*((전체!$J$2:$J="후보")+(전체!$J$2:$J="수동확인"))'
    def block(label: str) -> str:
        c = f'{cond}*(전체!$B$2:$B="{label}")'
        line = ('TEXT(전체!$C$2:$C,"0")&". "&전체!$D$2:$D&CHAR(10)'
                '&IF(전체!$E$2:$E<>"","   - 특정 병원: "&전체!$E$2:$E&CHAR(10),"")'
                '&"   - 유형: "&전체!$F$2:$F&IF(전체!$G$2:$G<>""," [확신도 "&전체!$G$2:$G&"]","")&CHAR(10)'
                '&IF(전체!$H$2:$H<>"","   - 근거: "&전체!$H$2:$H&CHAR(10),"")'
                '&"   - 캡처: "&전체!$I$2:$I')
        return (f'IF(SUMPRODUCT({c})=0,"","■ {label} ("&SUMPRODUCT({c})&"건)"&CHAR(10)'
                f'&TEXTJOIN(CHAR(10),TRUE,ARRAYFORMULA(IF({c},{line},"")))&CHAR(10)&CHAR(10))')
    return ('=IF($B$1="","지역을 선택하세요","# "&$B$1&" ("&TEXT(TODAY(),"yyyy-mm-dd")&" 기준)"&CHAR(10)&CHAR(10)&'
            + "&".join(block(l) for l in MEDIUM_LABEL.values()) + ")")


def _col_letter(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, r = divmod(idx - 1, 26)
        s = chr(65 + r) + s
    return s


# ---------- 시트 ----------
class TeamSheet:
    def __init__(self, creds, spreadsheet_id: str = "", title: str = "불법 의료광고 신고 관리"):
        import gspread
        self.gc = gspread.authorize(creds)
        if spreadsheet_id:
            self.sh = self.gc.open_by_key(spreadsheet_id)
        else:
            self.sh = self.gc.create(title)
            log.info("새 스프레드시트 생성: %s", self.sh.url)

    @property
    def url(self) -> str:
        return self.sh.url

    def _ws(self, title: str, rows: int = 1000, cols: int = 20):
        try:
            return self.sh.worksheet(title)
        except Exception:
            return self.sh.add_worksheet(title, rows, cols)

    def init(self, regions: list[str]) -> None:
        """탭·헤더·드롭다운·조건부 서식·요약 수식 생성. 여러 번 실행해도 안전."""
        from gspread.utils import ValidationConditionType
        ws = self._ws("전체", rows=2000, cols=len(HEADERS))
        if not ws.row_values(1):
            ws.update([HEADERS], "A1")
        ws.freeze(rows=1)
        ws.format("A1:Q1", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.87, "green": 0.92, "blue": 0.97}})
        ws.add_validation("J2:J2000", ValidationConditionType.one_of_list, STATUS_CHOICES, showCustomUi=True, strict=True)
        self._status_colors(ws)
        self._set_widths(ws, {"D": 320, "E": 140, "F": 180, "H": 360, "I": 160, "N": 200})

        summ = self._ws("요약", rows=200, cols=12)
        summ.clear()
        summ.update(summary_formulas(regions), "A1", raw=False)
        summ.format("A1:L1", {"textFormat": {"bold": True}})

        rep = self._ws("신고용", rows=10, cols=3)
        rep.update([["지역", ""], ["", ""], ["아래 블록을 복사해서 민원 본문에 붙여 넣으세요. 상태가 후보/수동확인 인 건만 포함됩니다."]], "A1", raw=False)
        rep.add_validation("B1", ValidationConditionType.one_of_list, regions, showCustomUi=True)
        rep.update([[report_block_formula()]], "A4", raw=False)
        rep.format("A4", {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"})
        self._set_widths(rep, {"A": 900})
        # 기본 시트(Sheet1) 정리
        for w in self.sh.worksheets():
            if w.title in ("Sheet1", "시트1") and len(self.sh.worksheets()) > 3:
                self.sh.del_worksheet(w)

    def existing_urls(self) -> set[str]:
        ws = self._ws("전체")
        return set(ws.col_values(COL["URL"] + 1)[1:])

    def append_findings(self, items: list[Finding], links: dict[str, str] | None = None) -> int:
        """새 후보만 전체 탭에 추가. links = {url: 캡처 Drive 링크}"""
        links = links or {}
        known = self.existing_urls()
        rows = [finding_to_row(f, links.get(f.url, "")) for f in items if f.url not in known]
        if rows:
            self._ws("전체").append_rows(rows, value_input_option="USER_ENTERED")
        return len(rows)

    def read_all(self) -> dict[str, dict]:
        return parse_rows(self._ws("전체").get_all_values())

    def update_status(self, url: str, status: str, result: str = "") -> bool:
        ws = self._ws("전체")
        cell = ws.find(url, in_column=COL["URL"] + 1)
        if not cell:
            return False
        ws.update_cell(cell.row, COL["상태"] + 1, status)
        if result:
            ws.update_cell(cell.row, COL["처리 결과"] + 1, result)
        return True

    # -- 서식 --
    def _status_colors(self, ws) -> None:
        reqs = []
        for status, (r, g, b) in STATUS_COLORS.items():
            reqs.append({"addConditionalFormatRule": {"rule": {
                "ranges": [{"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": COL["상태"], "endColumnIndex": COL["상태"] + 1}],
                "booleanRule": {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": status}]},
                                "format": {"backgroundColor": {"red": r, "green": g, "blue": b}}}}, "index": 0}})
        self.sh.batch_update({"requests": reqs})

    def _set_widths(self, ws, widths: dict[str, int]) -> None:
        reqs = []
        for letter, px in widths.items():
            idx = ord(letter) - 65
            reqs.append({"updateDimensionProperties": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS", "startIndex": idx, "endIndex": idx + 1},
                "properties": {"pixelSize": px}, "fields": "pixelSize"}})
        self.sh.batch_update({"requests": reqs})


# ---------- Drive ----------
class DriveFolder:
    """캡처 업로드. root 폴더 아래 수집일/지역 폴더를 만들고 PNG 를 올린 뒤 보기 링크 반환."""

    def __init__(self, creds, root_folder_id: str = "", root_name: str = "불법광고_캡처"):
        from googleapiclient.discovery import build
        self.svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        self.root = root_folder_id or self._ensure_folder(root_name, None)
        self._cache: dict[tuple[str, str | None], str] = {}

    def _ensure_folder(self, name: str, parent: str | None) -> str:
        key = (name, parent)
        if key in self._cache:
            return self._cache[key]
        q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent:
            q += f" and '{parent}' in parents"
        res = self.svc.files().list(q=q, fields="files(id)", pageSize=1).execute().get("files", [])
        if res:
            fid = res[0]["id"]
        else:
            meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
            if parent:
                meta["parents"] = [parent]
            fid = self.svc.files().create(body=meta, fields="id").execute()["id"]
        self._cache[key] = fid
        return fid

    def upload(self, path: str | Path, run_date: str, region: str) -> str:
        from googleapiclient.http import MediaFileUpload
        path = Path(path)
        folder = self._ensure_folder(region, self._ensure_folder(run_date, self.root))
        media = MediaFileUpload(str(path), mimetype="image/png", resumable=False)
        f = self.svc.files().create(body={"name": path.name, "parents": [folder]}, media_body=media,
                                    fields="id, webViewLink").execute()
        return f.get("webViewLink", "")

    @property
    def root_url(self) -> str:
        return f"https://drive.google.com/drive/folders/{self.root}"


# ---------- 파이프라인 연결 ----------
def publish_run(settings, store, run_date: str) -> dict:
    """수집 결과 중 신고 후보를 Drive + 시트에 올림. 반환: {'rows': n, 'sheet_url': ..., 'drive_url': ...}"""
    creds = get_credentials(settings.google_dir)
    sheet = TeamSheet(creds, settings.sheet_id)
    drive = DriveFolder(creds, settings.drive_folder_id)
    items = [f for f in store.by_run(run_date) if f.is_reportable]
    known = sheet.existing_urls()
    links = {}
    for f in items:
        if f.url in known or not f.screenshot or not Path(f.screenshot).exists():
            continue
        try:
            links[f.url] = drive.upload(f.screenshot, run_date, f.region)
        except Exception as e:
            log.warning("Drive 업로드 실패 %s: %s", f.screenshot, e)
    n = sheet.append_findings([f for f in items if f.url not in known], links)
    return {"rows": n, "sheet_url": sheet.url, "drive_url": drive.root_url}


def sync_from_sheet(settings, store) -> int:
    """시트에서 팀원이 바꾼 상태·신고일·처리 결과를 DB 로 가져옴. 반환: 갱신 건수"""
    creds = get_credentials(settings.google_dir)
    sheet = TeamSheet(creds, settings.sheet_id)
    n = 0
    for url, row in sheet.read_all().items():
        f = store.get(url)
        if not f:
            continue
        status, reported_at, result = row.get("상태", ""), row.get("신고일", ""), row.get("처리 결과", "")
        if status == STATUS_REPORTED and not reported_at:
            reported_at = datetime.now().strftime("%Y-%m-%d")
        if (status, reported_at, result) == (f.status, f.reported_at, f.result) or not status:
            continue
        store.set_status(url, status, result)
        if reported_at:
            store.conn.execute("UPDATE findings SET reported_at=? WHERE url=?", (reported_at, url))
            store.conn.commit()
        n += 1
    return n


def push_status_to_sheet(settings, urls_status: dict[str, tuple[str, str]]) -> int:
    """check-alive 결과 등을 시트에 반영. urls_status = {url: (status, result)}"""
    if not urls_status:
        return 0
    creds = get_credentials(settings.google_dir)
    sheet = TeamSheet(creds, settings.sheet_id)
    return sum(1 for u, (st, res) in urls_status.items() if sheet.update_status(u, st, res))
