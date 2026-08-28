"""POST /api/trial/start, POST /api/trial/verdict. (B304/B305에서 구현)"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/trial", tags=["trial"])
