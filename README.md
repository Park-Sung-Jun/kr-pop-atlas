# 대한민국 인구전망 아틀라스

전국 17개 시도 · 229개 시군구의 **2031년 인구 전망**과 **소멸위험**을
지도 · 카토그램 · 연도 시뮬레이션 · 성별연령 피라미드로 탐색하는 단일 정적 사이트입니다.

- 전국 뷰(시도 단위) → 시도 클릭 → 시군구 뷰로 드릴다운
- 탭: 개요(팬차트) / 지도·시뮬레이션(연도 재생) / 비교(막대) / 전망표(정렬) / 하이라이트
- 상세 카드: 인구 흐름 스파크라인 + 피라미드(지역 전체 대조) + 연령구조 유사 지역 TOP3(코사인 유사도)
- 함께 보기: [인구피라미드 탐색기](https://pop-pyramid.vercel.app) — 읍면동 단위 피라미드·대조군 비교 (같은 저자)

## 실행 (로컬 미리보기)

빌드된 `data/atlas.json`이 있으면 그대로 열립니다.

```bash
cd kr_pop_atlas
python -m http.server 8080
# http://localhost:8080/
```

`index.html`을 파일로 직접 열어도 `data/atlas.js` 폴백으로 동작합니다.

## 데이터 빌드 (연 1회 갱신)

KOSIS OpenAPI 키가 필요합니다 (발급: https://kosis.kr/openapi → 마이페이지 → 활용신청).
키는 빌드 시에만 쓰이며, 배포 사이트는 미리 생성된 `data/*.json`만 사용합니다.
**`.env`는 절대 커밋하지 않습니다**(`.gitignore` 포함).

```bash
# .env 파일에 KOSIS_API_KEY=... 를 두거나(자동 탐색), 직접 지정
python build_data.py
python build_data.py --key 발급키 --end 2025
```

표준 라이브러리만 사용합니다(별도 설치 불필요). 산출물:

- `data/atlas.json` — `{meta, national, sido:[...]}` 단일 컴팩트 JSON (~1.2MB)
- `data/atlas.js` — 동일 데이터의 `window.ATLAS` 래퍼 (file:// 폴백용)
- `data/decline.json` — `{meta, designation, fund, policy_playbook, budget}` 감소지역·기금·재정 결합 JSON (~165KB, 아래 절차로 생성)
- `data/finance.json` — `{meta, by_code}` 시군구별 분야별 세출예산(fld)·재정자립도 시계열(fi)·교부세 인센티브(inc) (~250KB, 지방재정365 OpenAPI)

### 감소지역·기금·재정 데이터 빌드 (data/decline.json)

`atlas.json`이 먼저 있어야 하며(코드 체계의 정본), 아래 순서대로 실행합니다.

```bash
# 1) 인구감소지역 지정·지방소멸대응기금·정책 플레이북 → data/decline.json 생성
python build_decline.py              # generated=오늘 (또는: python build_decline.py 2026-07-02)

# 2) 재정자립도·재정자주도(KOSIS e-지방지표) + 기금 전국 집행률 → budget 섹션 병합 (KOSIS 키 필요)
python build_budget.py

# 3) 예산현액·결산세출·주민 1인당 세출(2023 결산) → budget.by_code 병합 (KOSIS 키 필요)
python build_budget_exec.py

# 4) 분야별 세출예산·재정자립도 시계열·교부세 인센티브 → data/finance.json 생성
#    (지방재정365 lofin365 자체 인증키 필요 — LOFIN365_API_KEY, data.go.kr 키와 별개)
python build_finance.py
```

원칙: **확인된 수치·명단만 반영**합니다. 미확인 개별 배분액·등급은 `null`,
출처·연도·URL은 `meta.sources`에 병기하며, 임의 숫자를 생성하지 않습니다.
제주시·서귀포시(행정시, 자치단체 아님) 등 미공표 지역은 예산 금액을 `null`로 명시합니다.

### 데이터 출처·산출 방법

- **KOSIS 국가통계포털 OpenAPI** — 행정안전부 「주민등록인구현황」
  - 시군구별 연도 시계열: `DT_1B040A3` (2015~최신, 전국 1회 호출)
  - 성/연령(5세)별: `DT_1B04005N` (시도별 objL1 배치 17회 — 40,000건 응답 한도 회피)
- 전망 산식(추세 기반, 시군구별 산출 후 상위 지역은 합산):
  - **B(중심)** = 최근 5년 CAGR 연장 · **A(가속)** = 최근 3년 CAGR · **C(완화)** = 5년 CAGR×0.6
- 소멸위험지수 = (20~39세 여성) ÷ (65세 이상) — 이상호(한국고용정보원) 기준
- 행정구역 개편은 코드 승계로 시계열을 연결(강원 42→51, 전북 45→52, 군위군 47720→27720,
  인천 미추홀구 28170→28177). 시 산하 일반구·출장소는 모(母)시로 통합. 값이 없으면 "자료 없음"으로 표기.
- 경계: 전국 시군구 GeoJSON(좌표 4자리 반올림, 시도별 분할 수록)
- **행정안전부 인구감소지역 지정** — 최초지정(2021.10) 89곳 명단(군위군 2023 대구 편입 반영) + 관심지역 18곳(2차출처 재인용, 확신도 중간으로 명시)
- **행정안전부 지방소멸대응기금** — 연 1조 원(2022~2031), 배분기준 고시(제2024-6호)·연도별 배분현황·집행률(KDI 경제정보센터·나라살림연구소 분석 병기)
- **지방재정 통계(지방재정365 계열, KOSIS OpenAPI 경유)** — 재정자립도 `DT_1YL20921`·재정자주도 `DT_1YL20891`(e-지방지표, 2022~2025), 세입세출 예산현액·결산세출 `DT_110001_A011`(행정안전부 지방재정, 2023 결산). 시군구별 매칭은 시도명→시군명 이름매칭, 미공표 지역은 `null`.

## 배포 — GitHub 코드 정본 + Vercel 운영

- **운영 URL: https://kr-pop-atlas.vercel.app/** — 로그인 없이 공개되는 유일한 정본 URL입니다.
- 코드 정본은 이 저장소의 `main` 브랜치입니다. 변경은 GitHub에 먼저 반영하고 깨끗한 `main`에서만 Production을 배포합니다.
- 자매 사이트는 https://pop-pyramid.vercel.app/ 입니다.
- 자동 배포가 없거나 재배포가 필요할 때만 아래 명령을 사용합니다.

```bash
vercel deploy --prod --yes        # 깨끗한 main → Production
```

- `vercel.json`은 `framework: null` 순수 정적 서빙 + `cleanUrls`. 정적 파일(`index.html`, `data/`)만 있으면 되므로 빌드 파이프라인이 없다.
- 배포 후에는 최신 Production 하나와 운영 URL만 유지하고 Preview·자동 alias·이전 배포를 제거합니다.

### 도메인 등록 사전 체크 (URL 바인딩 외부 서비스)

- **이 사이트(kr-pop-atlas)는 URL 등록이 필요한 외부 서비스를 쓰지 않는다.** 지도·카토그램은 모두 인라인 SVG(GeoJSON 렌더), 데이터는 로컬 `data/*.json`뿐이라 카카오 API·캡차·`tms-ai-lab.com` 어느 것도 사용하지 않는다. 배포 URL을 바꿔도 사전 등록 없이 그대로 동작한다.
- 참고: 자매 프로젝트 **pop-pyramid**는 Cloudflare Turnstile(호스트 바인딩 캡차)을 **옵션으로** 지원한다. Turnstile 사이트 키를 Vercel 환경변수(`TURNSTILE_SITE_KEY`)에 넣어 캡차를 켜는 순간, 새 `*.vercel.app` 호스트를 **Cloudflare Turnstile 허용 도메인에 먼저 등록**해야 한다. 현재는 키 미설정이라 캡차 비활성(사전 등록 불필요).
