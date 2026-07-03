# -*- coding: utf-8 -*-
"""
build_finance.py — data/finance.json 생성 (지방재정365 lofin365 OpenAPI).

수집 대상(실호출 검증 완료, 표준 라이브러리만):
  AIDFA  구조별 기능별 세출예산 : 분야(fld)별 사업예산 — 2008~2026 확인
  JFIED  재정자립도(최종)      : 개편전/후 자립도 시계열 — 2010~2025 확인
  LLBSI  지방교부세 인센티브    : 항목별 인센티브(성과 프록시) — 2012~2025 확인

미수집(사유를 meta.notes 에 정직 기재):
  HCFDA 분야별 세출현황  — 공식 샘플 URL조차 CMSE0025 서버 오류(2026-07 확인)
  ACCAM 지방채 잔액      — 시도 본청 17건만 존재, 시군구 데이터 없음
  SIHHC 세입현황         — 일 단위·최근 연도만 보존, 연간 시계열 불가
  UCMZQK 지방보조금      — 2016~2019 이후 갱신 중단

인증키: lofin365 자체 발급 키 필요(data.go.kr 키는 ERROR-290 무효 확인).
  우선순위: --key > 환경변수 LOFIN365_API_KEY > isochrone_map/.env 의 LOFIN365_API_KEY
  키 없이 실행하면 샘플 모드(요청당 5행, 1페이지)로 파싱·매칭만 검증한다.

지자체코드: lofin365 laf_cd(행안부 7자리)는 atlas 코드(KOSIS 5자리)와 다르다.
  → laf_hg_nm("경북안동시" 형식)에서 시도 축약 프리픽스를 떼고 시군구명 이름매칭.
"""
import os, ssl, json, sys, time, argparse, urllib.request, urllib.parse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ATLAS = os.path.join(HERE, "data", "atlas.json")
OUT = os.path.join(HERE, "data", "finance.json")
ENV_PATH = r"C:\Users\user\Downloads\claude\isochrone_map\.env"
BASE = "https://www.lofin365.go.kr/lf/hub/"

FI_YEARS = list(range(2010, 2026))          # JFIED
INC_YEARS = list(range(2012, 2026))         # LLBSI (합계 시계열)
SRC = [
    {"name": "구조별 기능별 세출예산", "org": "행정안전부 지방재정365", "year": "2008~",
     "url": "https://www.data.go.kr/data/15058215/openapi.do"},
    {"name": "재정자립도(최종)", "org": "행정안전부 지방재정365", "year": "2010~",
     "url": "https://www.data.go.kr/data/15058102/openapi.do"},
    {"name": "지방교부세 인센티브현황", "org": "행정안전부 지방재정365", "year": "2012~",
     "url": "https://www.data.go.kr/data/15057324/openapi.do"},
]
INC_ITEMS = [  # LLBSI pfa_amt2~pfa_amt10 순서 (pfa_amt1 = 합계)
    "지방재정혁신", "인건비 건전운영", "지방의회 운영", "민간이전경비 절감",
    "행사축제경비 절감", "지방세 징수율 제고", "지방세 체납액 축소",
    "경상세외수입 확충", "지방세외수입 체납액 축소",
]


