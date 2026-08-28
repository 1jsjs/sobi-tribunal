"""B305 E2E: start(MOCK) → verdict 201 → records 반영, 이메일 정규화, INVALID_* 3종."""
import os
import tempfile

os.environ.setdefault("MOCK_AI", "1")

import pytest

import db as db_module


@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    """각 테스트를 임시 DB로 격리 (실 DB·시드 훼손 금지)."""
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    monkeypatch.setattr(db_module, "DB_PATH", path)
    db_module.init_db()
    yield
    os.remove(path)


def _client():
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app)


DOSSIER = {
    "itemName": "무선 이어폰",
    "price": 219000,
    "boughtAt": "2026-08-14",
    "merchant": "쿠팡",
    "category": "DIGITAL_APPLIANCE",
    "photoKey": None,
}

# 유죄가 나오는 답변 (전부 반대)
GUILTY_ANSWERS = [
    {"questionId": "USE", "choiceIndex": 2},
    {"questionId": "EG1", "choiceIndex": 2},
    {"questionId": "RI1", "choiceIndex": 2},
    {"questionId": "FS1", "choiceIndex": 1},
    {"questionId": "QD1", "choiceIndex": 1},
    {"questionId": "RETURN", "choiceIndex": 2},
]


def test_e2e_start_verdict_records():
    c = _client()

    # 1) start (MOCK)
    r = c.post("/api/trial/start", json={"dossier": DOSSIER})
    assert r.status_code == 200
    assert r.json()["data"]["source"] == "mock"

    # 2) verdict → 201
    r = c.post(
        "/api/trial/verdict",
        json={"email": "pjs@example.com", "dossier": DOSSIER, "answers": GUILTY_ANSWERS,
              "plea": "월급날이었단 말입니다"},
    )
    assert r.status_code == 201, r.text
    v = r.json()["data"]
    assert v["axisCode"] == "GISD"
    assert v["guilt"] == "GUILTY"
    assert v["guiltScore"] == 11
    assert v["typeEmoji"] == "🕺"
    assert v["costPerUse"] == 219000
    assert isinstance(v["verdictText"], str) and v["verdictText"]
    assert isinstance(v["evidence"], list) and v["evidence"]
    # B307: crime·reasoning 필드 존재, 유죄면 죄명이 "죄명 없음"이 아니어야
    assert isinstance(v["crime"], str) and v["crime"] and v["crime"] != "죄명 없음"
    assert len(v["crime"]) <= 12
    assert isinstance(v["reasoning"], str) and v["reasoning"]
    # 조립 전문에 섹션 라벨이 들어있어야 (records 상세 호환)
    assert "[죄명]" in v["verdictText"] and "[최종 판결]" in v["verdictText"]
    record_id = v["recordId"]

    # 3) records 목록에 반영
    r = c.get("/api/records", params={"email": "pjs@example.com"})
    assert r.status_code == 200
    rows = r.json()["data"]
    assert len(rows) == 1
    assert rows[0]["id"] == record_id
    assert rows[0]["itemName"] == "무선 이어폰"
    assert rows[0]["guiltLabel"] == "유죄"

    # 4) 상세 조회
    r = c.get(f"/api/records/{record_id}")
    assert r.status_code == 200
    detail = r.json()["data"]
    assert detail["plea"] == "월급날이었단 말입니다"
    assert detail["guiltScore"] == 11
    assert isinstance(detail["evidence"], list)
    assert isinstance(detail["verdictText"], str)
    # B307: 상세에 crime·reasoning
    assert detail["crime"] == v["crime"]
    assert detail["reasoning"] == v["reasoning"]
    # 심문 기록: 답변 수만큼, 각 항목은 {q, a}
    assert isinstance(detail["interrogation"], list)
    assert len(detail["interrogation"]) == len(GUILTY_ANSWERS)
    assert all("q" in x and "a" in x for x in detail["interrogation"])


INNOCENT_ANSWERS = [
    {"questionId": "USE", "choiceIndex": 0},
    {"questionId": "EG1", "choiceIndex": 0},
    {"questionId": "RI1", "choiceIndex": 0},
    {"questionId": "FS1", "choiceIndex": 0},
    {"questionId": "QD1", "choiceIndex": 0},
    {"questionId": "RETURN", "choiceIndex": 0},
]


def test_innocent_crime_is_none_label():
    # B307: 무죄면 crime == "죄명 없음"
    c = _client()
    r = c.post(
        "/api/trial/verdict",
        json={"email": "in@b.kr", "dossier": {**DOSSIER, "price": 9000}, "answers": INNOCENT_ANSWERS},
    )
    assert r.status_code == 201, r.text
    v = r.json()["data"]
    assert v["guilt"] == "INNOCENT"
    assert v["crime"] == "죄명 없음"


def test_email_uppercase_normalized_to_lowercase():
    c = _client()
    # 대문자·공백 이메일로 판결
    r = c.post(
        "/api/trial/verdict",
        json={"email": "  PJS@EXAMPLE.COM  ", "dossier": DOSSIER, "answers": GUILTY_ANSWERS},
    )
    assert r.status_code == 201
    # 소문자로 조회된다
    r = c.get("/api/records", params={"email": "pjs@example.com"})
    assert r.status_code == 200
    assert len(r.json()["data"]) == 1


def test_invalid_email():
    c = _client()
    r = c.post(
        "/api/trial/verdict",
        json={"email": "not-an-email", "dossier": DOSSIER, "answers": GUILTY_ANSWERS},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_EMAIL"


def test_invalid_answers_too_few():
    c = _client()
    r = c.post(
        "/api/trial/verdict",
        json={"email": "a@b.kr", "dossier": DOSSIER,
              "answers": [{"questionId": "USE", "choiceIndex": 0}]},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_ANSWERS"


def test_invalid_answers_bad_choice_index():
    c = _client()
    bad = list(GUILTY_ANSWERS)
    bad[0] = {"questionId": "USE", "choiceIndex": 9}  # 범위 밖
    r = c.post(
        "/api/trial/verdict",
        json={"email": "a@b.kr", "dossier": DOSSIER, "answers": bad},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_ANSWERS"


def test_invalid_plea_too_long():
    c = _client()
    r = c.post(
        "/api/trial/verdict",
        json={"email": "a@b.kr", "dossier": DOSSIER, "answers": GUILTY_ANSWERS,
              "plea": "가" * 201},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_PLEA"


def test_records_invalid_email_400():
    c = _client()
    r = c.get("/api/records", params={"email": "nope"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_EMAIL"


def test_record_not_found_404():
    c = _client()
    r = c.get("/api/records/99999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
