# -*- coding: utf-8 -*-
"""kosis_budget_utils.py — build_budget.py / build_budget_exec.py 공통 KOSIS 호출 보일러플레이트."""
import os, ssl, json, urllib.request, urllib.parse

ENV_PATH = r"C:\Users\user\Downloads\claude\isochrone_map\.env"
BASE = "https://kosis.kr/openapi/Param/statisticsParameterData.do"


def load_key(env_path=ENV_PATH):
    if os.environ.get("KOSIS_API_KEY"):
        return os.environ["KOSIS_API_KEY"]
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s.startswith("KOSIS_API_KEY") and "=" in s:
                return s.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("KOSIS_API_KEY not found")


def call(params, base=BASE):
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
        raw = r.read().decode("utf-8", errors="replace")
    data = json.loads(raw)
    if isinstance(data, dict) and ("err" in data or "errMsg" in data):
        raise RuntimeError("KOSIS %s %s" % (data.get("err"), data.get("errMsg")))
    return data


def num(v, round_digits=None):
    try:
        n = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return round(n, round_digits) if round_digits is not None else n
