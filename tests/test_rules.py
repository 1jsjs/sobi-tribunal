"""B304 채점 룰 검증 — docs/01 §4·§5와 숫자 하나까지 일치해야 한다."""
import os

os.environ.setdefault("MOCK_AI", "1")

from services.trial_service import score_axes, score_guilt


def A(qid, idx):
    return {"questionId": qid, "choiceIndex": idx}


# ── 축 판정 경계값 ───────────────────────────────────────────────────
def test_all_restraint_gives_ERFQ_and_innocent():
    dossier = {"itemName": "책", "price": 12000, "category": "OTHER"}
    answers = [A("USE", 0), A("EG1", 0), A("RI1", 0), A("FS1", 0), A("QD1", 0), A("RETURN", 0)]
    ax = score_axes(dossier, answers)
    assert ax["axisCode"] == "ERFQ"
    g = score_guilt(dossier, answers)
    assert g["guiltScore"] == 0
    assert g["guilt"] == "INNOCENT"
    assert g["guiltLabel"] == "무죄"
    assert g["sentence"].startswith("본 법정은 위 소비를 훌륭한")


def test_all_opposite_gives_GISD_and_guilty():
    dossier = {"itemName": "이어폰", "price": 219000, "category": "DIGITAL_APPLIANCE"}
    # askIf: EG1=G(-2)면 EG2 미출제, RI1=I(-2)면 RI2 미출제 → 6문
    answers = [A("USE", 2), A("EG1", 2), A("RI1", 2), A("FS1", 1), A("QD1", 1), A("RETURN", 2)]
    ax = score_axes(dossier, answers)
    assert ax["axisCode"] == "GISD"
    g = score_guilt(dossier, answers)
    # 3 + 2 + 2 + 1 + 0 + 2 = 10, USE③+price≥10만 → +1 = 11
    assert g["guiltScore"] == 11
    assert g["guilt"] == "GUILTY"
    assert g["costPerUse"] == 219000


# ── 유죄 점수 컷 경계 (0~3 / 4~6 / 7+) ───────────────────────────────
def test_guilt_score_3_is_innocent():
    dossier = {"itemName": "물건", "price": 9000, "category": "OTHER"}
    answers = [A("USE", 1), A("EG1", 1), A("RETURN", 1)]  # 1+1+1 = 3
    g = score_guilt(dossier, answers)
    assert g["guiltScore"] == 3
    assert g["guilt"] == "INNOCENT"


def test_guilt_score_4_is_probation():
    dossier = {"itemName": "물건", "price": 9000, "category": "OTHER"}
    answers = [A("USE", 1), A("EG1", 2), A("RETURN", 1)]  # 1+2+1 = 4
    g = score_guilt(dossier, answers)
    assert g["guiltScore"] == 4
    assert g["guilt"] == "PROBATION"
    assert g["guiltLabel"] == "집행유예"


def test_guilt_score_6_is_probation():
    dossier = {"itemName": "물건", "price": 9000, "category": "OTHER"}
    # USE③ guilt 3이지만 price<10만이라 +1 보정 없음 → 3+1+2 = 6
    answers = [A("USE", 2), A("EG1", 1), A("RETURN", 2)]
    g = score_guilt(dossier, answers)
    assert g["guiltScore"] == 6
    assert g["guilt"] == "PROBATION"


def test_guilt_score_7_is_guilty():
    dossier = {"itemName": "물건", "price": 9000, "category": "OTHER"}
    answers = [A("USE", 2), A("EG1", 2), A("RI1", 2)]  # 3+2+2 = 7
    g = score_guilt(dossier, answers)
    assert g["guiltScore"] == 7
    assert g["guilt"] == "GUILTY"


# ── 6문 재판(EG2 미포함)도 채점 가능 ─────────────────────────────────
def test_six_question_trial_without_eg2():
    dossier = {"itemName": "물건", "price": 50000, "category": "OTHER"}
    # EG1 중립(idx1, pole None) → EG축 합 0이지만 EG2가 answers에 없어도 채점되어야 한다
    answers = [A("USE", 0), A("EG1", 1), A("RI1", 1), A("FS1", 0), A("QD1", 0), A("RETURN", 0)]
    ax = score_axes(dossier, answers)
    # EG: 답변 pole 없음 → 합 0 → 앞 글자 E
    assert ax["axisScores"]["EG"] == 0
    assert ax["axisCode"][0] == "E"
    g = score_guilt(dossier, answers)
    assert g["guiltScore"] == 1  # EG1 idx1 guilt 1


# ── 선반영 vs 답변 (답변이 이긴다) ───────────────────────────────────
def test_fashion_prefill_S_when_no_answer():
    dossier = {"itemName": "립스틱", "price": 30000, "category": "FASHION_BEAUTY"}
    # FS1 미응답 → FS 합 = 선반영 -1 → 뒤 글자 S
    answers = [A("USE", 0), A("EG1", 0), A("RI1", 0), A("QD1", 0), A("RETURN", 0)]
    ax = score_axes(dossier, answers)
    assert ax["axisScores"]["FS"] == -1
    assert ax["axisCode"][2] == "S"


def test_answer_F_beats_fashion_prefill():
    dossier = {"itemName": "립스틱", "price": 30000, "category": "FASHION_BEAUTY"}
    # 선반영 -1 + FS1=F(+2) = +1 → 앞 글자 F
    answers = [A("USE", 0), A("EG1", 0), A("RI1", 0), A("FS1", 0), A("QD1", 0), A("RETURN", 0)]
    ax = score_axes(dossier, answers)
    assert ax["axisScores"]["FS"] == 1
    assert ax["axisCode"][2] == "F"


# ── costPerUse 규칙 ──────────────────────────────────────────────────
def test_cost_per_use_rules():
    d = {"itemName": "x", "price": 30000, "category": "OTHER"}
    assert score_guilt(d, [A("USE", 0)])["costPerUse"] is None
    assert score_guilt(d, [A("USE", 1)])["costPerUse"] == 10000  # round(30000/3)
    assert score_guilt(d, [A("USE", 2)])["costPerUse"] == 30000
