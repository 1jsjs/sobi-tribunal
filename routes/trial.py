"""POST /api/trial/start, POST /api/trial/verdict (verdict는 B305).

Body(None)으로 받아 직접 검증(422 금지 → 400 봉투).
"""
import re

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

import constants as C
from services.trial_service import style_questions
from services.verdict_service import render_and_save

router = APIRouter(prefix="/api/trial", tags=["trial"])

# 아이디@도메인.tld — 데모 수준 검증
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_VALID_QIDS = set(C.QUESTION_ORDER)
_CHOICE_COUNT = {q["id"]: len(q["choices"]) for q in C.QUESTION_BANK}


def _ok(data, status: int = 200):
    return JSONResponse(status_code=status, content={"success": True, "data": data})


def _fail(code: str, message: str, status: int = 400):
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def _valid_dossier(dossier) -> bool:
    if not isinstance(dossier, dict):
        return False
    item = dossier.get("itemName")
    if not isinstance(item, str) or not item.strip():
        return False
    price = dossier.get("price")
    # price는 정수여야 한다 (bool은 int 서브클래스라 배제)
    if isinstance(price, bool) or not isinstance(price, int):
        return False
    return True


@router.post("/start")
def trial_start(body: dict = Body(None)):
    dossier = body.get("dossier") if isinstance(body, dict) else None
    if not _valid_dossier(dossier):
        return _fail("INVALID_DOSSIER", "조서가 온전치 않소. 품목명과 금액을 확인하시오")

    result = style_questions(dossier)
    return _ok(result)


def _normalize_email(raw):
    """trim + 소문자. 형식·254자 위반 시 None."""
    if not isinstance(raw, str):
        return None
    email = raw.strip().lower()
    if not email or len(email) > 254 or not _EMAIL_RE.match(email):
        return None
    return email


def _valid_answers(answers) -> bool:
    if not isinstance(answers, list) or len(answers) < 6:
        return False
    for a in answers:
        if not isinstance(a, dict):
            return False
        qid = a.get("questionId")
        idx = a.get("choiceIndex")
        if qid not in _VALID_QIDS:
            return False
        if isinstance(idx, bool) or not isinstance(idx, int):
            return False
        if idx < 0 or idx >= _CHOICE_COUNT[qid]:
            return False
    return True


@router.post("/verdict")
def trial_verdict(body: dict = Body(None)):
    if not isinstance(body, dict):
        body = {}

    email = _normalize_email(body.get("email"))
    if email is None:
        return _fail("INVALID_EMAIL", "피고인의 이메일이 온전치 않소")

    answers = body.get("answers")
    if not _valid_answers(answers):
        return _fail("INVALID_ANSWERS", "심문 답변이 온전치 않소. 최소 6문에 답하시오")

    plea = body.get("plea")
    if plea is not None:
        if not isinstance(plea, str):
            return _fail("INVALID_PLEA", "변론이 온전치 않소")
        if len(plea) > 200:
            return _fail("INVALID_PLEA", "최후 변론은 200자 이내로 하시오")
        plea = plea.strip() or None

    dossier = body.get("dossier")
    if not _valid_dossier(dossier):
        return _fail("INVALID_DOSSIER", "조서가 온전치 않소. 품목명과 금액을 확인하시오")

    # 클라이언트 pole/guilt는 무시하고 constants 원본으로 재채점 (verdict_service 내부 룰)
    result = render_and_save(email, dossier, answers, plea)
    return _ok(result, status=201)
