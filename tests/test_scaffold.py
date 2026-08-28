"""B301 스캐폴드 검증: health 봉투 형식 + 깨진 JSON POST가 400(422 아님)인지."""
import os

os.environ.setdefault("MOCK_AI", "1")

from fastapi.testclient import TestClient

from main import app, ok


# 테스트 전용 라우트: typed body로 FastAPI 선검증을 일부러 유발해
# 전역 422→400 핸들러를 검증한다. (프로덕션 라우트에선 금지 패턴 — tech-constraints §3)
@app.post("/api/_test_echo")
def _test_echo(body: dict):
    return ok(body)


# import 시점에 이미 등록된 "/" StaticFiles 마운트가 뒤에 추가된 라우트를 가리므로
# 테스트 라우트를 라우팅 목록 맨 앞으로 옮긴다 (테스트 전용 조치).
app.router.routes.insert(0, app.router.routes.pop())

client = TestClient(app)


def test_health_envelope():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"]["message"] == "법정은 열려 있다"


def test_broken_json_returns_400_not_422():
    # 본문을 파싱하는 라우트에 깨진 JSON을 던진다 → 선검증 422가 아니라 400 봉투여야 한다.
    res = client.post(
        "/api/_test_echo",
        content=b"{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 400, f"expected 400, got {res.status_code}"
    body = res.json()
    assert body["success"] is False
    assert "error" in body and "code" in body["error"] and "message" in body["error"]
    # detail 배열이 새어나오면 실패
    assert "detail" not in body


def test_schema_mismatch_returns_400_not_422():
    # 유효한 JSON이지만 타입이 안 맞는 경우(dict 자리에 배열) — 실전에서 가장 흔한 422 경로
    res = client.post("/api/_test_echo", json=[1, 2, 3])
    assert res.status_code == 400
    body = res.json()
    assert body["success"] is False and "detail" not in body


def test_unknown_api_path_returns_envelope_404():
    # 미정의 /api 경로가 정적 마운트로 새지 않고 404 봉투로 잡히는지
    res = client.get("/api/no-such-thing")
    assert res.status_code == 404
    body = res.json()
    assert body["success"] is False and body["error"]["code"] == "NOT_FOUND"
