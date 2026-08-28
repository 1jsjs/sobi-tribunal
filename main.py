"""소비 재판소 — FastAPI 앱 진입점.

- 응답 봉투 헬퍼 ok()/fail()
- 전역 RequestValidationError 핸들러: 422 → 400 + 봉투 (detail 배열 노출 금지)
- routes/ 3개 라우터 include
- static/ 서빙 (/, /static)
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from db import init_db
from routes import intake, trial, records

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # 기동 시 DB 파일/테이블/인덱스 보장
    yield


app = FastAPI(title="소비 재판소", docs_url=None, redoc_url=None, lifespan=lifespan)


# ── 응답 봉투 헬퍼 ──────────────────────────────────────────────────
def ok(data, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content={"success": True, "data": data})


def fail(code: str, message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


# ── 전역 핸들러: FastAPI 선검증 422를 400 봉투로 변환 (detail 배열 숨김) ──
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return fail("BAD_REQUEST", "요청 형식이 올바르지 않소.", status=400)


# ── 정적 파일 no-cache: 배포 후 수정본이 참가자 브라우저 캐시에 막히는 사고 방지
# (etag 재검증이라 304로 여전히 빠르다. 로컬 검증에서 실제로 두 번 당했다.)
@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache"
    return response


# ── 헬스 체크 (고정 경로) ───────────────────────────────────────────
@app.get("/api/health")
def health():
    return ok({"message": "법정은 열려 있다"})


# ── 라우터 include (경로 변수 라우트는 각 라우터 내부에서 뒤로) ───────
app.include_router(intake.router)
app.include_router(trial.router)
app.include_router(records.router)


# ── /api 미정의 경로: 정적 마운트로 새지 않게 404 봉투로 잡는다 ───────
# (라우터 include 뒤에 등록 — 정의된 /api 라우트가 항상 먼저 매칭된다)
@app.api_route("/api/{_rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def api_not_found(_rest: str):
    return fail("NOT_FOUND", "그런 절차는 본 법정에 없소.", status=404)


# ── static 서빙: /static 마운트 + 루트에서 index.html ────────────────
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="root")
