# 대한민국 인구전망 아틀라스

전국 17개 시도 · 229개 시군구의 **2031년 인구 전망**과 **소멸위험**을
지도 · 카토그램 · 연도 시뮬레이션 · 성별연령 피라미드로 탐색하는 단일 정적 사이트입니다.

- 전국 뷰(시도 단위) → 시도 클릭 → 시군구 뷰로 드릴다운
- 탭: 개요(팬차트) / 지도·시뮬레이션(연도 재생) / 비교(막대) / 전망표(정렬) / 하이라이트
- 상세 카드: 인구 흐름 스파크라인 + 피라미드(지역 전체 대조) + 연령구조 유사 지역 TOP3(코사인 유사도)
- 함께 보기: `pyramid.html` — 읍면동 단위 피라미드·대조군 비교·전국 장기 인구 추세를 같은 배포 안에서 제공

## 실행 (로컬 미리보기)

빌드된 `data/atlas.json`이 있으면 그대로 열립니다.

```bash
cd kr_pop_atlas
python -m http.server 8080
# http://localhost:8080/
# http://localhost:8080/pyramid.html
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

## GitHub Pages 배포

```bash
git init && git add -A && git commit -m "atlas"
git remote add origin https://github.com/<계정>/kr-pop-atlas.git
git push -u origin main
# GitHub → Settings → Pages → Source: main / root
```

정적 파일(`index.html`, `data/`)만 있으면 되므로 별도 빌드 파이프라인이 필요 없습니다.

## 통합 버전·보호 설정

- `index.html`: 대한민국 인구전망 아틀라스
- `pyramid.html`: 전국 시도·시군구·읍면동 인구피라미드 탐색기와 전체 제공 연도별 장기 추세 표
- `robots.txt`, `noai` 메타, 사람 확인 게이트, 복사·우클릭 억제 스크립트를 포함합니다.
- CAPTCHA를 쓰려면 배포 환경에 `CAPTCHA_PROVIDER=turnstile|recaptcha`, `CAPTCHA_SITE_KEY`, 필요 시 `CAPTCHA_VERIFY_ENDPOINT`를 설정합니다.
- 장기 인구 추세는 `api/kosis-trend.js`가 `KOSIS_API_KEY`, `KOSIS_TREND_USER_STATS_ID`를 이용해 KOSIS OpenAPI를 우선 호출하고, 실패하면 로컬 CSV로 표시합니다.
