"""판정 룰의 단일 출처 (docs/01-판정룰표.md를 그대로 옮긴 것).

어긋나면 docs가 맞다. LLM은 어떤 판정에도 관여하지 않는다.
필드명은 camelCase 계약(api-contract.md) 그대로 유지한다.
"""

# ── §1/화면: 카테고리 6종 (코드 → 한글 라벨) ─────────────────────────
CATEGORIES = {
    "FASHION_BEAUTY": "패션·뷰티",
    "FOOD_DINING": "식음료·외식",
    "DIGITAL_APPLIANCE": "가전·디지털",
    "HOBBY_LEISURE": "취미·여가",
    "LIVING_GROCERY": "생활·식료품",
    "OTHER": "기타",
}

# ── §2: 16유형 (axisCode → {name, emoji}) ───────────────────────────
CONSUMER_TYPES = {
    "ERFQ": {"name": "차분하고 엄격한 자기관리 끝판왕", "emoji": "📒"},
    "ERFD": {"name": "절제를 할 줄 아는 멋진 활동가", "emoji": "🏃"},
    "ERSQ": {"name": "관리형, 쇼핑도 즐기는 멋쟁이", "emoji": "🛍️"},
    "ERSD": {"name": "절제하며 패션과 스타일을 중시하는 활동가", "emoji": "👔"},
    "EIFQ": {"name": "변화와 도전을 꿈꾸는 차분한 관리자", "emoji": "🌱"},
    "EIFD": {"name": "절제가 쉽지 않아 고민 중인 활동가", "emoji": "🎢"},
    "EISQ": {"name": "절제가 쉽지 않지만 노력 중인 멋쟁이", "emoji": "💄"},
    "EISD": {"name": "패션과 스타일을 중시하는 외향형 활동가", "emoji": "🕶️"},
    "GRFQ": {"name": "절제하며 만남을 즐기는 차분한 스타일", "emoji": "🍵"},
    "GRFD": {"name": "절제하며 만남을 즐기는 활동가", "emoji": "🍻"},
    "GRSQ": {"name": "자유로운 성향의 쇼핑 멋쟁이", "emoji": "🎁"},
    "GRSD": {"name": "자유로운 영혼의 패션 활동가", "emoji": "👗"},
    "GIFQ": {"name": "낭만과 감성을 아는 자유로운 영혼", "emoji": "🌙"},
    "GIFD": {"name": "낭만과 감성을 아는 기분파 활동가", "emoji": "🎪"},
    "GISQ": {"name": "차분하고 조용한 자유로운 영혼", "emoji": "🎧"},
    "GISD": {"name": "패션과 낭만을 중시하는 외향형 활동가", "emoji": "🕺"},
}

TYPE_SOURCE_LABEL = "유형 분류: 소비 MBTI 16 (MPiA · blog.naver.com/ezpbill)"

