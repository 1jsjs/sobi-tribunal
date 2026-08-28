"""전과 기록 — GET /api/records?email= , GET /api/records/{id}.

주의: /api/records/{id} 라우트는 /api/records 보다 뒤에 등록한다.
"""
import json
import logging
import re

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from db import get_conn
from services.intake_service import S3_BUCKET, S3_ENDPOINT_URL, PRESIGN_TTL

logger = logging.getLogger("bedrock")

router = APIRouter(prefix="/api", tags=["records"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _ok(data, status: int = 200):
    return JSONResponse(status_code=status, content={"success": True, "data": data})


def _fail(code: str, message: str, status: int = 400):
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def _normalize_email(raw):
    if not isinstance(raw, str):
        return None
    email = raw.strip().lower()
    if not email or len(email) > 254 or not _EMAIL_RE.match(email):
        return None
    return email


def _presign(photo_key):
    """photoKey 있을 때만 presigned GET 재발급. 실패 시 None."""
    if not photo_key:
        return None
    try:
        import boto3

        s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT_URL)
        return s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": photo_key},
            ExpiresIn=PRESIGN_TTL,
        )
    except Exception as e:
        logger.error("S3 presign 실패: %s", e)
        return None


def _summary(row) -> dict:
    return {
        "id": row["id"],
        "itemName": row["itemName"],
        "price": row["price"],
        "category": row["category"],
        "axisCode": row["axisCode"],
        "typeName": row["typeName"],
        "typeEmoji": _emoji(row["axisCode"]),
        "guilt": row["guilt"],
        "guiltLabel": _label(row["guilt"]),
        "sentence": row["sentence"],
        "createdAt": row["createdAt"],
        "photoUrl": _presign(row["photoKey"]),
    }


def _emoji(axis_code):
    from constants import CONSUMER_TYPES

    return CONSUMER_TYPES.get(axis_code, {}).get("emoji", "❓")


def _label(guilt):
    return {"GUILTY": "유죄", "PROBATION": "집행유예", "INNOCENT": "무죄"}.get(guilt, guilt)


# ── 고정 경로 먼저 ───────────────────────────────────────────────────
@router.get("/records")
def list_records(email: str = Query(None)):
    norm = _normalize_email(email)
    if norm is None:
        return _fail("INVALID_EMAIL", "피고인의 이메일이 온전치 않소")

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM verdicts WHERE email = ? ORDER BY id DESC", (norm,)
        ).fetchall()
    finally:
        conn.close()

    return _ok([_summary(r) for r in rows])


# ── 경로 변수 라우트는 뒤에 ──────────────────────────────────────────
@router.get("/records/{record_id}")
def get_record(record_id: int):
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM verdicts WHERE id = ?", (record_id,)
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return _fail("NOT_FOUND", "그런 사건 기록은 없소", status=404)

    data = _summary(row)
    # 상세 = summary + verdictText, plea, guiltScore, evidence
    try:
        evidence = json.loads(row["evidenceJson"]) if row["evidenceJson"] else []
    except (ValueError, TypeError):
        evidence = []
    raw_intr = row["interrogationJson"] if "interrogationJson" in row.keys() else None
    try:
        interrogation = json.loads(raw_intr) if raw_intr else []
    except (ValueError, TypeError):
        interrogation = []
    data.update(
        {
            "verdictText": row["verdictText"],
            "plea": row["plea"],
            "guiltScore": row["guiltScore"],
            "evidence": evidence,
            "interrogation": interrogation,
        }
    )
    return _ok(data)
