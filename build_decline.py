# -*- coding: utf-8 -*-
"""
build_decline.py — 대한민국 인구전망 아틀라스: 인구감소지역/지방소멸대응기금/대응정책 결합 데이터 생성기.

원칙(비협상): 확인된 수치·명단만 반영. 확인 못한 개별 배분액/등급은 null.
출처·연도·URL을 meta.sources에 병기. 임의 숫자 생성 금지.

입력: data/atlas.json (시군구 코드 체계의 정본; name->5자리코드 매핑을 여기서 도출)
출력: data/decline.json

사용법:
  python build_decline.py            # generated=오늘
  python build_decline.py 2026-07-02 # generated 지정
"""
import json
import os
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ATLAS = os.path.join(HERE, "data", "atlas.json")
OUT = os.path.join(HERE, "data", "decline.json")

# ---------------------------------------------------------------------------
# 1) 출처 (조사에서 확인된 공식/2차 출처)
# ---------------------------------------------------------------------------
SOURCES = [
    {"name": "인구감소지역 지정 현황", "org": "행정안전부",
     "url": "https://www.mois.go.kr/frt/sub/a06/b06/populationDecline/screen.do", "year": 2021},
    {"name": "인구감소지역 지원 특별법 안내", "org": "행정안전부",
     "url": "https://www.mois.go.kr/frt/sub/a06/b06/populationDeclineLaw/screen.do", "year": 2023},
    {"name": "지방소멸대응기금 안내(연도별 배분현황)", "org": "행정안전부",
     "url": "https://www.mois.go.kr/frt/sub/a06/b06/localextinctionFund/screen.do", "year": 2025},
    {"name": "지방소멸대응기금 배분기준 고시(제2024-6호)", "org": "행정안전부",
     "url": "https://www.mois.go.kr/frt/bbs/type001/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000016&nttId=106561", "year": 2024},
    {"name": "2025년도 지방소멸대응기금 배분 자료", "org": "KDI 경제정보센터",
     "url": "https://eiec.kdi.re.kr/policy/materialView.do?num=259239", "year": 2025},
    {"name": "2024년도 차등배분 자료", "org": "KDI 경제정보센터",
     "url": "https://eiec.kdi.re.kr/policy/materialView.do?num=244398", "year": 2024},
    {"name": "지방소멸대응기금 최초(2022) 배분 자료", "org": "KDI 경제정보센터",
     "url": "https://eiec.kdi.re.kr/policy/materialView.do?num=229097", "year": 2022},
    {"name": "지방소멸대응기금 집행/배분 분석", "org": "나라살림연구소",
     "url": "https://www.narasallim.net/report/546", "year": 2023},
    {"name": "고향사랑기부제 안내", "org": "행정안전부",
     "url": "https://www.mois.go.kr/frt/sub/a06/b06/hometownLovedonation/screen.do", "year": 2023},
    {"name": "생활인구 중심 지방소멸대응 정책브리핑", "org": "대한민국 정책브리핑(korea.kr)",
     "url": "https://www.korea.kr/news/policyNewsView.do?newsId=148955792", "year": 2025},
]

NOTES = (
    "인구감소지역 89곳은 행안부 최초지정(2021.10) 명단으로, 군위군은 2023년 대구 편입 반영. "
    "관심지역 18곳은 언론·2차출처 재인용(확신도 중간, 행안부 원문 1:1 대조 미완). "
    "지방소멸대응기금 by_code는 시군구별 개별 배분액·등급이 공식 원문에서 확정 확인되지 않아 비움({}). "
    "grade_bands는 확인된 연도별 등급체계·배분범위만 수록(2022~2023 등급별 금액 미확인). "
    "모든 개별 배분액은 확인 전까지 amount_krw:null. 확인 못한 값은 생성하지 않음."
)

