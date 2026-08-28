"""판결 확정 — 룰 채점 → 죄명·판단 생성 → 전문 조립 → 저장.

- 판정(유무죄·유형·형량·evidence·costPerUse)은 전부 trial_service 룰이 결정한다.
  Bedrock/MOCK 어느 쪽이든 판정 값은 동일하다. LLM은 crime(죄명)·reasoning(판단)만 만든다.
- Bedrock 실패/MOCK → docs/03 §3 폴백 룰(죄명 템플릿 + reasoning 템플릿).
- verdictText는 서버가 섹션 조립한 전문을 저장·응답한다(records 상세 호환).
"""
import json
import logging

import constants as C
from db import get_conn
from services import llm_service as llm
from services import trial_service as trial

logger = logging.getLogger("bedrock")

CRIME_MAX = 12  # 죄명 최대 글자

# ── docs/03 §3 판결문 프롬프트 v2 (§0 문장 금칙 포함) ─────────────────
VERDICT_SYSTEM = f"""너는 소비 재판소의 판사다. 심문이 끝났고 판정은 이미 확정되어 있다.
판정(유무죄·유형·형량)을 바꾸면 무효다. 너는 두 가지만 쓴다.
{trial.NO_SLOP}
1) crime(죄명): 이 사건에 붙일 죄명 한 줄, 12자 이내. 품목의 특성을 비틀어라.
   (예: "냉장고 유기죄", "구독료 방치죄", "서랍 중복 보유죄") 무죄면 "죄명 없음".
2) reasoning(재판부 판단): 2~3문장. 피고인의 실제 답변을 인용해 판정 이유를 서술하고,
   최후 변론(plea)이 있으면 한 문장으로 인용하며 받아들이거나 기각한다.
반드시 아래 JSON 하나만 출력한다: {{"crime": "...", "reasoning": "..."}}"""

# 폴백 죄명 템플릿 — 최다 기여 요인별 (docs/03 §3 폴백 표)
FALLBACK_CRIME = {
    "EG": "잔고 외면죄",
    "RI": "중복 보유죄",
    "RETURN": "충동 결제죄",
    "INNOCENT": "죄명 없음",
}


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


