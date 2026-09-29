# 네이버 검색 MCP 커넥터 (Cloudflare Worker)

대시보드 페이지가 네이버 블로그·카페·지역 검색을 호출하려면 claude.ai 에 연결된 커넥터가 필요합니다.
PlayMCP 에서 네이버 검색이 빠졌기 때문에, 우리 전용 커넥터를 무료로 하나 올립니다. 15분이면 됩니다.

## 1. 네이버 검색 API 키 (무료)

https://developers.naver.com → 로그인 → Application → 애플리케이션 등록
- 애플리케이션 이름: 아무거나
- 사용 API: **검색** 체크
- 환경: WEB 설정 → 서비스 URL 에 `https://example.com` 아무거나
- 등록 후 **Client ID**, **Client Secret** 복사

## 2. Cloudflare Worker 만들기 (무료, 명령어 없이 웹에서)

1. https://dash.cloudflare.com 가입/로그인
2. 왼쪽 **Workers & Pages** → **Create** → **Create Worker** → 이름 `naver-search-mcp` → **Deploy**
3. **Edit code** 를 눌러 편집기를 열고, 기본 코드를 모두 지운 뒤 이 폴더의 `worker.js` 내용을 붙여 넣고 **Deploy**
4. Worker 의 **Settings → Variables and Secrets** 에서 **Secret** 세 개 추가
   | 이름 | 값 |
   |---|---|
   | `NAVER_CLIENT_ID` | 1번에서 받은 Client ID |
   | `NAVER_CLIENT_SECRET` | 1번에서 받은 Client Secret |
   | `ACCESS_TOKEN` | 아무 긴 문자열 (예: 비밀번호 생성기로 32자). URL 에 들어가는 열쇠 |
5. Worker 주소 확인: `https://naver-search-mcp.<계정이름>.workers.dev`
   브라우저에서 열어 `naver-search mcp ok` 가 나오면 정상

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

- 네이버 검색 API 는 하루 25,000회 무료. 지점 하나 실행에 최대 9회.
- ACCESS_TOKEN 이 들어간 URL 이 외부에 새면 남이 우리 API 한도를 쓸 수 있으니 URL 은 팀 안에서만.
- 명령어로 배포하려면 `npm i -g wrangler && wrangler login && wrangler deploy` 후 `wrangler secret put` 으로 시크릿 3개.
