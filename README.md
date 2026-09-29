# adwatch — 불법 의료광고 탐지·정리 도구

"지역명 + 피부과" 키워드로 네이버 블로그탭·카페탭·플레이스를 훑어, 특정 병원을 식별할 수 있는
비의료인 광고 게시글과 대표 이미지에 가격을 노출한 플레이스를 찾아 **지역별 → 매체별** 신고용 목록과
캡처를 만들어 줍니다. 신고 제출은 사람이 직접 하고, 신고한 건은 PPT 로 기록합니다.

## 흐름

1. `config.yaml` 의 지역/키워드 목록으로 검색 (Playwright 로 실제 검색탭을 열어 상위 N개)
2. 게시글 풀페이지 캡처 + 본문·이미지 저장
3. Claude 가 병원 특정 여부·작성 주체·광고 신호·심의필을 판정 → "후보"
4. `output/날짜/지역/신고용.txt` 와 `전체.xlsx` 로 정리. 캡처는 `지역명_매체_번호.png`
5. 사람이 확인 후 신고 → 상태를 "신고함" 으로 표시 → `신고기록_YYYY-MM.pptx` 생성
6. 주기적으로 삭제 여부 확인

```
output/
  2026-09-22/
    강남/
      신고용.txt            # "# 강남" 헤더, ■ 블로그 / ■ 카페 / ■ 플레이스 순
      강남_블로그_01.png
      강남_카페_01.png
      강남_플레이스_01.png
      _images/              # 판정에 쓴 본문 이미지
      _기타/                # 해당없음·자사로 분류된 캡처
    잠실/ ...
    전체.xlsx               # 시트 = 지역, 마지막 "제외" 시트
  records/
    신고기록_2026-09.pptx
```

## 설치 (Windows / Mac 공통)

```bash
# Python 3.11 이상
pip install -r requirements.txt
playwright install chromium
cp .env.example .env      # Windows: copy .env.example .env
```

`.env` 에 키를 넣습니다.

| 키 | 발급 위치 | 비고 |
|---|---|---|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com → 가입 → Billing 에 결제수단 등록 → **API Keys → Create Key** | 종량제. 게시글 1건 판정에 이미지 6장 기준 대략 수십 원 |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | https://developers.naver.com → 로그인 → **Application → 애플리케이션 등록** → 사용 API 에 "검색" 체크 → 등록 후 Client ID / Secret 확인 | 무료, 일 25,000회. 검색탭 열람이 막혔을 때 대체 수단이라 없어도 동작함 |

자사 공식 블로그·카페 아이디는 `config.yaml` 의 `own_channels` 에 넣습니다.
블로그 주소가 `blog.naver.com/uni_skin` 이면 `uni_skin` 이 아이디입니다. 마케팅 담당자나 대행사에 확인하면 됩니다.
비워 둬도 본문에 "유앤아이" 가 들어간 글은 자사로 걸러집니다.

## 사용

```bash
# 전체 지역 수집 (주 1회 권장). 처음엔 한 지역, 소량으로 동작 확인
python run.py collect --region 강남 --limit 5
python run.py collect

# 신고 후 상태 기록 (둘 중 편한 방법)
python run.py mark-reported https://blog.naver.com/xxx/123 https://cafe.naver.com/yyy/456
python run.py import-status output/2026-09-22/전체.xlsx     # 엑셀 "상태" 열에 신고함 이라고 적고 저장한 뒤

# 신고 기록 PPT (해당 월에 신고한 건)
python run.py pptx --month 2026-09

# 신고한 글이 삭제됐는지 확인 (상태가 삭제됨 / 유지됨 으로 바뀜)
python run.py check-alive

python run.py status
python run.py report --date 2026-09-22    # txt/xlsx 다시 생성
```

## 팀 공유 대시보드 (Google 시트 + Drive)

같은 Google 계정을 쓰는 팀원이 함께 보고 상태를 바꾸는 시트입니다. 서버 없이 동작합니다.

