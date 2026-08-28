"""POST /api/trial/start, POST /api/trial/verdict (verdict는 B305).

Body(None)으로 받아 직접 검증(422 금지 → 400 봉투).
"""
from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from services.trial_service import style_questions

router = APIRouter(prefix="/api/trial", tags=["trial"])


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