# ---------------------------------------------------------------------------
# 2) 인구감소지역 89곳 (시도명 -> [시군구명]) — designation 조사 명단
#    시도명은 atlas.json의 sido['name']과 정확히 일치시킴.
# ---------------------------------------------------------------------------
DESIGNATED_89 = {
    "부산광역시": ["동구", "서구", "영도구"],
    "대구광역시": ["남구", "서구", "군위군"],
    "인천광역시": ["강화군", "옹진군"],
    "경기도": ["가평군", "연천군"],
    "강원특별자치도": ["고성군", "삼척시", "양구군", "양양군", "영월군", "정선군",
                 "철원군", "태백시", "평창군", "홍천군", "화천군", "횡성군"],
    "충청북도": ["괴산군", "단양군", "보은군", "영동군", "옥천군", "제천시"],
    "충청남도": ["공주시", "금산군", "논산시", "보령시", "부여군", "서천군",
              "예산군", "청양군", "태안군"],
    "전북특별자치도": ["고창군", "김제시", "남원시", "무주군", "부안군", "순창군",
                 "임실군", "장수군", "정읍시", "진안군"],
    "전라남도": ["강진군", "고흥군", "곡성군", "구례군", "담양군", "보성군",
              "신안군", "영광군", "영암군", "완도군", "장성군", "장흥군",
              "진도군", "함평군", "해남군", "화순군"],
    "경상북도": ["고령군", "문경시", "봉화군", "상주시", "성주군", "안동시",
              "영덕군", "영양군", "영주시", "영천시", "울릉군", "울진군",
              "의성군", "청도군", "청송군"],
    "경상남도": ["거창군", "고성군", "남해군", "밀양시", "산청군", "의령군",
              "창녕군", "하동군", "함안군", "함양군", "합천군"],
}

# 관심지역 18곳 (시도명 -> [시군구명]) — 확신도 중간
INTEREST_18 = {
    "경기도": ["동두천시", "포천시"],
    "강원특별자치도": ["강릉시", "동해시", "속초시", "인제군"],
    "전북특별자치도": ["익산시"],
    "경상북도": ["경주시", "김천시"],
    "경상남도": ["사천시", "통영시"],
    "부산광역시": ["금정구", "중구"],
    "인천광역시": ["동구"],
    "광주광역시": ["동구"],
    "대전광역시": ["대덕구", "동구", "중구"],
}


def build_name_index(atlas):
    """sido_name -> {sgg_name -> code}, 그리고 code -> (sido_name, sgg_name)."""
    by_sido = {}
    code_meta = {}
    for s in atlas["sido"]:
        sname = s["name"]
        m = {}
        for r in s["rows"]:
            m[r["name"]] = r["code"]
            code_meta[r["code"]] = (sname, r["name"])
        by_sido[sname] = m
    return by_sido, code_meta


def resolve(by_sido, mapping, unmatched):
    """(sido_name -> [sgg]) 명단을 code->name 딕셔너리로 변환. 미매칭은 unmatched에 축적."""
    out = {}
    for sido_name, names in mapping.items():
        sub = by_sido.get(sido_name)
        if sub is None:
            for nm in names:
                unmatched.append(f"{sido_name} {nm} (시도 미존재)")
            continue
        for nm in names:
            code = sub.get(nm)
            if code is None:
                unmatched.append(f"{sido_name} {nm}")
                continue
            out[code] = nm
    return out


