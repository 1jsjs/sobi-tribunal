"""GET /api/records, GET /api/records/{id}. (B305에서 구현)

주의: /api/records/{id} 라우트는 /api/records 보다 뒤에 등록한다.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["records"])
