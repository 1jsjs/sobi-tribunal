"""데모 전과 기록 5건 (demo@tribunal.kr).

유죄 2 · 집행유예 2 · 무죄 1, 유형·품목 다양하게.
판정 값은 실제 룰 함수로 계산해 저장하므로 화면 계약과 항상 일치한다.
실행 시 이미 있으면 건너뛴다(시드 훼손 금지).

실행: MOCK_AI=1 appenv/bin/python -m data.seed
"""
import json
import os
import sys

# 패키지 밖에서 직접 실행해도 임포트되도록
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_conn, init_db  # noqa: E402
from services import verdict_service as vs  # noqa: E402

DEMO_EMAIL = "demo@tribunal.kr"


def A(qid, idx):
    return {"questionId": qid, "choiceIndex": idx}


# (조서, 답변, 최후변론) — 답변은 목표 판정을 내도록 구성
CASES = [
    # 1) 무선 이어폰 — 유죄, GISD
    (
        {"itemName": "무선 이어폰", "price": 219000, "boughtAt": "2026-08-14",
         "merchant": "쿠팡", "category": "DIGITAL_APPLIANCE", "photoKey": None},
        [A("USE", 2), A("EG1", 2), A("RI1", 2), A("FS1", 1), A("QD1", 1), A("RETURN", 2)],
        "무선이라 편할 줄 알았습니다",
    ),
    # 2) 한정판 스니커즈 — 유죄, GISQ
    (
        {"itemName": "한정판 스니커즈", "price": 189000, "boughtAt": "2026-07-03",
         "merchant": "무신사", "category": "FASHION_BEAUTY", "photoKey": None},
        [A("USE", 2), A("EG1", 2), A("RI1", 2), A("FS1", 1), A("QD1", 0), A("RETURN", 1)],
        "한정판은 지금 아니면 못 삽니다",
    ),
    # 3) 홈베이킹 오븐 — 집행유예, GRFD
    (
        {"itemName": "홈베이킹 오븐", "price": 340000, "boughtAt": "2026-05-20",
         "merchant": "위메프", "category": "HOBBY_LEISURE", "photoKey": None},
        [A("USE", 1), A("EG1", 2), A("RI1", 1), A("FS1", 0), A("RI2", 0), A("QD1", 1), A("RETURN", 1)],
        None,
    ),
    # 4) 콘서트 티켓 — 집행유예, EISD
    (
        {"itemName": "콘서트 티켓", "price": 154000, "boughtAt": "2026-04-11",
         "merchant": "인터파크", "category": "HOBBY_LEISURE", "photoKey": None},
        [A("USE", 1), A("EG1", 1), A("EG2", 0), A("RI1", 2), A("FS1", 1), A("QD1", 1), A("RETURN", 1)],
        "친구랑 N빵 했습니다",
    ),
    # 5) 중고 책 — 무죄, ERFQ
    (
        {"itemName": "중고 책", "price": 12000, "boughtAt": "2026-02-08",
         "merchant": "알라딘", "category": "OTHER", "photoKey": None},
        [A("USE", 0), A("EG1", 0), A("RI1", 0), A("FS1", 0), A("QD1", 0), A("RETURN", 0)],
        None,
    ),
]


def already_seeded() -> bool:
    conn = get_conn()
    try:
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM verdicts WHERE email = ?", (DEMO_EMAIL,)
        ).fetchone()["c"]
    finally:
        conn.close()
    return n > 0


def run():
    init_db()
    if already_seeded():
        print(f"시드 건너뜀: {DEMO_EMAIL} 기록이 이미 있소.")
        return

    for dossier, answers, plea in CASES:
        result = vs.render_and_save(DEMO_EMAIL, dossier, answers, plea)
        print(
            f"  #{result['recordId']} {dossier['itemName']}"
            f" → {result['guiltLabel']} / {result['axisCode']} {result['typeName']}"
        )
    print(f"시드 완료: {DEMO_EMAIL} 전과 {len(CASES)}건 등록.")


if __name__ == "__main__":
    run()