def main():
    generated = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()

    with open(ATLAS, encoding="utf-8") as f:
        atlas = json.load(f)
    by_sido, code_meta = build_name_index(atlas)

    unmatched = []
    designated = resolve(by_sido, DESIGNATED_89, unmatched)
    interest = resolve(by_sido, INTEREST_18, unmatched)

    # designation.codes 구성
    codes = {}
    for code, nm in designated.items():
        codes[code] = {"name": nm, "designated": True, "type": "인구감소지역"}
    for code, nm in interest.items():
        # 관심지역이 인구감소지역과 코드 충돌하면 안 됨(제도상 배타)
        if code in codes:
            unmatched.append(f"{nm}({code}) 인구감소·관심 중복")
            continue
        codes[code] = {"name": nm, "designated": False, "type": "관심지역"}

    designation = {
        "criteria": ("인구감소지수 8개 지표 종합: 연평균인구증감률, 인구밀도, 청년순이동률, "
                     "주간인구, 고령화비율, 유소년비율, 조출생률, 재정자립도"),
        "law": ("지방자치분권 및 지역균형발전 특별법 제2조·시행령 제3조 및 "
                "인구감소지역 지원 특별법(근거 법령 원문 대조 권장)"),
        "designated_year": 2021,
        "reassessment_cycle_years": 5,
        "next_reassessment": 2026,
        "total_count": 89,
        "interest_count": 18,
        "counted_designated": len(designated),
        "counted_interest": len(interest),
        "codes": dict(sorted(codes.items())),
    }

    # -----------------------------------------------------------------------
    # fund — 구조/총액/등급밴드만 확인분 수록. 개별 by_code는 미확인 -> 비움.
    # -----------------------------------------------------------------------
    fund = {
        "annual_total_krw": 1_000_000_000_000,   # 매년 1조원 (2022년만 7,500억)
        "start_year": 2022,
        "end_year": 2031,
        "period_years": 10,
        "first_year_total_krw": 750_000_000_000,  # 2022년 최초배분 7,500억
        "account_split": {"광역지원계정_krw": 250_000_000_000, "기초지원계정_krw": 750_000_000_000, "note": "1조원 기준, 광역25%/기초75%"},
        "operator": "17개 시·도 조합 → 한국지방재정공제회 위탁 운용",
        "distribution_method": "기초=평가단 성과평가 등급 차등배분 / 광역=인구감소지역 비율 등 정액배분",
        "recipients_2025": {"광역": 15, "기초": 107, "note": "기초=인구감소지역89+관심지역18"},
        "grade_bands": [
            {"year": 2022, "system": "A~E 5단계", "designated_range_krw": None,
             "interest_range_krw": None, "confidence": "낮음",
             "note": "등급체계는 확인, 등급별 개별 금액 미확인"},
            {"year": 2024, "system": "S·A·B·C 4단계",
             "designated_range_krw": [6_400_000_000, 14_400_000_000],
             "interest_range_krw": [1_600_000_000, 3_600_000_000],
             "confidence": "중간",
             "note": "최고-최저 등급차 56억→80억 확대(KDI 244398)"},
            {"year": 2025, "system": "우수·양호 2단계",
             "designated_range_krw": [7_200_000_000, 16_000_000_000],
             "interest_range_krw": [1_800_000_000, 4_000_000_000],
             "confidence": "중간",
             "note": "인구감소 기본72억+우수88억=최대160억, 관심 기본18억+우수22억=최대40억. 우수 인구감소 8곳·우수 관심 2곳(개별 명단 미확인)"},
        ],
        "execution": [
            {"scope": "2022년 배분분", "as_of": "2023-06-30", "overall_rate": 0.3757,
             "wide_area_rate": 0.9367, "basic_rate": 0.1885,
             "zero_exec_count": 11, "confidence": "중간~높음",
             "source_url": "https://www.narasallim.net/report/546"},
        ],
        "by_code": {},  # 시군구별 개별 배분액/등급 공식 확정치 미확인 → 생성 금지
        "by_code_note": "시군구별 개별 배분액·등급은 행안부 고시 붙임 PDF 파싱 필요. 확인 전까지 비움.",
    }

    # -----------------------------------------------------------------------
    # policy_playbook — 실제 제도·사업명 연결, 프로필 4종 x 3~4 measure
    # -----------------------------------------------------------------------
    MOIS_FUND = "https://www.mois.go.kr/frt/sub/a06/b06/localextinctionFund/screen.do"
    KOREA_LIFE = "https://www.korea.kr/news/policyNewsView.do?newsId=148955792"
    MOIS_DONATION = "https://www.mois.go.kr/frt/sub/a06/b06/hometownLovedonation/screen.do"
    KDI_2025 = "https://eiec.kdi.re.kr/policy/materialView.do?num=259239"

    playbook = [
        {"profile": "소멸_고위험",
         "desc": "소멸위험지수 0.2 미만 초고령·인구급감 지역. 정주기반 유지가 최우선.",
         "measures": [
             {"title": "지방소멸대응기금 노인·의료 집중투자", "real_program": "지방소멸대응기금(기초지원계정) 노인·의료 분야",
              "desc": "찾아가는 의료·돌봄, 폐교·유휴시설 리모델링 등 생존기반 투자로 집행률을 높여 차등배분 우수등급 확보.",
              "source_url": MOIS_FUND},
             {"title": "생활인구·체류인구 확대", "real_program": "생활인구 제도(주민등록+체류인구 합산)",
              "desc": "완도 '치유의 섬'형 체류형 관광·여객선 운임지원으로 정주인구 감소를 생활인구로 보완.",
              "source_url": KOREA_LIFE},
             {"title": "고향사랑기부제 지정기부 연계", "real_program": "고향사랑기부제(2023 시행, 지정기부)",
              "desc": "돌봄·의료 등 특정사업 지정기부로 세외재원 확보(답례품 30% 이내, 10만원까지 전액 세액공제).",
              "source_url": MOIS_DONATION},
             {"title": "빈집·유휴자산 정비", "real_program": "지방소멸대응기금 주거 분야",
              "desc": "빈집 정비 후 리빙스테이션·청년상회 전환으로 재정착 기반 조성(영월군 사례).",
              "source_url": KOREA_LIFE},
         ]},
        {"profile": "위험_진입",
         "desc": "소멸위험 진입(지수 0.2~0.5) 지역. 청년유입·일자리로 반등 시도.",
         "measures": [
             {"title": "로컬 창업·청년 일자리", "real_program": "지방소멸대응기금 산업·일자리 분야",
              "desc": "청년 로컬창업 지원, 청년협력가 양성·마을 파견(하동군 사례)으로 유출 방지.",
              "source_url": KOREA_LIFE},
             {"title": "관계인구 → 정주인구 전환", "real_program": "생활인구·관계인구 정책",
              "desc": "워케이션·두지역살이 프로그램으로 관계인구를 형성하고 정주로 유도.",
              "source_url": KOREA_LIFE},
             {"title": "성과평가 대응 집행관리", "real_program": "지방소멸대응기금 성과평가 차등배분",
              "desc": "집행률·성과지표 관리로 우수등급(최대 160억) 확보, 사업 다층화.",
              "source_url": KDI_2025},
             {"title": "고향사랑기부 답례품 지역경제 연계", "real_program": "고향사랑기부제 답례품",
              "desc": "지역 농특산품 답례품으로 소상공인 매출·기부수입 동시 확보.",
              "source_url": MOIS_DONATION},
         ]},
        {"profile": "중견도시_감소",
         "desc": "인구 규모는 있으나 감소세인 중소도시. 산업·주거 재구조화 중심.",
         "measures": [
             {"title": "산업·일자리 거점 투자", "real_program": "지방소멸대응기금 산업·일자리 분야",
              "desc": "지역 주력산업 연계 일자리·창업공간으로 청년 정착 유도(2023 산업·일자리 비중 25%).",
              "source_url": "https://www.narasallim.net/report/744"},
             {"title": "주거·정주여건 개선", "real_program": "지방소멸대응기금 주거 분야",
              "desc": "청년·신혼 주거지원과 생활SOC로 전입 유인(2023 주거 비중 22%).",
              "source_url": "https://www.narasallim.net/report/744"},
             {"title": "교육·보육 정주매력 강화", "real_program": "지방소멸대응기금 교육·보육 분야",
              "desc": "돌봄·교육 인프라로 청년가구 유지, 통근·통학 교통 연계.",
              "source_url": MOIS_FUND},
         ]},
        {"profile": "정체_증가",
         "desc": "인구 정체 또는 증가 지역(지정 제외). 광역 정액계정·연계협력 활용.",
         "measures": [
             {"title": "광역지원계정 연계협력", "real_program": "지방소멸대응기금 광역지원계정(정액배분)",
              "desc": "인접 인구감소지역과 광역 연계사업(교통·의료·관광 벨트)으로 균형발전 견인.",
              "source_url": KDI_2025},
             {"title": "생활인구 허브 기능", "real_program": "생활인구 제도",
              "desc": "인근 소멸위험 지역의 생활인구 유입 거점(의료·상권) 역할로 광역 상생.",
              "source_url": KOREA_LIFE},
             {"title": "고향사랑기부 매칭·홍보 지원", "real_program": "고향사랑기부제",
              "desc": "규모·행정역량을 활용해 인접 지역 기부 캠페인·플랫폼을 공동 운영.",
              "source_url": MOIS_DONATION},
         ]},
    ]

    result = {
        "meta": {
            "generated": generated,
            "sources": SOURCES,
            "notes": NOTES,
            "unmatched": unmatched,
            "atlas_source": atlas.get("meta", {}).get("source"),
        },
        "designation": designation,
        "fund": fund,
        "policy_playbook": playbook,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    size = os.path.getsize(OUT)
    print(f"OUT={OUT}")
    print(f"size_bytes={size}")
    print(f"designated_matched={len(designated)}/89")
    print(f"interest_matched={len(interest)}/18")
    print(f"designation_codes_total={len(codes)}")
    print(f"fund_by_code={len(fund['by_code'])}")
    print(f"unmatched={unmatched}")


if __name__ == "__main__":
    main()
