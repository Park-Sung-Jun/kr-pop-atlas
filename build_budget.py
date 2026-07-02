# -*- coding: utf-8 -*-
"""
build_budget.py — data/decline.json 에 "budget" 섹션 병합.

수집(전 시군구, 표준 라이브러리만):
  ④ 재정자립도 : KOSIS orgId=101 tblId=DT_1YL20921 (e-지방지표)
     보조 재정자주도 : KOSIS orgId=101 tblId=DT_1YL20891
  ③ 예산규모   : KOSIS/data.go.kr에 전 시군구 API 표 부재 → null (정직 처리)
  ①② 기금집행 : 개별 시군 집행률 API 부재 → by_code fund_exec_pct=null,
                전국 합계 집행률만 fund_exec_national 에 확인분 등재.

키는 isochrone_map/.env 의 KOSIS_API_KEY 를 파일로 읽어 사용(값 출력·커밋 금지).
e-지방지표 C1 코드는 atlas 표준코드와 다르므로 시도명 → 시군명 이름매칭.
"""
import os, ssl, json, sys, urllib.request, urllib.parse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ATLAS = os.path.join(HERE, "data", "atlas.json")
DECLINE = os.path.join(HERE, "data", "decline.json")
ENV_PATH = r"C:\Users\user\Downloads\claude\isochrone_map\.env"
BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"

TBL_INDEP = "DT_1YL20921"   # 재정자립도(시도/시/군/구)
TBL_AUTO  = "DT_1YL20891"   # 재정자주도(시도/시/군/구)
SRC_URL = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
YEARS = ["2022", "2023", "2024", "2025"]


