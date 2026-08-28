"""재판 — 질문 스타일링(LLM) + 채점 룰(결정적).

- style_questions: constants.QUESTION_BANK을 docs/03 §2로 Bedrock 재작성. 검증·폴백.
- score_axes / score_guilt: docs/01 §4·§5 그대로의 순수 함수. 판정은 전부 여기 룰이다.
  (api-contract: 서버는 클라이언트가 보낸 pole/guilt를 무시하고 constants 원본으로 재채점)
"""
import json
import logging

import constants as C
from services import llm_service as llm

logger = logging.getLogger("bedrock")

# ── docs/03 §0 문장 금칙 ─────────────────────────────────────────────
NO_SLOP = """문장 금칙 — 아래 패턴이 하나라도 나오면 실패다:
- "단순한 X가 아니라 Y" 식 이항 대비
- "주목할 점은:", "핵심은:", "문제는:" 식 콜론 공개
- "~를 보여주는 대목", "~의 증거입니다", "~하는 순간입니다" 식 의미 부풀리기
- "전문가들은", "연구에 따르면" 식 유령 출처
- 같은 뜻을 단어만 바꿔 반복하기
- "진정한 소비는 이제 시작이오" 식 심오한 척 마무리
- 느낌표 남발, 이모티콘, 괄호 안 부연
대신: 이 사건의 구체 사실(품목·금액·날짜·피고인의 실제 답변)만 짚어라.
짧고 단정한 문장. 근엄한 옛말투("~하오", "~인 것이오")를 유지하되 내용으로 웃겨라."""

# ── docs/03 §2 스타일리스트 프롬프트 ─────────────────────────────────
STYLE_SYSTEM = f"""너는 소비 재판소의 판사다. 아래 심문 질문 뱅크를 이 사건의 물건에 맞게 다시 쓴다.
{NO_SLOP}
철칙:
- 질문 id·순서·개수, 각 질문의 선택지 개수를 절대 바꾸지 않는다.
- 선택지의 '의미 방향'을 바꾸지 않는다(1번이 절제형 답이면 재작성 후에도 절제형 답이다).
- 질문은 2문장 이내, 선택지는 1문장(25자 이내). 존대가 아닌 하대 옛말투("~했소?").
- 사건의 품목명·금액·가맹점을 최소 3개 질문에 자연스럽게 박아 넣는다.
- 품목이 물건이 아니라 서비스·결제(택시·구독·외식·이체 등)면 '사용/개봉/서랍' 같은
  물건 표현을 '이용/만족/본전' 관점으로 바꿔라. 단 각 선택지의 절제/후회 방향은 유지한다.
  (예: "21만 9천원짜리 이어폰을 포장도 안 뜯었다니, 그건 소장품이오?")
- opening은 판사의 개정 선언 2문장: 사건번호·품목·금액 낭독 + "지금부터 심문을 시작하겠소."
반드시 아래 JSON 하나만 출력한다:
{{"opening": "...", "questions": [{{"id": "USE", "text": "...", "choices": ["...", "...", "..."]}}, ...]}}"""


# ── opening 템플릿 (MOCK·폴백 공용, docs/03 §4) ──────────────────────
def _opening_template(dossier: dict) -> str:
    item = dossier.get("itemName") or "그 물건"
    price = dossier.get("price") or 0
    return (
        f"사건번호 2026-소비-001. 피고인은 {item} {price:,}원 건으로 본 법정에 섰소. "
        f"지금부터 심문을 시작하겠소."
    )


def _base_questions() -> list:
    """원본 뱅크를 그대로 계약 형태(태그 포함)로 복제해 내려준다."""
    out = []
    for q in C.QUESTION_BANK:
        out.append(
            {
                "id": q["id"],
                "axis": q["axis"],
                "askIf": q["askIf"],
                "text": q["text"],
                "choices": [
                    {"label": c["label"], "pole": c["pole"], "guilt": c["guilt"]}
                    for c in q["choices"]
                ],
            }
        )
    return out


def _apply_styled(styled: dict) -> list:
    """LLM 재작성 결과를 원본 태그에 덮어씌운다.

    검증: id 집합·순서 동일, 각 질문 choices 개수 동일. 어긋난 질문은 기본 문구 유지.
    (태그 pole/guilt/askIf/axis는 항상 서버 원본을 쓴다 — LLM은 문구만 바꾼다.)
    """
    base = _base_questions()
    styled_qs = {q.get("id"): q for q in styled.get("questions", []) if isinstance(q, dict)}

    for q in base:
        sq = styled_qs.get(q["id"])
        if not isinstance(sq, dict):
            continue  # 이 질문은 기본 문구 유지
        new_text = sq.get("text")
        new_choices = sq.get("choices")
        # choices 개수가 원본과 다르면 이 질문 전체를 기본 문구로 폴백
        if not isinstance(new_choices, list) or len(new_choices) != len(q["choices"]):
            continue
        if isinstance(new_text, str) and new_text.strip():
            q["text"] = new_text.strip()
        for i, label in enumerate(new_choices):
            if isinstance(label, str) and label.strip():
                q["choices"][i]["label"] = label.strip()[:40]
    return base


