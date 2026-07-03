# 행정구역 경계 JSON

`pyramid.html` 지도에서 먼저 읽는 로컬 경계 GeoJSON입니다.

- `sido_20251231_light.geojson`: 시도 경계, 17개
- `sgg_20251231_light.geojson`: 시군구 경계, 252개
- `emd_20251231_light.geojson`: 법정동/읍면동 단위 경계, 3,557개
- `manifest.json`: 기준일, 출처, 파일별 개수 요약

출처는 `admdongkor` 2025-12-31 기준 simplified 경계입니다. 파일이 없거나 로드에 실패하면 앱은 기존 외부 경계 데이터로 한 번 더 시도합니다.
