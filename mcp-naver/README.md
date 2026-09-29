# 네이버 검색 MCP 커넥터 (Cloudflare Worker)

대시보드 페이지가 네이버 블로그·카페·지역 검색을 호출하려면 claude.ai 에 연결된 커넥터가 필요합니다.
PlayMCP 에서 네이버 검색이 빠졌기 때문에, 우리 전용 커넥터를 무료로 하나 올립니다. 15분이면 됩니다.

## 1. 네이버 검색 API 키 (NAVER API HUB)

네이버 개발자센터(developers.naver.com)는 2026-07-31 부로 검색 API 신규 발급을 끝냈습니다 (사용 API 목록에 "검색" 이 없는 이유).
신규 키는 **NAVER API HUB** (네이버클라우드플랫폼) 에서만 받습니다. 종량제이지만 검색 API 는 현재 무료 구간이 있고 월 775,000회 한도입니다.

1. https://www.ncloud.com 가입 → 콘솔 로그인 (결제수단 등록을 요구할 수 있음)
2. 콘솔에서 **Services → Application Services → NAVER API HUB** → 이용 신청
3. **Application(앱) 등록** → 이름 아무거나 → 사용할 API 에서 **검색: 블로그, 카페글, 지역** 체크 → 등록
4. 등록된 앱의 **인증 정보** 에서 **Client ID** 와 **Client Secret** 복사
   (Worker 시크릿 이름은 `NCP_API_KEY_ID`, `NCP_API_KEY`)

콘솔 메뉴 이름은 바뀔 수 있습니다. "NAVER API HUB" 상품 페이지: https://www.ncloud.com/product/applicationService/naverApiHub

> 예전에 개발자센터에서 받아 둔 검색 API 키가 있으면 그것도 됩니다 (`NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`). 2027-06-30 에 중단되니 그 전에 API HUB 로 옮기세요.

## 2. Cloudflare Worker 만들기 (무료, 명령어 없이 웹에서)

1. https://dash.cloudflare.com 가입/로그인
2. 왼쪽 **Workers & Pages** → **Create** → **Create Worker** → 이름 `naver-search-mcp` → **Deploy**
3. **Edit code** 를 눌러 편집기를 열고, 기본 코드를 모두 지운 뒤 이 폴더의 `worker.js` 내용을 붙여 넣고 **Deploy**
4. Worker 의 **Settings → Variables and Secrets** 에서 **Secret** 세 개 추가
   | 이름 | 값 |
   |---|---|
   | `NCP_API_KEY_ID` | 1번에서 받은 Client ID |
   | `NCP_API_KEY` | 1번에서 받은 Client Secret |
   | `ACCESS_TOKEN` | 아무 긴 문자열 (예: 비밀번호 생성기로 32자). URL 에 들어가는 열쇠 |
5. Worker 주소 확인: `https://naver-search-mcp.<계정이름>.workers.dev`
   브라우저에서 열어 `naver-search mcp ok (api-hub)` 가 나오면 정상

## 3. claude.ai 에 커넥터로 추가

claude.ai → 설정 → **커넥터** → **커스텀 커넥터 추가**
- 이름: **`NaverSearch`** (대시보드가 이 이름으로 찾습니다. 정확히 이대로)
- URL: `https://naver-search-mcp.<계정이름>.workers.dev/mcp/<ACCESS_TOKEN>`
- 인증: 없음 (OAuth 사용 안 함)

추가되면 도구 3개(search_blog, search_cafearticle, search_local)가 보입니다.
같은 계정을 쓰는 팀원은 따로 할 게 없습니다.

## 4. 대시보드 실행

대시보드 새로고침 → 지점 선택 → 실행. 첫 실행 때 NaverSearch 커넥터 사용 허용을 묻습니다.

## 참고

- API HUB 검색 API 는 월 775,000회 한도. 지점 하나 실행에 최대 9회라 한도 걱정은 없음. 요금은 네이버클라우드 콘솔에서 확인.
- ACCESS_TOKEN 이 들어간 URL 이 외부에 새면 남이 우리 API 한도를 쓸 수 있으니 URL 은 팀 안에서만.
- 명령어로 배포하려면 `npm i -g wrangler && wrangler login && wrangler deploy` 후 `wrangler secret put` 으로 시크릿 3개.