def style_questions(dossier: dict) -> dict:
    """질문 뱅크를 사건 맞춤으로 재작성. {opening, questions, source} 반환."""
    base = _base_questions()

    try:
        user = (
            "사건 조서: "
            + json.dumps(_dossier_for_prompt(dossier), ensure_ascii=False)
            + "\n질문 뱅크 원본: "
            + json.dumps(_bank_for_prompt(), ensure_ascii=False)
            + "\n이 사건에 맞게 재작성하라."
        )
        raw = llm.call_text(STYLE_SYSTEM, user, use_thinking=False)
    except llm.MockAIError:
        return {"opening": _opening_template(dossier), "questions": base, "source": "mock"}
    except Exception as e:
        logger.error("Bedrock 호출 실패: %s", e)
        return {"opening": _opening_template(dossier), "questions": base, "source": "fallback"}

    # 파싱·검증
    try:
        styled = llm.extract_json(raw)
    except Exception as e:
        logger.error("Bedrock 호출 실패: 질문 스타일 파싱 실패 %s", e)
        return {"opening": _opening_template(dossier), "questions": base, "source": "fallback"}

    # id 집합·순서 검사 — 어긋나면 전체 폴백(문구만), 태그는 어차피 원본
    styled_ids = [q.get("id") for q in styled.get("questions", []) if isinstance(q, dict)]
    if styled_ids != C.QUESTION_ORDER:
        questions = _base_questions()  # 순서/개수 불일치 → 문구도 기본
        source = "fallback"
    else:
        questions = _apply_styled(styled)
        source = "bedrock"

    opening = styled.get("opening")
    if not isinstance(opening, str) or not opening.strip():
        opening = _opening_template(dossier)

    return {"opening": opening.strip(), "questions": questions, "source": source}


def _dossier_for_prompt(dossier: dict) -> dict:
    return {
        "itemName": dossier.get("itemName"),
        "price": dossier.get("price"),
        "boughtAt": dossier.get("boughtAt"),
        "merchant": dossier.get("merchant"),
        "category": dossier.get("category"),
    }


def _bank_for_prompt() -> list:
    """LLM에는 id·text·choices label만 준다(태그 유출 없이 문구만 재작성)."""
    return [
        {"id": q["id"], "text": q["text"], "choices": [c["label"] for c in q["choices"]]}
        for q in C.QUESTION_BANK
    ]


# ══════════════════════════════════════════════════════════════════════
#  채점 룰 (docs/01 §4·§5) — 순수 함수. 판정은 전부 여기다.
# ══════════════════════════════════════════════════════════════════════

# id → 원본 질문 (빠른 조회)
_Q_BY_ID = {q["id"]: q for q in C.QUESTION_BANK}


def _answered_choice(answer):
    """answer({questionId, choiceIndex})에서 (question, choice) 반환. 범위 밖이면 (None,None)."""
    qid = answer.get("questionId")
    idx = answer.get("choiceIndex")
    q = _Q_BY_ID.get(qid)
    if q is None or not isinstance(idx, int):
        return None, None
    if idx < 0 or idx >= len(q["choices"]):
        return None, None
    return q, q["choices"][idx]


def score_axes(dossier: dict, answers: list) -> dict:
    """docs/01 §4: 선반영 ±1 + 답변 pole ±2, 축별 합. 합 0이면 앞 글자."""
    scores = {axis: 0 for axis in C.AXES}

    # 1) 조서 선반영 (±1)
    prefill = C.AXIS_PREFILL.get(dossier.get("category"))
    if prefill:
        scores[prefill["axis"]] += C.POLE_SIGN[prefill["pole"]] * 1

    # 2) 답변 합산 (±2) — 서버 원본 pole 사용
    for a in answers or []:
        q, choice = _answered_choice(a)
        if q is None or choice is None:
            continue
        pole = choice.get("pole")
        if pole is None:
            continue
        axis = q["axis"]
        if axis in scores:
            scores[axis] += C.POLE_SIGN[pole] * 2

    # 3) 축별 최종 글자 (합 0 → 앞 글자)
    code = ""
    for axis in C.AXES:  # EG, RI, FS, QD 순
        s = scores[axis]
        code += C.AXIS_POLES[axis]["front"] if s >= 0 else C.AXIS_POLES[axis]["back"]

    return {"axisCode": code, "axisScores": scores}