| 탭 | 내용 | 편집 |
|---|---|---|
| 전체 | 후보 한 건 = 한 행. 캡처는 Drive 링크 | 상태(드롭다운)·신고일·처리 결과·담당자·메모만 |
| 요약 | 지역 × 상태 건수, 매체별, 월별 신고 건수 | 수식, 편집 불필요 |
| 신고용 | B1 에서 지역 선택 → 복사용 블록 자동 생성 | B1 만 |

흐름: `collect` 가 끝나면 후보 캡처를 Drive(`불법광고_캡처/수집일/지역/`)에 올리고 시트 "전체" 탭에 추가합니다.
팀원이 시트에서 상태를 "신고함"으로 바꾸면, `pptx` / `check-alive` 실행 시 자동으로 읽어와 반영합니다.

### Google 연동 설정 (최초 1회, 공유 계정으로)

1. https://console.cloud.google.com 접속 → 프로젝트 새로 만들기 (이름 아무거나)
2. "API 및 서비스 → 라이브러리" 에서 **Google Sheets API**, **Google Drive API** 두 개를 사용 설정
3. "API 및 서비스 → OAuth 동의 화면" → 외부(또는 내부) → 앱 이름·이메일 입력 → 저장. 테스트 사용자에 공유 계정 이메일 추가
4. "API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → OAuth 클라이언트 ID" → 애플리케이션 유형 **데스크톱 앱** → 만들기 → JSON 다운로드
5. 다운로드한 파일을 `google/credentials.json` 으로 저장
6. 아래를 실행하면 브라우저가 열리고 공유 계정으로 로그인 → `google/token.json` 이 생성되고 시트·Drive 폴더가 만들어집니다.

```bash
python run.py sheet-init
```

7. 출력된 `GOOGLE_SHEET_ID`, `GOOGLE_DRIVE_FOLDER_ID` 를 `.env` 에 넣고, `config.yaml` 의 `google.enabled` 를 `true` 로 바꿉니다.

`google/` 폴더는 저장소에 올라가지 않습니다. 다른 PC 에서도 수집기를 돌리려면 `google/credentials.json` 과 `.env` 를 복사하고 한 번 로그인하면 됩니다.

```bash
python run.py sheet-push --date 2026-09-22   # 업로드 실패 시 재시도
python run.py sheet-sync                     # 시트 상태를 지금 가져오기
```

## 상태 값

| 상태 | 의미 |
|---|---|
| 후보 | 자동 판정 결과 신고 대상으로 보임. 사람이 확인 후 신고 |
| 수동확인 | 카페 회원 전용 등으로 본문을 못 읽었거나 판정 실패. 직접 열어 확인 |
| 신고함 | 신고 완료 (`mark-reported` 또는 엑셀 반영) |
| 삭제됨 / 유지됨 | `check-alive` 결과 |
| 자사 / 해당없음 | 신고 대상 아님. 재수집에서 제외되도록 DB 에만 남김 |

## 주의

- 네이버 검색 페이지 자동 열람은 약관상 회색 지대입니다. `delay_seconds` 를 줄이거나 하루 여러 번 돌리지 마세요.
  차단되면 `use_search_tab: false` 로 바꿔 검색 API 만 쓰는 방식으로 전환할 수 있습니다 (노출 순위는 다소 달라짐).
- 판정은 "후보" 입니다. 확신도 낮음은 특히 직접 확인하고, 자사 광고에도 같은 기준을 먼저 적용해 보는 것을 권합니다.
- 네이버 마크업이 바뀌면 `adwatch/collectors/search_tab.py` 의 정규식과 `adwatch/evidence.py` 의 본문 선택자를 손봐야 합니다.

## 테스트

```bash
python -m pytest -q
```
네트워크 없이 가짜 수집기·판정기로 파이프라인 전체(캡처 파일명, txt/xlsx/pptx 생성, 자사 제외, 재수집 제외)를 검증합니다.