# ── §3: 질문 뱅크 (기본 문구) ────────────────────────────────────────
# pole: 답변 축 점수 기여(±2 성격 / 프론트 게이지·askIf 판정용). guilt: 유죄 점수 기여.
# 진행 순서 고정: USE → EG1 → RI1 → FS1 → QD1 → (EG2) → (RI2) → RETURN.
# askIf: None이면 무조건 질문. {"axis":..,"whenScore":0}이면 그 시점까지 해당 축 pole 합이 0일 때만.
QUESTION_BANK = [
    {
        "id": "USE",
        "axis": "GUILT",
        "askIf": None,
        "text": "지금 그 물건은 어디서 무엇을 하고 있소?",
        "choices": [
            {"label": "거의 매일 쓰고 있습니다", "pole": None, "guilt": 0},
            {"label": "가끔… 생각나면 씁니다", "pole": None, "guilt": 1},
            {"label": "…아직 포장도 안 뜯었습니다", "pole": None, "guilt": 3},
        ],
    },
    {
        "id": "EG1",
        "axis": "EG",
        "askIf": None,
        "text": "이걸 결제하던 순간, 이번 달에 얼마나 썼는지 알고는 있었소?",
        "choices": [
            {"label": "네, 가계부에 다 적혀 있습니다", "pole": "E", "guilt": 0},
            {"label": "대충 감으로는 알고 있었습니다", "pole": None, "guilt": 1},
            {"label": "통장 잔고는 보는 게 아니라고 배웠습니다", "pole": "G", "guilt": 2},
        ],
    },
    {
        "id": "RI1",
        "axis": "RI",
        "askIf": None,
        "text": "이런 종류의 소비, 이번이 처음이오?",
        "choices": [
            {"label": "매달 정해둔 만큼만 삽니다", "pole": "R", "guilt": 0},
            {"label": "처음은 아니지만 드문 일입니다", "pole": None, "guilt": 0},
            {"label": "…서랍에 비슷한 게 몇 개 더 있습니다", "pole": "I", "guilt": 2},
        ],
    },
    {
        "id": "FS1",
        "axis": "FS",
        "askIf": None,
        "text": "그 물건, 쓰려고 샀소 — 아니면 예뻐서 샀소?",
        "choices": [
            {"label": "필요해서 샀습니다. 기능을 보고 골랐습니다", "pole": "F", "guilt": 0},
            {"label": "예쁘면 그게 곧 필요한 것 아니겠습니까", "pole": "S", "guilt": 1},
        ],
    },
    {
        "id": "QD1",
        "axis": "QD",
        "askIf": None,
        "text": "그 물건은 주로 어디에서 활약하는 물건이오?",
        "choices": [
            {"label": "집입니다. 제 방에서 씁니다", "pole": "Q", "guilt": 0},
            {"label": "밖입니다. 사람들 만날 때 빛을 봅니다", "pole": "D", "guilt": 0},
        ],
    },
    {
        "id": "EG2",
        "axis": "EG",
        "askIf": {"axis": "EG", "whenScore": 0},
        "text": "그래서, 가격 비교는 해보고 산 것이오?",
        "choices": [
            {"label": "세 군데는 비교하고 최저가로 샀습니다", "pole": "E", "guilt": 0},
            {"label": "첫눈에 반해 그 자리에서 결제했습니다", "pole": "G", "guilt": 2},
        ],
    },
    {
        "id": "RI2",
        "axis": "RI",
        "askIf": {"axis": "RI", "whenScore": 0},
        "text": "피고인의 지출은 매달 비슷하오, 들쭉날쭉하오?",
        "choices": [
            {"label": "매달 거의 똑같습니다", "pole": "R", "guilt": 0},
            {"label": "꽂히는 달엔 크게 나갑니다", "pole": "I", "guilt": 1},
        ],
    },
    {
        "id": "RETURN",
        "axis": "GUILT",
        "askIf": None,
        "text": "마지막으로 묻겠소. 그날로 돌아간다면, 또 사겠소?",
        "choices": [
            {"label": "네. 백 번이라도 다시 삽니다", "pole": None, "guilt": 0},
            {"label": "…조금 더 고민은 해볼 것 같습니다", "pole": None, "guilt": 1},
            {"label": "안 삽니다. 그 돈이면…", "pole": None, "guilt": 2},
        ],
    },
]

# 질문 순서(id) — 채점·검증의 기준
QUESTION_ORDER = [q["id"] for q in QUESTION_BANK]

# ── §4-1: 조서 선반영 (카테고리 → 축 ±1) ─────────────────────────────
# 앞 글자 = +, 뒤 글자 = −. 여기 없는 카테고리는 0.
AXIS_PREFILL = {
    "FASHION_BEAUTY": {"axis": "FS", "pole": "S"},   # S = 뒤 글자 → −1
    "LIVING_GROCERY": {"axis": "FS", "pole": "F"},   # F = 앞 글자 → +1
    "HOBBY_LEISURE": {"axis": "QD", "pole": "D"},    # D = 뒤 글자 → −1
}

# 4축 정의: 앞 글자(+) / 뒤 글자(−)
AXES = ["EG", "RI", "FS", "QD"]
AXIS_POLES = {
    "EG": {"front": "E", "back": "G"},
    "RI": {"front": "R", "back": "I"},
    "FS": {"front": "F", "back": "S"},
    "QD": {"front": "Q", "back": "D"},
}
# 각 pole 글자의 부호 (+1 앞 / -1 뒤)
POLE_SIGN = {
    "E": 1, "G": -1,
    "R": 1, "I": -1,
    "F": 1, "S": -1,
    "Q": 1, "D": -1,
}

# ── §5: 유죄 점수 등급 (0~3 무죄 / 4~6 집행유예 / 7+ 유죄) ─────────────
GUILT_CUTS = [
    {"max": 3, "guilt": "INNOCENT", "label": "무죄"},
    {"max": 6, "guilt": "PROBATION", "label": "집행유예"},
    {"max": None, "guilt": "GUILTY", "label": "유죄"},  # 7 이상
]

# ── §5: 형량(sentence) — 최다 기여 요인 기준 템플릿 (동점이면 위쪽 우선) ──
# 판정 순위: USE → EG → RI → RETURN. 무죄는 별도 처리(INNOCENT).
SENTENCE_ORDER = ["USE", "EG", "RI", "RETURN"]
SENTENCES = {
    "USE": "피고인은 7일 이내 위 물건을 1회 이상 사용하거나, 중고 장터에 등록할 것을 명한다.",
    "EG": "피고인은 다음 5만원 이상 결제 전 24시간의 숙려 기간을 가질 것을 명한다.",
    "RI": "피고인은 보유 중인 동종 물품의 전수 조사를 실시하고 그 목록을 제출할 것을 명한다.",
    "RETURN": "피고인은 환불·교환 가능 여부를 24시간 이내 확인할 것을 명한다.",
    "INNOCENT": "본 법정은 위 소비를 훌륭한 소비로 인정한다. 피고인은 당당히 사용할 것.",
}
