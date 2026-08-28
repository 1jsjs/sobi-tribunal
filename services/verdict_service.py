"""판결 확정 — 룰 채점 → 판결문 생성 → 저장.

- 판정(유무죄·유형·형량·evidence·costPerUse)은 전부 trial_service 룰이 결정한다.
  Bedrock/MOCK 어느 쪽이든 판정 값은 동일하다. LLM은 verdictText(산문)만 만든다.
- Bedrock 실패/MOCK → docs/03 §4 템플릿 조립.
"""
import json
import logging

import constants as C
from db import get_conn
from services import llm_service as llm
from services import trial_service as trial

logger = logging.getLogger("bedrock")

# ── docs/03 §3 판결문 프롬프트 (§0 문장 금칙 포함) ───────────────────
VERDICT_SYSTEM = f"""너는 소비 재판소의 판사다. 심문이 끝났고 판정은 이미 확정되어 있다.
너의 일은 판결문 낭독 원고를 쓰는 것뿐이다. 판정(유무죄·유형·형량)을 바꾸면 무효다.
{trial.NO_SLOP}
구성(총 6~9문장, 문단 3개):
1) 죄명 낭독: 품목·금액을 적시하며 이 사건이 무엇인지 선언
2) 증거 적시: 전달받은 evidence와 피고인의 실제 답변을 인용해 판정 이유 서술.
   피고인이 최후 변론(plea)을 냈다면 한 문장으로 인용하고 받아들이거나 기각한다.
3) 주문: guiltLabel을 선고하고 sentence를 낭독, 마지막에 소비 유형(typeName)을 선언
반드시 아래 JSON 하나만 출력한다: {{"verdictText": "..."}}"""


def _q_by_id(qid):
    return {q["id"]: q for q in C.QUESTION_BANK}.get(qid)


def _interrogation_log(answers: list) -> list:
    """심문 기록: 원본 뱅크 문구 + 선택 라벨. [{"q":..., "a":...}]"""
    log = []
    for a in answers or []:
        q = _q_by_id(a.get("questionId"))
        idx = a.get("choiceIndex")
        if not q or not isinstance(idx, int) or idx < 0 or idx >= len(q["choices"]):
            continue
        log.append({"q": q["text"], "a": q["choices"][idx]["label"]})
    return log


def _verdict_text(dossier, answers, judgement, plea) -> str:
    """판결문 산문 생성. Bedrock 실패/MOCK → 템플릿 조립."""
    plea_line = f'\n최후 변론: "{plea}"' if plea else "\n최후 변론: (없음)"
    try:
        judgement_view = {
            "guiltLabel": judgement["guiltLabel"],
            "guiltScore": judgement["guiltScore"],
            "axisCode": judgement["axisCode"],
            "typeName": judgement["typeName"],
            "sentence": judgement["sentence"],
            "evidence": judgement["evidence"],
            "costPerUse": judgement["costPerUse"],
        }
        user = (
            "조서: " + json.dumps(_dossier_view(dossier), ensure_ascii=False)
            + "\n심문 기록: " + json.dumps(_interrogation_log(answers), ensure_ascii=False)
            + "\n확정 판정: " + json.dumps(judgement_view, ensure_ascii=False)
            + plea_line
            + "\n판결문을 작성하라."
        )
        raw = llm.call_text(VERDICT_SYSTEM, user)
    except llm.MockAIError:
        return _template_verdict(dossier, judgement, plea)
    except Exception as e:
        logger.error("Bedrock 호출 실패: %s", e)
        return _template_verdict(dossier, judgement, plea)

    try:
        data = llm.extract_json(raw)
        text = data.get("verdictText")
        if isinstance(text, str) and text.strip():
            return text.strip()
        raise ValueError("verdictText 비어 있음")
    except Exception as e:
        logger.error("Bedrock 호출 실패: 판결문 파싱 실패 %s", e)
        return _template_verdict(dossier, judgement, plea)


def _dossier_view(dossier) -> dict:
    return {
        "itemName": dossier.get("itemName"),
        "price": dossier.get("price"),
        "boughtAt": dossier.get("boughtAt"),
        "merchant": dossier.get("merchant"),
        "category": dossier.get("category"),
    }


def _template_verdict(dossier, j, plea) -> str:
    """docs/03 §4 템플릿 조립."""
    item = dossier.get("itemName") or "물건"
    price = dossier.get("price") or 0
    merchant = dossier.get("merchant") or "어느 가게"
    bought = dossier.get("boughtAt") or "그날"

    p1 = f"피고인은 {bought}, {merchant}에서 {item}을(를) {price:,}원에 구매하였소."
    p2 = " ".join(f"{e}." for e in j["evidence"])
    plea_line = ""
    if plea:
        plea_line = f" 피고인은 '{plea}'라 항변하였으나, 본 법정은 이를 참작하는 데 그치오."
    p3 = (
        f"이에 본 법정은 {j['guiltLabel']}를 선고하오. {j['sentence']} "
        f"피고인의 소비 유형은 {j['typeName']}({j['axisCode']})이오."
    )
    return f"{p1} {p2}{plea_line} {p3}".strip()


def decide(dossier: dict, answers: list, plea) -> dict:
    """룰 채점 → 판정 확정 딕셔너리(판결문 제외 값 + verdictText 없이 반환).

    저장·응답에 필요한 모든 판정 값을 담는다.
    """
    axes = trial.score_axes(dossier, answers)
    guilt = trial.score_guilt(dossier, answers)

    axis_code = axes["axisCode"]
    type_info = C.CONSUMER_TYPES.get(axis_code, {"name": "미상 유형", "emoji": "❓"})

    return {
        "axisCode": axis_code,
        "typeName": type_info["name"],
        "typeEmoji": type_info["emoji"],
        "guilt": guilt["guilt"],
        "guiltLabel": guilt["guiltLabel"],
        "guiltScore": guilt["guiltScore"],
        "sentence": guilt["sentence"],
        "evidence": guilt["evidence"],
        "costPerUse": guilt["costPerUse"],
    }


def render_and_save(email: str, dossier: dict, answers: list, plea) -> dict:
    """판정 확정 + 판결문 생성 + 저장. api-contract §판결 응답 data 반환."""
    j = decide(dossier, answers, plea)
    verdict_text = _verdict_text(dossier, answers, j, plea)

    record_id = _save(email, dossier, j, verdict_text, plea)

    return {
        "recordId": record_id,
        "axisCode": j["axisCode"],
        "typeName": j["typeName"],
        "typeEmoji": j["typeEmoji"],
        "guilt": j["guilt"],
        "guiltLabel": j["guiltLabel"],
        "guiltScore": j["guiltScore"],
        "sentence": j["sentence"],
        "verdictText": verdict_text,
        "evidence": j["evidence"],
        "costPerUse": j["costPerUse"],
    }


def _save(email, dossier, j, verdict_text, plea) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO verdicts
              (email, itemName, price, boughtAt, merchant, category, photoKey,
               axisCode, typeName, guilt, guiltScore, sentence, verdictText,
               plea, evidenceJson, costPerUse)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                dossier.get("itemName"),
                dossier.get("price"),
                dossier.get("boughtAt"),
                dossier.get("merchant"),
                dossier.get("category"),
                dossier.get("photoKey"),
                j["axisCode"],
                j["typeName"],
                j["guilt"],
                j["guiltScore"],
                j["sentence"],
                verdict_text,
                plea,
                json.dumps(j["evidence"], ensure_ascii=False),
                j["costPerUse"],
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