def _crime_reasoning(dossier, answers, j, plea) -> tuple:
    """LLM으로 (crime, reasoning) 생성. 실패/MOCK → 폴백 룰. crime 검증까지 적용."""
    plea_line = f'\n최후 변론: "{plea}"' if plea else "\n최후 변론: (없음)"
    try:
        judgement_view = {
            "guiltLabel": j["guiltLabel"],
            "guiltScore": j["guiltScore"],
            "axisCode": j["axisCode"],
            "typeName": j["typeName"],
            "sentence": j["sentence"],
            "evidence": j["evidence"],
            "costPerUse": j["costPerUse"],
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
        return _fallback_crime(j), _template_reasoning(j, plea)
    except Exception as e:
        logger.error("Bedrock 호출 실패: %s", e)
        return _fallback_crime(j), _template_reasoning(j, plea)

    try:
        data = llm.extract_json(raw)
        crime = data.get("crime")
        reasoning = data.get("reasoning")
        crime = _sanitize_crime(crime, j)
        if not (isinstance(reasoning, str) and reasoning.strip()):
            reasoning = _template_reasoning(j, plea)
        else:
            reasoning = reasoning.strip()
        return crime, reasoning
    except Exception as e:
        logger.error("Bedrock 호출 실패: 판결문 파싱 실패 %s", e)
        return _fallback_crime(j), _template_reasoning(j, plea)


def _sanitize_crime(crime, j) -> str:
    """crime 검증: 무죄면 '죄명 없음' 강제, 12자 초과면 잘라내기, 빈 값이면 폴백."""
    if j["guilt"] == "INNOCENT":
        return "죄명 없음"
    if not isinstance(crime, str) or not crime.strip():
        return _fallback_crime(j)
    crime = crime.strip()
    if crime == "죄명 없음":  # 유죄인데 무죄 죄명이 오면 폴백으로 교정
        return _fallback_crime(j)
    return crime[:CRIME_MAX]


def _fallback_crime(j) -> str:
    """최다 기여 요인별 죄명 템플릿 (docs/03 §3 폴백)."""
    if j["guilt"] == "INNOCENT":
        return "죄명 없음"
    key = j.get("sentenceKey")
    if key == "USE":
        item = (j.get("itemName") or "물건")
        return f"{item} 방치죄"[:CRIME_MAX]
    return FALLBACK_CRIME.get(key, "충동 결제죄")


def _dossier_view(dossier) -> dict:
    return {
        "itemName": dossier.get("itemName"),
        "price": dossier.get("price"),
        "boughtAt": dossier.get("boughtAt"),
        "merchant": dossier.get("merchant"),
        "category": dossier.get("category"),
    }


def _template_reasoning(j, plea) -> str:
    """폴백 reasoning: evidence 나열 + plea 참작 (기존 _template_verdict 문단 2 재사용)."""
    body = " ".join(f"{e}." for e in j["evidence"])
    if plea:
        body += f" 피고인은 '{plea}'라 항변하였으나, 본 법정은 이를 참작하는 데 그치오."
    return body.strip()


def _assemble_verdict_text(dossier, j, crime, reasoning) -> str:
    """섹션 조립 전문 (피고인/죄명/주요 증거/재판부 판단/최종 판결/최종 소비 유형)."""
    item = dossier.get("itemName") or "물건"
    price = dossier.get("price") or 0
    merchant = dossier.get("merchant") or "어느 가게"
    bought = dossier.get("boughtAt") or "그날"

    lines = [
        f"[피고인] {bought}, {merchant}에서 {item}을(를) {price:,}원에 구매한 자.",
        f"[죄명] {crime}",
        f"[주요 증거] {' / '.join(j['evidence'])}",
        f"[재판부 판단] {reasoning}",
        f"[최종 판결] {j['guiltLabel']} — {j['sentence']}",
        f"[최종 소비 유형] {j['typeName']} ({j['axisCode']})",
    ]
    return "\n".join(lines)


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
        "sentenceKey": guilt["sentenceKey"],  # 죄명 폴백용
        "itemName": dossier.get("itemName"),   # USE 죄명 템플릿용
        "evidence": guilt["evidence"],
        "costPerUse": guilt["costPerUse"],
    }


def render_and_save(email: str, dossier: dict, answers: list, plea) -> dict:
    """판정 확정 + 죄명·판단 생성 + 전문 조립 + 저장. api-contract §판결 응답 data 반환."""
    j = decide(dossier, answers, plea)
    crime, reasoning = _crime_reasoning(dossier, answers, j, plea)
    verdict_text = _assemble_verdict_text(dossier, j, crime, reasoning)

    record_id = _save(email, dossier, j, verdict_text, crime, reasoning, plea, answers)

    return {
        "recordId": record_id,
        "axisCode": j["axisCode"],
        "typeName": j["typeName"],
        "typeEmoji": j["typeEmoji"],
        "guilt": j["guilt"],
        "guiltLabel": j["guiltLabel"],
        "guiltScore": j["guiltScore"],
        "sentence": j["sentence"],
        "crime": crime,
        "reasoning": reasoning,
        "verdictText": verdict_text,
        "evidence": j["evidence"],
        "costPerUse": j["costPerUse"],
    }


def _save(email, dossier, j, verdict_text, crime, reasoning, plea, answers) -> int:
    # 심문 기록은 서버 원본 뱅크 문구로 구성한다(클라이언트 텍스트 불신)
    interrogation = _interrogation_log(answers)
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO verdicts
              (email, itemName, price, boughtAt, merchant, category, photoKey,
               axisCode, typeName, guilt, guiltScore, sentence, verdictText,
               plea, evidenceJson, costPerUse, interrogationJson, crime, reasoning)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(interrogation, ensure_ascii=False),
                crime,
                reasoning,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()