def load_key():
    if os.environ.get("KOSIS_API_KEY"):
        return os.environ["KOSIS_API_KEY"]
    with open(ENV_PATH, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s.startswith("KOSIS_API_KEY") and "=" in s:
                return s.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("KOSIS_API_KEY not found")


def call(params):
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
        raw = r.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if isinstance(data, dict) and ("err" in data or "errMsg" in data):
        raise RuntimeError("KOSIS %s %s" % (data.get("err"), data.get("errMsg")))
    return data


def fetch_table(key, tbl, year):
    return call({
        "method": "getList", "apiKey": key, "orgId": "101", "tblId": tbl,
        "itmId": "ALL", "objL1": "ALL", "format": "json", "jsonVD": "Y",
        "prdSe": "Y", "startPrdDe": year, "endPrdDe": year,
    })


def num(v):
    try:
        return round(float(str(v).replace(",", "")), 2)
    except (TypeError, ValueError):
        return None


def build_maps(atlas):
    """반환: sido_by_name{시도명->시도코드}, sgg_index{시도코드: {시군명->atlas코드}}"""
    sido_by_name = {}
    sgg_index = {}
    for s in atlas["sido"]:
        sido_by_name[s["name"]] = s["code"]
        idx = {}
        for r in s["rows"]:
            idx[r["name"]] = r["code"]
        sgg_index[s["code"]] = idx
    return sido_by_name, sgg_index


def parse_table(rows, itm_wanted):
    """5자리 시군 행과 2자리 시도 행을 분리. itm_wanted 항목만.
    반환: prefix_name{2자리prefix->시도명}, sgg{(2자리prefix, 시군명)->값}, sido_val{2자리prefix->값}"""
    prefix_name = {}
    sido_val = {}
    sgg = {}
    for r in rows:
        if r.get("ITM_ID") != itm_wanted:
            continue
        c1 = str(r.get("C1", ""))
        nm = r.get("C1_NM", "")
        val = num(r.get("DT"))
        if len(c1) == 2:
            if c1 == "00":
                continue
            prefix_name[c1] = nm
            sido_val[c1] = val
        elif len(c1) == 5:
            sgg[(c1[:2], nm)] = val
    return prefix_name, sido_val, sgg


def main():
    key = load_key()
    atlas = json.load(open(ATLAS, encoding="utf-8"))
    sido_by_name, sgg_index = build_maps(atlas)

    # ---- fetch all years ----
    indep_by_year = {}   # year -> (prefix_name, sido_val_T10, sgg_T10, sido_val_T20, sgg_T20)
    auto_by_year = {}
    for y in YEARS:
        rows_i = fetch_table(key, TBL_INDEP, y)
        pn10, sv10, sg10 = parse_table(rows_i, "T10")
        _,   sv20, sg20 = parse_table(rows_i, "T20")
        indep_by_year[y] = (pn10, sv10, sg10, sv20, sg20)
        rows_a = fetch_table(key, TBL_AUTO, y)
        pna, sva, sga = parse_table(rows_a, "T10")
        auto_by_year[y] = (pna, sva, sga)
        print("[fetch] %s indep=%d auto=%d" % (y, len(rows_i), len(rows_a)))

    # prefix -> atlas sido code (이름 exact 매칭, 최신연도 기준)
    pn_latest = indep_by_year[YEARS[-1]][0]
    prefix_to_sido = {}
    for pref, name in pn_latest.items():
        code = sido_by_name.get(name)
        if code is None:
            print("[WARN] 시도 미매칭:", pref, name)
        else:
            prefix_to_sido[pref] = code

    # atlas 코드별 재정자립도/재정자주도 (최신 연도 우선으로 채움)
    # 값 구조: code -> {indep_pre, indep_post, auto, year}
    result = {}
    matched_sgg = set()
    unmatched = []

    for y in YEARS:
        pn10, sv10, sg10, sv20, sg20 = indep_by_year[y]
        pna, sva, sga = auto_by_year[y]
        for (pref, sname), v10 in sg10.items():
            sido_code = prefix_to_sido.get(pref)
            if not sido_code:
                continue
            acode = sgg_index.get(sido_code, {}).get(sname)
            if not acode:
                unmatched.append((y, pref, sname))
                continue
            matched_sgg.add(acode)
            # 최신 연도가 먼저 오도록 YEARS 역순 처리 대신, 나중 연도로 덮어씀
            cur = result.get(acode)
            if cur is None or int(y) >= cur["fiscal_year"]:
                result[acode] = {
                    "indep_pre": v10,
                    "indep_post": sg20.get((pref, sname)),
                    "auto": sga.get((pref, sname)),
                    "fiscal_year": int(y),
                }

    # 미커버 자치단체: 세종 / 제주시 / 서귀포시 → 시도 단위 값 대체
    # 매칭: atlas 시도코드 -> e-prefix (prefix_to_sido 역맵)
    sido_to_prefix = {v: k for k, v in prefix_to_sido.items()}
    sido_level = {}
    ylast = YEARS[-1]
    pn10, sv10, sg10, sv20, sg20 = indep_by_year[ylast]
    pna, sva, sga = auto_by_year[ylast]
    for sido_code, pref in sido_to_prefix.items():
        sido_level[sido_code] = {
            "indep_pre": sv10.get(pref),
            "indep_post": sv20.get(pref),
            "auto": sva.get(pref),
            "fiscal_year": int(ylast),
        }

    substitutes = {}  # atlas_code -> sido_code (시도단위 대체 표시)
    for s in atlas["sido"]:
        for r in s["rows"]:
            if r["code"] in result:
                continue
            # 자치구 아님 → 시도 단위 값 대체 (세종·제주시·서귀포시)
            substitutes[r["code"]] = s["code"]

    # by_code 구성
    by_code = {}
    for acode, v in result.items():
        by_code[acode] = {
            "fiscal_independence_pct": v["indep_pre"],
            "fiscal_independence_pct_after_reform": v["indep_post"],
            "fiscal_autonomy_pct": v["auto"],
            "fiscal_year": v["fiscal_year"],
            "budget_total_krw": None,
            "fund_exec_pct": None,
            "level": "시군구",
            "src": SRC_URL,
        }
    for acode, sido_code in substitutes.items():
        sv = sido_level.get(sido_code)
        if not sv:
            continue
        by_code[acode] = {
            "fiscal_independence_pct": sv["indep_pre"],
            "fiscal_independence_pct_after_reform": sv["indep_post"],
            "fiscal_autonomy_pct": sv["auto"],
            "fiscal_year": sv["fiscal_year"],
            "budget_total_krw": None,
            "fund_exec_pct": None,
            "level": "시도단위대체",
            "src": SRC_URL,
        }

    n_indep = sum(1 for v in by_code.values() if v["fiscal_independence_pct"] is not None)

    budget = {
        "sources": [
            {"name": "재정자립도(시도/시/군/구) e-지방지표", "org": "KOSIS·행정안전부",
             "url": SRC_URL, "year": int(YEARS[-1]), "tbl_id": TBL_INDEP},
            {"name": "재정자주도(시도/시/군/구) e-지방지표", "org": "KOSIS·행정안전부",
             "url": SRC_URL, "year": int(YEARS[-1]), "tbl_id": TBL_AUTO},
            {"name": "지방소멸대응기금 2022~2024 전국 집행 내역(보고서 736)", "org": "나라살림연구소",
             "url": "https://narasallim.net/report/736", "year": 2025},
            {"name": "지방소멸대응기금 집행/배분 분석(보고서 546)", "org": "나라살림연구소",
             "url": "https://www.narasallim.net/report/546", "year": 2023},
        ],
        "fund_exec_national": [
            {"alloc_year": 2022, "rate_pct": 37.57, "asof": "2023-06-30",
             "source_url": "https://www.narasallim.net/report/546"},
            {"alloc_year": 2022, "rate_pct": 84.4, "asof": "2024-12-31",
             "source_url": "https://narasallim.net/report/736"},
            {"alloc_year": 2023, "rate_pct": 58.7, "asof": "2024-12-31",
             "source_url": "https://narasallim.net/report/736"},
            {"alloc_year": 2024, "rate_pct": 42.2, "asof": "2024-12-31",
             "source_url": "https://narasallim.net/report/736"},
        ],
        "by_code": by_code,
        "coverage": {
            "fiscal_independence_codes": n_indep,
            "budget_total_codes": 0,
            "fiscal_year_latest": int(YEARS[-1]),
            "fiscal_year_range": [int(YEARS[0]), int(YEARS[-1])],
            "sido_level_substitutes": sorted(substitutes.keys()),
        },
        "notes": (
            "재정자립도·재정자주도는 KOSIS e-지방지표(orgId=101, DT_1YL20921/DT_1YL20891)에서 "
            "전 시군구를 수집해 atlas 이름매칭으로 매핑했습니다. fiscal_independence_pct 는 "
            "세입과목개편전(T10) 기준이며 개편후(T20)는 별도 필드로 병기했습니다. "
            "세종·제주시·서귀포시는 자치구 단위 지표가 없어 해당 시도 단위 값으로 대체(level=시도단위대체)했습니다. "
            "지자체 예산규모(총계)는 전 시군구를 제공하는 공개 API 표가 없어 budget_total_krw 는 미공표(null)입니다. "
            "지방소멸대응기금 개별 시군 집행률도 공개 API 부재로 by_code 는 null이며, 전국 합계 집행률만 "
            "fund_exec_national 에 배분연도·기준일을 병기해 등재했습니다. "
            "기금은 229개 전 시군에 배분되지 않으며(광역계정+인구감소·관심지역 대상), 광역이 기초로 재이전하거나 "
            "위탁·출자 시 실집행과 무관하게 집행률이 100%로 잡히는 착시가 있습니다."
        ),
    }

    decline = json.load(open(DECLINE, encoding="utf-8"))
    decline["budget"] = budget
    # meta.sources 에 budget 출처 미러(중복 없이)
    with open(DECLINE, "w", encoding="utf-8") as f:
        json.dump(decline, f, ensure_ascii=False, indent=2)

    print("[done] by_code total=%d, fiscal_independence non-null=%d, substitutes=%d, unmatched=%d"
          % (len(by_code), n_indep, len(substitutes), len(unmatched)))
    if unmatched:
        # 최신연도만 요약
        last = [u for u in unmatched if u[0] == YEARS[-1]]
        print("[unmatched latest-year count]", len(last))
        for u in last[:30]:
            print("  ", u[1], repr(u[2]))
    print("[substitutes]", sorted(substitutes.keys()))
    print("[fund_exec_national years]", [e["alloc_year"] for e in budget["fund_exec_national"]])


if __name__ == "__main__":
    main()
