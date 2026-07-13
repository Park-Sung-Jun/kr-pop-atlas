# -*- coding: utf-8 -*-
"""
build_budget_exec.py — data/decline.json 의 budget.by_code 에
지자체 예산규모·실제지출(결산세출)·주민 1인당 세출을 병합.

출처: KOSIS orgId=110 tblId=DT_110001_A011 (세입세출, 행정안전부 지방재정)
  ITM T1=예산현액(최종) · T3=결산세출(B). C2='계' 회계. 단위 백만원. 최신=2023.
  C1 은 A00x 순번코드 → 시도 블록 순서로 그룹핑 후 시군명 이름매칭(재정자립도와 동일 원리).
  세종시=단일단체(정확). 제주시·서귀포시=행정시(단체 미제공) → 예산액 null(도 전체를 행정시에 배분 금지).
키는 isochrone_map/.env 의 KOSIS_API_KEY (값 출력·커밋 금지).
"""
import os, json, sys
from kosis_budget_utils import load_key, call, num

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ATLAS = os.path.join(HERE, "data", "atlas.json")
DECLINE = os.path.join(HERE, "data", "decline.json")
BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
ORG, TBL, YEAR = "110", "DT_110001_A011", "2023"
SRC_URL = BASE

SIDO_ALIAS = {"전라북도": "전북특별자치도", "강원도": "강원특별자치도",
              "전라남도": "전라남도", "충청북도": "충청북도"}
# 행정시(자치단체 아님) — 예산 금액 대체 금지
NO_AMOUNT_SUB = {"50110", "50130"}  # 제주시·서귀포시


def main():
    key = load_key()
    atlas = json.load(open(ATLAS, encoding="utf-8"))

    sido_by_name, sgg_index, pop = {}, {}, {}
    for s in atlas["sido"]:
        sido_by_name[s["name"]] = s["code"]
        sgg_index[s["code"]] = {r["name"]: r["code"] for r in s["rows"]}
        for r in s["rows"]:
            pop[r["code"]] = r.get("pop_last")

    def atlas_sido(name):
        return sido_by_name.get(name) or sido_by_name.get(SIDO_ALIAS.get(name, ""))

    rows = call({
        "method": "getList", "apiKey": key, "orgId": ORG, "tblId": TBL,
        "itmId": "ALL", "objL1": "ALL", "objL2": "ALL", "format": "json",
        "jsonVD": "Y", "prdSe": "Y", "startPrdDe": YEAR, "endPrdDe": YEAR,
    })
    # C1 -> {name, T1, T3} (계 회계만)
    agg = {}
    for r in rows:
        if r.get("C2_NM") != "계":
            continue
        c1 = r.get("C1"); nm = r.get("C1_NM"); itm = r.get("ITM_ID")
        d = agg.setdefault(c1, {"name": nm})
        if itm == "T1":
            d["budget"] = num(r.get("DT"))
        elif itm == "T3":
            d["exec"] = num(r.get("DT"))

    # 시도 블록 순서로 매칭
    result, unmatched = {}, []
    cur_sido = None
    sido_level = {}   # atlas_sido_code -> {budget,exec}
    for c1 in sorted(agg.keys()):
        e = agg[c1]; nm = e["name"]
        sc = atlas_sido(nm)
        if sc:  # 시도 헤더
            cur_sido = sc
            sido_level[sc] = {"budget": e.get("budget"), "exec": e.get("exec")}
            continue
        if "본청" in (nm or ""):
            continue
        if not cur_sido:
            continue
        acode = sgg_index.get(cur_sido, {}).get(nm)
        if not acode:
            unmatched.append((cur_sido, nm))
            continue
        result[acode] = {"budget": e.get("budget"), "exec": e.get("exec")}

    # decline.json 병합
    decline = json.load(open(DECLINE, encoding="utf-8"))
    budget = decline.get("budget") or {}
    by_code = budget.setdefault("by_code", {})

    def per_capita(exec_baekman, code):
        p = pop.get(code)
        if not exec_baekman or not p:
            return None
        return round(exec_baekman * 100.0 / p, 1)  # 백만원*1e6 / p / 1e4 = *100/p 만원

    def to_100m(baekman):
        return round(baekman / 100.0) if baekman else None  # 억원

    n_budget = 0
    for acode, v in result.items():
        ent = by_code.setdefault(acode, {"level": "시군구", "src": SRC_URL})
        ent["budget_final_100m"] = to_100m(v.get("budget"))
        ent["expenditure_settled_100m"] = to_100m(v.get("exec"))
        ent["expenditure_per_capita_manwon"] = per_capita(v.get("exec"), acode)
        ent["settle_year"] = int(YEAR)
        ent["settle_src"] = SRC_URL
        if ent["budget_final_100m"] is not None:
            n_budget += 1

    # 세종시(36110): 세종특별자치시 = 단일 단체 → 시도 값 그대로(정확)
    sejong_sc = sido_by_name.get("세종특별자치시")
    if sejong_sc and sejong_sc in sido_level:
        code = "36110"
        ent = by_code.setdefault(code, {"level": "시도단위대체", "src": SRC_URL})
        sv = sido_level[sejong_sc]
        ent["budget_final_100m"] = to_100m(sv.get("budget"))
        ent["expenditure_settled_100m"] = to_100m(sv.get("exec"))
        ent["expenditure_per_capita_manwon"] = per_capita(sv.get("exec"), code)
        ent["settle_year"] = int(YEAR)
        ent["settle_src"] = SRC_URL
        if ent["budget_final_100m"] is not None and code not in result:
            n_budget += 1

    # 제주시·서귀포시: 행정시 → 예산 금액 없음(명시적 null)
    for code in NO_AMOUNT_SUB:
        if code in by_code:
            by_code[code].setdefault("budget_final_100m", None)
            by_code[code].setdefault("expenditure_settled_100m", None)
            by_code[code]["settle_note"] = "행정시(자치단체 아님)로 단체 단위 예산·결산 미제공"

    budget.setdefault("sources", []).append({
        "name": "지방자치단체 세입세출(예산현액·결산세출) DT_110001_A011",
        "org": "KOSIS·행정안전부 지방재정", "url": SRC_URL,
        "year": int(YEAR), "tbl_id": TBL,
    })
    cov = budget.setdefault("coverage", {})
    cov["budget_total_codes"] = n_budget
    cov["settle_year"] = int(YEAR)
    budget["notes"] = (budget.get("notes", "") +
        " [예산·집행 추가] 지자체 예산규모(예산현액 최종)·실제지출(결산세출)·주민 1인당 세출을 "
        "KOSIS 행정안전부 지방재정 표(DT_110001_A011, 2023)에서 전 시군구로 병합했습니다. "
        "예산현액은 최종예산, 결산세출은 이월·추경 포함 총계 기준이라 둘의 단순 비율(집행률)은 산정하지 않았습니다. "
        "제주시·서귀포시는 행정시로 단체 단위 예산·결산이 없어 금액은 null입니다.")

    decline["budget"] = budget
    with open(DECLINE, "w", encoding="utf-8") as f:
        json.dump(decline, f, ensure_ascii=False, indent=2)

    print("[done] 예산·결산 매칭 %d개, budget_total_codes=%d, unmatched=%d" %
          (len(result), n_budget, len(unmatched)))
    if unmatched:
        print("[unmatched]", unmatched[:30])


if __name__ == "__main__":
    main()
