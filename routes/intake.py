"""POST /api/intake — 사진 → 조서 추출. (B303에서 구현)"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["intake"])
