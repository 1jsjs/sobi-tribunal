"""POST /api/intake — 사진 → 조서.

multipart 필드명 `file`. File(None)으로 받아 직접 검증(422 금지 → 400 봉투).
"""
import logging

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from services.intake_service import MEDIA_TYPES, process_intake

logger = logging.getLogger("bedrock")

router = APIRouter(prefix="/api", tags=["intake"])

MAX_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED = set(MEDIA_TYPES.keys())  # image/jpeg, image/png, image/webp


def _ok(data, status: int = 200):
    return JSONResponse(status_code=status, content={"success": True, "data": data})


def _fail(code: str, message: str, status: int = 400):
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


@router.post("/intake")
async def intake(file: UploadFile = File(None)):
    # 1) 파일 없음
    if file is None:
        return _fail("INVALID_FILE", "증거 사진을 제출하시오")

    content_type = (file.content_type or "").lower()
    image_bytes = await file.read()

    # 2) 빈 파일 / 형식 위반
    if not image_bytes:
        return _fail("INVALID_FILE", "증거 사진을 제출하시오")
    if content_type not in ALLOWED:
        return _fail("INVALID_FILE", "jpg·png·webp 형식의 사진만 받소")

    # 3) 크기 초과
    if len(image_bytes) > MAX_BYTES:
        return _fail("INVALID_FILE", "사진은 5MB 이하여야 하오")

    data = process_intake(image_bytes, content_type)
    return _ok(data)