def _grade(score: int) -> dict:
    for cut in C.GUILT_CUTS:
        if cut["max"] is None or score <= cut["max"]:
            return {"guilt": cut["guilt"], "guiltLabel": cut["label"]}
    return {"guilt": C.GUILT_CUTS[-1]["guilt"], "guiltLabel": C.GUILT_CUTS[-1]["label"]}


def _sentence_key(contrib: dict, guilt: str) -> str:
    """최다 기여 요인 → 형량 키. 무죄면 INNOCENT. 동점이면 SENTENCE_ORDER 위쪽 우선."""
    if guilt == "INNOCENT":
        return "INNOCENT"
    best_key = None
    best_val = -1
    for key in C.SENTENCE_ORDER:  # USE, EG, RI, RETURN
        v = contrib.get(key, 0)
        if v > best_val:  # 엄격히 클 때만 갱신 → 동점은 먼저 온 위쪽이 이긴다
            best_val = v
            best_key = key
    # 아무 요인도 기여 안 했으면(전부 0인데 무죄 아님은 불가) 안전하게 USE
    return best_key or "USE"


def score_guilt(dossier: dict, answers: list) -> dict:
    """docs/01 §5: guilt 합산 + USE③·price≥100000 보정 +1, 컷, 형량, evidence, costPerUse."""
    price = dossier.get("price") or 0
    try:
        price = int(price)
    except (TypeError, ValueError):
        price = 0

    total = 0
    contrib = {"USE": 0, "EG": 0, "RI": 0, "RETURN": 0}
    use_idx = None
    evidence = []

    for a in answers or []:
        q, choice = _answered_choice(a)
        if q is None or choice is None:
            continue
        g = choice.get("guilt", 0) or 0
        total += g
        qid = q["id"]
        if qid == "USE":
            use_idx = a.get("choiceIndex")
            contrib["USE"] += g
        elif qid in ("EG1", "EG2"):
            contrib["EG"] += g
        elif qid in ("RI1", "RI2"):
            contrib["RI"] += g
        elif qid == "RETURN":
            contrib["RETURN"] += g

    # USE③(포장 안 뜯음, index 2) + price >= 100000 → +1
    if use_idx == 2 and price >= 100000:
        total += 1
        contrib["USE"] += 1

    grade = _grade(total)

    # costPerUse: USE① null / USE② round(price/3) / USE③ price
    if use_idx == 0:
        cost_per_use = None
    elif use_idx == 1:
        cost_per_use = round(price / 3) if price else 0
    elif use_idx == 2:
        cost_per_use = price
    else:
        cost_per_use = None

    sentence_key = _sentence_key(contrib, grade["guilt"])
    sentence = C.SENTENCES[sentence_key]

    evidence = _build_evidence(dossier, answers, use_idx, price, cost_per_use)

    return {
        "guiltScore": total,
        "guilt": grade["guilt"],
        "guiltLabel": grade["guiltLabel"],
        "sentence": sentence,
        "sentenceKey": sentence_key,  # 최다 기여 요인 (USE/EG/RI/RETURN/INNOCENT) — 죄명 폴백용
        "evidence": evidence,
        "costPerUse": cost_per_use,
    }


def _build_evidence(dossier, answers, use_idx, price, cost_per_use) -> list:
    """사람이 읽는 한국어 증거 문장 배열."""
    ev = []

    # 사용 여부
    if use_idx == 0:
        ev.append("구매 후 거의 매일 사용 중")
    elif use_idx == 1:
        ev.append("구매 후 가끔만 사용 (사용 3회로 추정)")
    elif use_idx == 2:
        ev.append("구매 후 사용 0회 — 포장 미개봉 (회당 단가 = 전액)")

    # 회당 단가
    if cost_per_use:
        ev.append(f"회당 단가 {cost_per_use:,}원 (가격 ÷ 추정 사용 횟수)")

    # 답변에서 드러난 정황
    for a in answers or []:
        q, choice = _answered_choice(a)
        if q is None or choice is None:
            continue
        qid = q["id"]
        idx = a.get("choiceIndex")
        if qid == "EG1" and idx == 2:
            ev.append("결제 시점 잔고를 확인하지 않음")
        elif qid == "EG2" and idx == 1:
            ev.append("가격 비교 없이 즉시 결제")
        elif qid == "RI1" and idx == 2:
            ev.append("유사 물품을 이미 다수 보유")
        elif qid == "FS1" and idx == 1:
            ev.append("기능이 아니라 외양을 보고 구매")
        elif qid == "RI2" and idx == 1:
            ev.append("소비가 특정 달에 몰림")
        elif qid == "RETURN" and idx == 2:
            ev.append("피고인 스스로 구매를 후회함")

    if not ev:
        item = dossier.get("itemName") or "물건"
        ev.append(f"{item} 구매 기록 확인")
    return ev