def load_key(cli_key):
    if cli_key:
        return cli_key
    if os.environ.get("LOFIN365_API_KEY"):
        return os.environ["LOFIN365_API_KEY"]
    try:
        with open(ENV_PATH, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("LOFIN365_API_KEY") and "=" in s:
                    return s.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return None  # 샘플 모드


def call(svc, params, key):
    q = dict(params)
    q["Type"] = "json"
    if key:
        q["Key"] = key
    url = BASE + svc + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    ctx = ssl.create_default_context()
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")  # lofin365 TLS 호환(관공서 구형 암호수트)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
                data = json.loads(r.read().decode("utf-8", errors="replace"))
            break
        except Exception as e:
            if attempt == 2:
                raise
            print("  [retry] %s %s" % (svc, e))
            time.sleep(3)
    body = data.get(svc)
    if not body:  # {"RESULT":{"CODE":"INFO-200"...}} 형태(데이터 없음/오류)
        code = (data.get("RESULT") or {}).get("CODE", "?")
        if code == "INFO-200":
            return []
        raise RuntimeError("%s %s %s" % (svc, code, (data.get("RESULT") or {}).get("MESSAGE", "")))
    rows = []
    for part in body:
        if "row" in part:
            rows.extend(part["row"])
    return rows


def fetch_all(svc, params, key, page_size=1000):
    """전 페이지 수집. 샘플 모드(키 없음)는 1페이지 5행만 반환됨."""
    rows, p = [], 1
    while True:
        chunk = call(svc, dict(params, pIndex=p, pSize=page_size), key)
        rows.extend(chunk)
        if not key or len(chunk) < page_size:
            return rows
        p += 1


def num(v):
    try:
        return round(float(str(v).replace(",", "")), 2)
    except (TypeError, ValueError):
        return None


# ── laf_hg_nm("경북안동시") → atlas 코드 매칭 ─────────────────────────
def build_matcher(atlas):
    shorts = {}
    for s in atlas["sido"]:
        idx = {}
        for r in s["rows"]:
            idx[r["name"]] = r["code"]
            idx[r["name"].replace(" ", "")] = r["code"]
        shorts[s["short"]] = (s["code"], idx)

    def match(laf_hg_nm, laf_cd, wa_laf_cd):
        if not laf_hg_nm or str(laf_cd) == str(wa_laf_cd):
            return None  # 본청(시도)·결측 제외
        nm = laf_hg_nm.strip()
        for short, (scode, idx) in shorts.items():
            if nm.startswith(short):
                rest = nm[len(short):]
                code = idx.get(rest) or idx.get(rest.replace(" ", ""))
                if code:
                    return code
        return None
    return match


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default="", help="lofin365 인증키 (미지정 시 자동 탐색, 없으면 샘플 모드)")
    ap.add_argument("--aidfa-year", type=int, default=0, help="기능별 세출 기준연도 (기본: 최신 자동 탐지)")
    args = ap.parse_args()
    key = load_key(args.key)
    sample = key is None
    print("[mode] %s" % ("샘플(키 없음, 요청당 5행) — 파싱 검증용" if sample else "정식 수집"))

    atlas = json.load(open(ATLAS, encoding="utf-8"))
    match = build_matcher(atlas)
    by = {}
    ok = lambda c: by.setdefault(c, {})

    # ── 1) AIDFA 구조별 기능별 세출예산: 최신연도 분야별 사업예산 ──
    ay = args.aidfa_year
    if not ay:
        for y in range(2026, 2020, -1):
            if fetch_all("AIDFA", {"fyr": y, "pIndex": 1, "pSize": 5}, key, page_size=5):
                ay = y
                break
    print("[AIDFA] 기준연도 %s 수집..." % ay)
    rows = fetch_all("AIDFA", {"fyr": ay}, key)
    n_match = 0
    for r in rows:
        code = match(r.get("laf_hg_nm"), r.get("laf_cd"), r.get("wa_laf_cd"))
        if not code:
            continue
        n_match += 1
        d = ok(code).setdefault("fld", {})
        f = r.get("fld_nm") or "기타"
        cur = d.setdefault(f, {"b": 0.0, "o": 0.0})
        cur["b"] += num(r.get("biz_bdg_tott_amt")) or 0.0        # 사업예산 총계
        cur["o"] += num(r.get("padm_oper_exps_tott_amt")) or 0.0  # 행정운영경비
    print("[AIDFA] rows=%d 매칭행=%d 지역=%d" % (len(rows), n_match, sum(1 for v in by.values() if "fld" in v)))

    # ── 2) JFIED 재정자립도 시계열 ──
    print("[JFIED] %s~%s 수집..." % (FI_YEARS[0], FI_YEARS[-1]))
    fi_tmp = {}
    for y in (FI_YEARS if not sample else FI_YEARS[-2:]):
        for r in fetch_all("JFIED", {"fyr": y}, key):
            code = match(r.get("laf_hg_nm"), r.get("laf_cd"), r.get("wa_laf_cd"))
            if code:
                fi_tmp.setdefault(code, {})[y] = [num(r.get("rate1")), num(r.get("rate2"))]
    for code, ym in fi_tmp.items():
        ys = sorted(ym)
        ok(code)["fi"] = {"years": ys, "pre": [ym[y][0] for y in ys], "post": [ym[y][1] for y in ys]}
    print("[JFIED] 지역=%d" % len(fi_tmp))

    # ── 3) LLBSI 교부세 인센티브: 최신 상세 + 합계 시계열 ──
    print("[LLBSI] %s~%s 수집..." % (INC_YEARS[0], INC_YEARS[-1]))
    inc_tmp = {}
    for y in (INC_YEARS if not sample else INC_YEARS[-1:]):
        for r in fetch_all("LLBSI", {"fyr": y}, key):
            code = match(r.get("laf_hg_nm"), r.get("laf_cd"), r.get("wa_laf_cd"))
            if not code:
                continue
            e = inc_tmp.setdefault(code, {"series": {}})
            e["series"][y] = num(r.get("pfa_amt1"))
            if y == max(INC_YEARS) or "items" not in e:
                e["items_year"] = y
                e["items"] = [num(r.get("pfa_amt%d" % i)) for i in range(2, 11)]
    for code, e in inc_tmp.items():
        ys = sorted(e["series"])
        ok(code)["inc"] = {"years": ys, "total": [e["series"][y] for y in ys],
                           "items_year": e["items_year"], "items": e["items"]}
    print("[LLBSI] 지역=%d" % len(inc_tmp))

    out = {
        "meta": {
            "generated": time.strftime("%Y-%m-%d"),
            "mode": "sample" if sample else "full",
            "aidfa_year": ay,
            "inc_item_names": INC_ITEMS,
            "sources": SRC,
            "notes": "금액 단위: AIDFA 원, LLBSI 백만원(lofin365 원문 단위 그대로). "
                     "분야별 세출현황(HCFDA)은 서버 오류, 지방채 잔액(ACCAM)은 시군구 데이터 부재, "
                     "세입현황(SIHHC)은 연간 시계열 불가, 지방보조금(UCMZQK)은 2019년 이후 갱신 중단으로 미수록(2026-07 확인).",
        },
        "by_code": by,
    }
    js = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(js)
    print("[out] %s (%.1f KB, 지역 %d곳)%s" % (
        OUT, len(js.encode("utf-8")) / 1024, len(by),
        " — 샘플 모드 산출물: 검증용, 커밋 금지" if sample else ""))


if __name__ == "__main__":
    main()
