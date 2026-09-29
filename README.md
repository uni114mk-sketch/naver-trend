# adwatch — 불법 의료광고 탐지·정리 도구

"지역명 + 피부과" 키워드로 네이버 블로그탭·카페탭·플레이스를 훑어, 특정 병원을 식별할 수 있는
비의료인 광고 게시글과 대표 이미지에 가격을 노출한 플레이스를 찾아 **지역별 → 매체별** 신고용 목록과
캡처를 만들어 줍니다. 신고 제출은 사람이 직접 하고, 신고한 건은 PPT 로 기록합니다.

## 흐름

1. `config.yaml` 의 지역/키워드 목록으로 검색 (Playwright 로 실제 검색탭을 열어 상위 N개)
2. 게시글 풀페이지 캡처 + 본문·이미지 저장
3. Claude 가 병원 특정 여부·작성 주체·광고 신호·심의필을 판정 → "후보"
4. `output/날짜/지역/신고용.txt` 와 `전체.xlsx` 로 정리. 캡처는 `지역명_매체_번호.png`
5. 팀 대시보드에서 확인 후 신고 → "신고함" 처리 → 월말에 `신고기록_YYYY-MM.pptx` 생성
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
    dashboard_2026-09-22.json  # 팀 대시보드에 올리는 파일
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

## 팀 대시보드 (웹 페이지)

팀원 각자가 브라우저로 여는 페이지입니다. 주소는 https://claude.ai/artifact/NHV8veMWU9GR49rsHjkkd8 이고,
같은 claude.ai 계정으로 로그인하면 누구나 같은 데이터를 봅니다. 페이지 소스는 `dashboard/index.html` 입니다.

| 화면 | 내용 |
|---|---|
| 상단 타일 | 후보 / 수동확인 / 신고함 / 삭제됨 / 유지됨 건수. 누르면 그 상태만 필터 |
| 지역별 현황 | 지역 × 상태 표. 행을 누르면 그 지역만 |
| 게시글 | 캡처 미리보기, 병원명, 위반 유형, 근거, URL. 버튼으로 상태 변경, 신고일·담당자·메모 입력 |
| 신고용 텍스트 | 지역을 고르면 후보·수동확인 건이 블로그/카페/플레이스 순으로 정리된 복사용 블록. 복사 후 "전체 신고함 처리" 가능 |
| 상태 내보내기 | 전체 상태를 `status_날짜.json` 으로 저장. 수집 PC 에서 PPT 를 만들 때 사용 |

### 흐름

1. 수집 PC: `python run.py collect` → `output/날짜/dashboard_날짜.json` 이 생김 (후보 캡처 축소본 포함)
2. 대시보드: **수집 결과 가져오기** 에 그 파일을 끌어다 놓음 → 후보 목록·캡처가 팀 전체에 보임
3. 팀원: 확인 → 신고 → **신고함으로** 버튼 (신고일·담당자 자동 기록) → 메모에 접수번호 기록
4. 월말: 대시보드에서 **상태 내보내기** → 수집 PC 에서

```bash
python run.py import-status status_2026-09-30.json   # 대시보드 상태를 DB 에 반영
python run.py check-alive                            # 삭제 여부 확인 (결과는 다시 대시보드에서 직접 반영)
python run.py pptx --month 2026-09                   # 신고 기록 PPT
```

이미 올린 URL 은 다시 올려도 중복되지 않습니다. 수집일 옆 ✕ 로 회차 전체를 지울 수 있습니다.

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
