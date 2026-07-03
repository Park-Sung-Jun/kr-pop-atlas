# 회사 PC 작업 인수 문서

## 현재 작업본

- 저장소: `Park-Sung-Jun/kr-pop-atlas`
- 브랜치: `codex/pop-pyramid-version`
- 최신 커밋: 작업 폴더에서 `git log --oneline -1`로 확인
- PR: https://github.com/Park-Sung-Jun/kr-pop-atlas/pull/1
- 새 버전 링크: https://krpopatlas-pop-pyramid.vercel.app

## 포함된 주요 변경

- 기존 `kr-pop-atlas`에 `pyramid.html` 통합
- 아틀라스 첫 화면에서 읍면동 피라미드 탐색기로 이동하는 링크 추가
- 지도 상단 선택박스 모바일 줄바꿈 개선
- 사람 확인 게이트, robots/noai 메타, 복사/우클릭 억제 추가
- 장기 인구 추세 패널 추가
- 장기 추세 아래에 1925~2070 전체 연도 표 추가
- KOSIS 공식 API 우선 호출용 Vercel 함수 `api/kosis-trend.js` 추가
- 지도용 행정구역 경계 JSON 로컬 포함(`data/boundaries`)

## 공유 폴더 구성

공유 드라이브에는 다음 형태로 복사합니다.

```text
kr-pop-atlas_company_pc_YYYYMMDD_HHMMSS/
  kr-pop-atlas/
  pop_pyramid_reference/
  git-bundles/
  HANDOFF_COMPANY_PC.md
```

네트워크 드라이브에서 폴더 단위 복사가 느리거나 멈추면, 같은 내용을 담은 ZIP 패키지로 전달합니다. 회사 PC에서는 ZIP을 로컬 폴더에 풀고 `kr-pop-atlas` 폴더에서 작업을 시작하면 됩니다.

- `kr-pop-atlas/`: 회사 PC에서 바로 열 작업 폴더입니다.
- `pop_pyramid_reference/`: 기존 단독 피라미드 탐색기 참고본입니다.
- `git-bundles/`: Git 이력을 단일 파일로 담은 백업입니다.

## 회사 PC에서 실행

1. 공유 폴더의 `kr-pop-atlas` 폴더를 회사 PC 로컬 작업 폴더로 복사합니다.
2. 해당 폴더에서 간단한 웹 서버를 실행합니다.

```powershell
python -m http.server 8080
```

3. 브라우저에서 엽니다.

```text
http://localhost:8080/
http://localhost:8080/pyramid.html
```

## Git으로 이어서 작업

인터넷이 되는 환경이면 GitHub에서 바로 이어받는 것을 권장합니다.

```powershell
git clone https://github.com/Park-Sung-Jun/kr-pop-atlas.git
cd kr-pop-atlas
git checkout codex/pop-pyramid-version
```

공유 폴더의 bundle 파일만으로 복원할 수도 있습니다.

```powershell
git clone git-bundles/kr-pop-atlas_codex-pop-pyramid-version.bundle kr-pop-atlas
cd kr-pop-atlas
git checkout codex/pop-pyramid-version
```

## 데이터 파일

- `data/atlas.json`: 아틀라스용 시도/시군구 전망 데이터
- `data/atlas.js`: `file://` 폴백 데이터
- `data/pop_202512.json`: 피라미드 탐색기용 시도/시군구/읍면동 성·연령 데이터
- `data/boundaries/sido_20251231_light.geojson`: 시도 경계 JSON
- `data/boundaries/sgg_20251231_light.geojson`: 시군구 경계 JSON
- `data/boundaries/emd_20251231_light.geojson`: 법정동/읍면동 단위 경계 JSON
- `data/boundaries/manifest.json`: 경계 기준일·출처·개수 요약
- `인구1925-2070.csv`: 장기 인구 추세 로컬 폴백 데이터

## KOSIS API 설정

장기 추세는 다음 순서로 데이터를 사용합니다.

1. `data/trend_kosis.json`
2. `api/kosis-trend.js`를 통한 KOSIS OpenAPI
3. `인구1925-2070.csv`

Vercel에서 KOSIS OpenAPI를 우선 사용하려면 환경 변수를 설정합니다.

```text
KOSIS_API_KEY=발급키
KOSIS_TREND_USER_STATS_ID=KOSIS에서 만든 사용자 통계 ID
```

키는 코드나 Git에 넣지 않습니다.

## CAPTCHA 설정

선택 사항입니다. 배포 환경에 아래 값을 넣으면 사람 확인 위젯을 사용합니다.

```text
CAPTCHA_PROVIDER=turnstile 또는 recaptcha
CAPTCHA_SITE_KEY=공개 사이트 키
CAPTCHA_VERIFY_ENDPOINT=서버 검증 주소(선택)
```

## 주의

- `.vercel/`, `runtime-env.json`, `kosis-env.json`은 공유/커밋 대상에서 제외합니다.
- 실제 KOSIS API 키와 CAPTCHA 비밀 키는 회사 PC 또는 배포 환경 변수에만 둡니다.
- 현재 Vercel 프로젝트는 보호 설정이 있어 일부 preview URL은 Vercel 로그인 화면이 먼저 보일 수 있습니다.
