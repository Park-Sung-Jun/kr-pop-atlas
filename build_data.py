#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
대한민국 인구전망 아틀라스 — 데이터 빌드 (KOSIS OpenAPI, 표준 라이브러리만)
==========================================================================
kosis_gb_report/kosis_gb_sigungu_report.py(경북판, 검증 완료)의 수집·전망 로직을
전국 17개 시도 × 시군구로 일반화한 빌드 스크립트.

데이터 소스 (KOSIS 국가통계포털 OpenAPI, orgId=101):
  [A] DT_1B040A3   주민등록인구 시군구별 연도 시계열 (2015~최신, 1회 호출)
  [B] DT_1B04005N  주민등록인구 시군구/성/연령(5세)별 (시도별 objL1 배치, 17회 호출
                   — 전국 ALL은 40,000건 한도 초과라 지역코드 지정으로 회피)

산출물:
  data/atlas.json  {meta, national, sido:[...]} 단일 컴팩트 JSON (5MB 이하 목표)
  data/atlas.js    window.ATLAS = {...} — file:// 폴백용 동일 데이터

사용법:
  python build_data.py            # KOSIS_API_KEY 자동 탐색(.env)
  python build_data.py --key 발급키
키는 빌드 시에만 사용. .env는 커밋 금지(.gitignore).
"""
import argparse
import json
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_PARAM = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
START_YEAR = 2015
TARGET_YEAR = 2031

HERE = os.path.dirname(os.path.abspath(__file__))
GEOJSON_CANDS = [
    os.path.join(HERE, "sigungu.geojson"),
    os.path.join(HERE, "..", "isochrone_map", "data", "sigungu.geojson"),
]

# 시도 표시명 (2자리 행정구역코드 → 짧은 이름)
SIDO_SHORT = {
    "11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "광주",
    "30": "대전", "31": "울산", "36": "세종", "41": "경기", "51": "강원",
    "43": "충북", "44": "충남", "52": "전북", "46": "전남", "47": "경북",
    "48": "경남", "50": "제주",
}
# 조사 기간(2015~) 내 행정구역 코드 승계 매핑 — 같은 지역의 시계열을 잇는다.
#  강원특별자치도 42→51(2023), 전북특별자치도 45→52(2024): 접미 3자리 동일 승계
#  군위군 47720→27720(2023.7 대구 편입), 인천 남구 28170→미추홀구 28177(2018.7)
REMAP_PREFIX = {"42": "51", "45": "52"}
REMAP_CODE = {"47720": "27720", "28170": "28177"}


# ──────────────────────────────────────────────
# KOSIS API 호출부 (경북판 그대로)
# ──────────────────────────────────────────────
class KosisError(RuntimeError):
    def __init__(self, code, msg):
        super().__init__(f"KOSIS 오류 [{code}] {msg}")
        self.code = str(code)


def _call(url, params):
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(url + "?" + query,
                                 headers={"User-Agent": "Mozilla/5.0"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        raw = r.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if isinstance(data, dict) and ("err" in data or "errMsg" in data):
        raise KosisError(data.get("err", "?"), data.get("errMsg", raw[:200]))
    return data


def get_stat(key, org_id, tbl_id, prd_se, start, end, itm_id="ALL", obj1="ALL"):
    """분류 레벨(objL2~)이 부족하면(오류 20/21) 자동 확장 재시도.
    40,000건 한도(오류 31)는 objL1에 지역코드를 '+'로 지정해 회피한다."""
    params = {
        "method": "getList", "apiKey": key, "orgId": org_id, "tblId": tbl_id,
        "itmId": itm_id, "objL1": obj1,
        "format": "json", "jsonVD": "Y",
        "prdSe": prd_se, "startPrdDe": start, "endPrdDe": end,
    }
    for lvl in range(2, 9):
        try:
            return _call(BASE_PARAM, params)
        except KosisError as e:
            if e.code in ("20", "21") and lvl <= 8:
                params[f"objL{lvl}"] = "ALL"
                continue
            if e.code == "31":
                raise KosisError("31", f"{tbl_id}: 40,000건 한도 초과 — objL1 지역코드 지정 필요") from e
            raise
    raise KosisError("-", "분류 레벨 확장(objL2~8) 후에도 조회 실패")


# ──────────────────────────────────────────────
# 파싱 유틸
# ──────────────────────────────────────────────
def canon(code):
    """행정구역 코드 승계 정규화 (옛 코드 → 현행 코드)."""
    if code in REMAP_CODE:
        return REMAP_CODE[code]
    if len(code) >= 2 and code[:2] in REMAP_PREFIX:
        return REMAP_PREFIX[code[:2]] + code[2:]
    return code


def is_five(code):
    return isinstance(code, str) and len(code) == 5 and code.isdigit()


def find_sub_gu(series):
    """시 산하 일반구 집합 판정.

    후보: 끝 1~9이면서 모(母)시 코드(앞4자리+0)가 함께 존재하는 코드.
    (광진구 11215·미추홀구 28177처럼 끝자리가 0이 아니어도 모 코드가 없으면 독립 시군구.)
    단, 증평군(43745)은 영동군(43740)과 코드가 우연히 이웃일 뿐이므로,
    '자식 합계 == 부모 인구'가 성립하는 그룹만 일반구로 확정한다.
    """
    all5 = set(series)
    groups = defaultdict(list)
    for c in all5:
        if c[-1] != "0" and (c[:4] + "0") in all5:
            groups[c[:4] + "0"].append(c)
    drop = set()
    for parent, kids in groups.items():
        # 연도별로: 그 해 자료가 있는 자식들의 합 == 부모이면 그 자식들은 일반구.
        # (부천시처럼 구가 폐지 후 재설치돼 옛/새 구 코드가 섞여 있어도 안전)
        for y in series[parent]:
            kids_y = [k for k in kids if y in series[k]]
            if not kids_y:
                continue
            s = sum(series[k][y] for k in kids_y)
            if abs(s - series[parent][y]) <= max(3, series[parent][y] * 0.005):
                drop |= set(kids_y)
    return drop


def sex_of(name):
    n = (name or "")
    if "남" in n: return "M"
    if "여" in n: return "F"
    return "T"


def age_lo(label):
    if not label or any(k in label for k in ("계", "합", "전체")):
        return None
    m = re.search(r"(\d+)", label)
    return int(m.group(1)) if m else None


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


# ──────────────────────────────────────────────
# [A] 전국 시군구 인구 시계열 (1회 호출)
# ──────────────────────────────────────────────
def fetch_timeseries(key, end_year):
    print(f"[A] 주민등록인구 시계열 조회 (DT_1B040A3, {START_YEAR}~{end_year}, 전국 1회)")
    rows = get_stat(key, "101", "DT_1B040A3", "Y", str(START_YEAR), str(end_year))
    series = defaultdict(dict)   # {정규화 시군구코드: {연도: 인구}}
    names = {}
    sido_names = {}
    for r in rows:
        c1 = canon(str(r.get("C1", "")))
        if "총인구" not in (r.get("ITM_NM") or ""):
            continue
        yr, val = r.get("PRD_DE"), num(r.get("DT"))
        if not yr or val is None:
            continue
        nm = (r.get("C1_NM") or c1).strip()
        if len(c1) == 2 and c1 in SIDO_SHORT:
            sido_names[c1] = nm
            continue
        if not is_five(c1):
            continue
        if "출장소" in nm:                 # 출장소는 시 일부만 담당 — 시군구 아님
            continue
        series[c1][int(yr)] = int(val)
        names[c1] = nm
    if not series:
        raise RuntimeError("시군구 데이터가 비어 있음 — 응답 C1 코드 체계 확인 필요")
    # 시 산하 일반구(수원 장안구 41111 등)는 모시로 대표되므로 제외
    sub_gu = find_sub_gu(series)
    series = {c: ys for c, ys in series.items() if c not in sub_gu}
    # 최신연도가 없는 코드(관할 변경으로 소멸한 옛 코드)는 제외 → 전 기간 동일 구성
    global_last = max(max(ys) for ys in series.values())
    dropped = sorted(f"{names.get(c, c)}({c})" for c, ys in series.items()
                     if max(ys) < global_last)
    if dropped:
        series = {c: ys for c, ys in series.items() if max(ys) == global_last}
        print(f"    → 관할 변경으로 제외: {', '.join(dropped)}")
    incomplete = [f"{names.get(c, c)}({c}:{len(ys)}y)" for c, ys in series.items()
                  if len(ys) < len(range(START_YEAR, global_last + 1))]
    if incomplete:
        print(f"    (주의: 일부 연도 결측 {len(incomplete)}건 — {', '.join(incomplete[:5])})")
    print(f"    → 시군구 {len(series)}개 · 시도 {len(sido_names)}개 수집 "
          f"(실적 {min(min(ys) for ys in series.values())}~{global_last})")
    return series, names, sido_names, global_last


# ──────────────────────────────────────────────
# 3-시나리오 전망 (경북판 project 그대로)
# ──────────────────────────────────────────────
def project(series):
    """B(중심)=최근5년 CAGR 연장 · A(가속)=최근3년 CAGR · C(완화)=5년 CAGR×0.6"""
    out = {}
    for code, ys in series.items():
        years = sorted(ys)
        last = years[-1]
        p_last = ys[last]

        def cagr(span):
            base_y = last - span
            if span <= 0 or base_y not in ys or ys[base_y] <= 0 or p_last <= 0:
                return None
            return (p_last / ys[base_y]) ** (1 / span) - 1

        r5 = cagr(5) if last - 5 in ys else cagr(last - years[0])
        r3 = cagr(3)
        if r5 is None:
            continue
        if r3 is None:
            r3 = r5
        n = TARGET_YEAR - last
        out[code] = {
            "last_year": last, "pop_last": p_last,
            "cagr5": r5, "cagr3": r3,
            "p2031_A": round(p_last * (1 + min(r3, r5)) ** n),
            "p2031_B": round(p_last * (1 + r5) ** n),
            "p2031_C": round(p_last * (1 + r5 * 0.6) ** n),
        }
    return out


# ──────────────────────────────────────────────
# [B] 성/연령(5세)별 — 시도별 objL1 배치
# ──────────────────────────────────────────────
def fetch_pyramids_for(key, end_year, codes, label):
    """codes(시군구 목록)의 5세 남/여 피라미드. 반환 {code:{ages,m,f}}, 사용연도."""
    codeset = set(codes)
    obj1 = "+".join(sorted(codeset))
    rows, used = None, None
    for yr in range(end_year, end_year - 3, -1):        # 최신연도 자동 탐색
        try:
            rows = get_stat(key, "101", "DT_1B04005N", "Y", str(yr), str(yr), obj1=obj1)
            used = yr
            break
        except KosisError as e:
            print(f"    {label} {yr}년 조회 실패({e.code}) → 이전 연도 시도")
    if not rows:
        raise RuntimeError(f"{label}: 연령별 데이터 조회 실패")
    acc = defaultdict(lambda: defaultdict(float))       # {코드: {(sex, age): 합}}
    for r in rows:
        c1 = canon(str(r.get("C1", "")))
        if c1 not in codeset:
            continue
        age_label = next((r.get(k) for k in ("C2_NM", "C3_NM", "C4_NM")
                          if age_lo(r.get(k)) is not None), None)
        a = age_lo(age_label)
        if a is None:
            continue
        v = num(r.get("DT"))
        if v is None:
            continue
        acc[c1][(sex_of(r.get("ITM_NM")), a)] += v
    pyr = {}
    for code, d in acc.items():
        ages = sorted({a for (s, a) in d if s in ("M", "F")})
        if ages:
            pyr[code] = {"ages": ages,
                         "m": [int(d.get(("M", a), 0)) for a in ages],
                         "f": [int(d.get(("F", a), 0)) for a in ages]}
    return pyr, used


def sum_pyramids(pyrs):
    """피라미드 목록 합산(연령계급 합집합 기준)."""
    ages = sorted({a for p in pyrs for a in p["ages"]})
    if not ages:
        return None
    def tot(sex):
        out = []
        for a in ages:
            s = 0
            for p in pyrs:
                if a in p["ages"]:
                    s += p[sex][p["ages"].index(a)]
            out.append(s)
        return out
    return {"ages": ages, "m": tot("m"), "f": tot("f")}


def age_metrics(p):
    """피라미드 → 연령구조·소멸위험지수. 자료 없으면 None들."""
    if not p:
        return {"young_pct": None, "work_pct": None, "old_pct": None, "risk_idx": None}
    mf = [(a, m + f) for a, m, f in zip(p["ages"], p["m"], p["f"])]
    total = sum(v for _, v in mf)
    if total <= 0:
        return {"young_pct": None, "work_pct": None, "old_pct": None, "risk_idx": None}
    young = sum(v for a, v in mf if a <= 14)
    work = sum(v for a, v in mf if 15 <= a <= 64)
    old = sum(v for a, v in mf if a >= 65)
    f2039 = sum(f for a, f in zip(p["ages"], p["f"]) if 20 <= a <= 39)
    return {
        "young_pct": round(young / total * 100, 1),
        "work_pct": round(work / total * 100, 1),
        "old_pct": round(old / total * 100, 1),
        "risk_idx": round(f2039 / old, 3) if old > 0 else None,
    }


# ──────────────────────────────────────────────
# 경계 GeoJSON → 시도별 추출
# ──────────────────────────────────────────────
def load_geometry(valid_codes, names):
    src = next((p for p in GEOJSON_CANDS if os.path.exists(p)), None)
    if not src:
        raise RuntimeError("sigungu.geojson 미발견: " + " / ".join(GEOJSON_CANDS))
    with open(src, encoding="utf-8") as fh:
        gj = json.load(fh)
    by_sido = defaultdict(lambda: {"features": [], "cent": {}})
    unmatched = []
    for ft in gj.get("features", []):
        pr = ft.get("properties", {})
        code = canon(str(pr.get("code") or pr.get("SIG_CD") or ""))
        if len(code) != 5:
            continue
        # 정확 일치 우선, 아니면 시 산하 일반구 → 모(母)시(앞4자리+0)로 병합
        norm = code if code in valid_codes else code[:4] + "0"
        if norm not in valid_codes:
            unmatched.append(f"{pr.get('name')}({code})")
            continue
        sd = norm[:2]
        geom = ft["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        rings = [[[round(x, 4), round(y, 4)] for x, y in poly[0]] for poly in polys]
        g = by_sido[sd]
        g["features"].append({"code": norm, "name": names.get(norm, pr.get("name", norm)),
                              "rings": rings})
        big = max(rings, key=len)
        cx = sum(p[0] for p in big) / len(big)
        cy = sum(p[1] for p in big) / len(big)
        if norm not in g["cent"] or len(big) > g["cent"][norm][2]:
            g["cent"][norm] = (round(cx, 4), round(cy, 4), len(big))
    if unmatched:
        print(f"    (경계 미매칭 {len(unmatched)}건: {', '.join(unmatched[:6])} …)")
    out = {}
    for sd, g in by_sido.items():
        xs = [p[0] for f_ in g["features"] for r in f_["rings"] for p in r]
        ys = [p[1] for f_ in g["features"] for r in f_["rings"] for p in r]
        out[sd] = {
            "geo": {"features": g["features"],
                    "bbox": [round(min(xs), 4), round(min(ys), 4),
                             round(max(xs), 4), round(max(ys), 4)]},
            "cent": {k: [v[0], v[1]] for k, v in g["cent"].items()},
        }
    n_feat = sum(len(g['geo']['features']) for g in out.values())
    print(f"[C] 경계 로드: 시도 {len(out)}개 · 피처 {n_feat}개 ({os.path.basename(src)})")
    return out


# ──────────────────────────────────────────────
# 팬차트·시뮬레이션 경로 빌더 (경북판 render_report 로직 일반화)
# ──────────────────────────────────────────────
def man(v):
    return round(v / 10000, 1)


def build_fan(tot_by_year, yrs_hist, last_y, sumA, sumB, sumC):
    n_f = TARGET_YEAR - last_y
    base = tot_by_year[last_y]

    def path(end):
        r = (end / base) ** (1 / n_f) - 1
        seq = [None] * (len(yrs_hist) - 1) + [man(base)]
        for i in range(1, n_f + 1):
            seq.append(man(base * (1 + r) ** i))
        return seq

    return {
        "years": yrs_hist + list(range(last_y + 1, TARGET_YEAR + 1)),
        "actual": [man(tot_by_year[y]) for y in yrs_hist] + [None] * n_f,
        "A": path(sumA), "B": path(sumB), "C": path(sumC),
        "endA": man(sumA), "endB": man(sumB), "endC": man(sumC),
    }


def sim_path(series_code, proj_code, yrs_hist, last_y):
    n_f = TARGET_YEAR - last_y
    pathv = [series_code.get(y) for y in yrs_hist]
    for i in range(1, n_f + 1):
        pathv.append(round(proj_code["pop_last"] * (1 + proj_code["cagr5"]) ** i))
    return pathv


def make_row(code, name, p, met):
    return {"code": code, "name": name,
            "pop_last": p["pop_last"], "cagr5": round(p["cagr5"], 5),
            "p2031_A": p["p2031_A"], "p2031_B": p["p2031_B"], "p2031_C": p["p2031_C"],
            "young_pct": met["young_pct"], "work_pct": met["work_pct"],
            "old_pct": met["old_pct"], "risk_idx": met["risk_idx"]}


# ──────────────────────────────────────────────
# 키 로드 (경북판 _load_dotenv_key + isochrone_map 명시 후보)
# ──────────────────────────────────────────────
def _load_dotenv_key(explicit=None):
    import glob
    if os.environ.get("KOSIS_API_KEY"):
        return os.environ["KOSIS_API_KEY"]
    cands = []
    if explicit:
        cands.append(explicit)
    cands.append(os.path.join(HERE, "..", "isochrone_map", ".env"))
    roots, d = [HERE, os.getcwd()], os.getcwd()
    for _ in range(4):
        d = os.path.dirname(d)
        roots.append(d)
    seen = set()
    for r in roots:
        if not r or r in seen:
            continue
        seen.add(r)
        cands.append(os.path.join(r, ".env"))
        cands.extend(sorted(glob.glob(os.path.join(r, "*", ".env"))))
    for p in cands:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("KOSIS_API_KEY") and "=" in s:
                        v = s.split("=", 1)[1].strip().strip('"').strip("'")
                        if v:
                            print(f"    KOSIS 키 로드: {p}")
                            return v
        except Exception:
            pass
    return ""


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default="")
    ap.add_argument("--env", default="", help=".env 파일 경로 (미지정 시 자동 탐색)")
    ap.add_argument("--end", type=int, default=date.today().year - 1)
    args = ap.parse_args()
    key = args.key or _load_dotenv_key(args.env or None)
    if not key:
        sys.exit("KOSIS API 키가 필요합니다 (--key / --env / KOSIS_API_KEY).")

    # [A] 전국 시계열 → 전망
    series, names, sido_names, last_y = fetch_timeseries(key, args.end)
    proj = project(series)
    yrs_hist = sorted({y for s in series.values() for y in s if y <= last_y})

    # 시도별 자식 코드 그룹
    children = defaultdict(list)
    for c in proj:
        children[c[:2]].append(c)
    sd_codes = sorted(c for c in children if c in SIDO_SHORT)
    print(f"    → 시도 {len(sd_codes)}개 그룹: " +
          ", ".join(f"{SIDO_SHORT[s]}({len(children[s])})" for s in sd_codes))

    # [B] 시도별 피라미드 (17회 배치 호출)
    print(f"[B] 성/연령(5세)별 조회 (DT_1B04005N, 시도별 objL1 배치 {len(sd_codes)}회)")
    pyr_all = {}
    pyr_year = None
    for sd in sd_codes:
        p, used = fetch_pyramids_for(key, last_y, children[sd], SIDO_SHORT[sd])
        pyr_all.update(p)
        pyr_year = used if pyr_year is None else min(pyr_year, used)
        print(f"    {SIDO_SHORT[sd]}: {len(p)}/{len(children[sd])}개 · {used}년")

    # [C] 경계
    geo_by_sido = load_geometry(set(proj.keys()), names)

    # ── 시도별 데이터셋 조립 ──
    sido_out = []
    nat_rows, nat_sim, nat_cent, nat_pyr = [], {}, {}, {}
    nat_tot = defaultdict(int)
    excluded_note = ("행정구역 개편 지역은 코드 승계로 시계열을 이었으며(강원·전북 도명 변경, "
                     "군위군 대구 편입, 인천 미추홀구), 승계가 불가능한 옛 코드는 제외했습니다.")
    for sd in sd_codes:
        codes = sorted(children[sd])
        rows, sim_by = [], {}
        tot = defaultdict(int)
        for c in codes:
            met = age_metrics(pyr_all.get(c))
            rows.append(make_row(c, names.get(c, c), proj[c], met))
            sim_by[c] = sim_path(series[c], proj[c], yrs_hist, last_y)
            for y in yrs_hist:
                tot[y] += series[c].get(y, 0)
        rows.sort(key=lambda r: -r["pop_last"])
        sumA = sum(proj[c]["p2031_A"] for c in codes)
        sumB = sum(proj[c]["p2031_B"] for c in codes)
        sumC = sum(proj[c]["p2031_C"] for c in codes)
        fan = build_fan(tot, yrs_hist, last_y, sumA, sumB, sumC)
        g = geo_by_sido.get(sd, {"geo": None, "cent": {}})
        sd_pyr = sum_pyramids([pyr_all[c] for c in codes if c in pyr_all])
        sido_out.append({
            "code": sd, "name": sido_names.get(sd, SIDO_SHORT[sd]),
            "short": SIDO_SHORT[sd],
            "rows": rows, "fan": fan,
            "sim": {"years": fan["years"], "actualN": len(yrs_hist), "byCode": sim_by},
            "geo": g["geo"], "cent": g["cent"],
            "pyr": {c: pyr_all[c] for c in codes if c in pyr_all},
            "pyrAll": sd_pyr,
        })
        # 전국 뷰용 시도 대표값
        sd_series = dict(tot)
        sd_proj = project({sd: sd_series})[sd]
        sd_proj["p2031_A"], sd_proj["p2031_B"], sd_proj["p2031_C"] = sumA, sumB, sumC
        nat_rows.append(make_row(sd, sido_names.get(sd, SIDO_SHORT[sd]), sd_proj,
                                 age_metrics(sd_pyr)))
        sim_sd = [sum(sim_by[c][i] or 0 for c in codes) for i in range(len(fan["years"]))]
        nat_sim[sd] = sim_sd
        if g["cent"]:
            nat_cent[sd] = [round(sum(v[0] for v in g["cent"].values()) / len(g["cent"]), 4),
                            round(sum(v[1] for v in g["cent"].values()) / len(g["cent"]), 4)]
        if sd_pyr:
            nat_pyr[sd] = sd_pyr
        for y in yrs_hist:
            nat_tot[y] += tot[y]

    nat_rows.sort(key=lambda r: -r["pop_last"])
    nat_fan = build_fan(nat_tot, yrs_hist, last_y,
                        sum(r["p2031_A"] for r in nat_rows),
                        sum(r["p2031_B"] for r in nat_rows),
                        sum(r["p2031_C"] for r in nat_rows))
    national = {
        "name": "전국", "rows": nat_rows, "fan": nat_fan,
        "sim": {"years": nat_fan["years"], "actualN": len(yrs_hist), "byCode": nat_sim},
        "cent": nat_cent, "pyr": nat_pyr, "pyrAll": sum_pyramids(list(nat_pyr.values())),
    }

    atlas = {
        "meta": {
            "generated": date.today().isoformat(),
            "start": yrs_hist[0], "last": last_y, "target": TARGET_YEAR,
            "pyrYear": pyr_year,
            "nSido": len(sido_out),
            "nSgg": sum(len(s["rows"]) for s in sido_out),
            "note": excluded_note,
            "source": "KOSIS 국가통계포털 OpenAPI — 행정안전부 주민등록인구현황 "
                      "(시군구별 DT_1B040A3 · 성/연령 5세별 DT_1B04005N)",
        },
        "national": national,
        "sido": sido_out,
    }

    out_dir = os.path.join(HERE, "data")
    os.makedirs(out_dir, exist_ok=True)
    payload = json.dumps(atlas, ensure_ascii=False, separators=(",", ":"))
    p_json = os.path.join(out_dir, "atlas.json")
    with open(p_json, "w", encoding="utf-8") as f:
        f.write(payload)
    p_js = os.path.join(out_dir, "atlas.js")
    with open(p_js, "w", encoding="utf-8") as f:
        f.write("window.ATLAS=" + payload + ";")

    mb = os.path.getsize(p_json) / 1e6
    print("\n완료:")
    print(f"  data/atlas.json  {mb:.2f} MB")
    print(f"  시도 {atlas['meta']['nSido']}개 · 시군구 {atlas['meta']['nSgg']}개 · "
          f"실적 {yrs_hist[0]}~{last_y} · 전망 {TARGET_YEAR} · 피라미드 {pyr_year}년")
    if mb > 5:
        print("  경고: 5MB 초과 — 좌표 정밀도/피처 수 점검 필요")


if __name__ == "__main__":
    main()
