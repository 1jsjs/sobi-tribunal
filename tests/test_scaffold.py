"""B301 스캐폴드 검증: health 봉투 형식 + 깨진 JSON POST가 400(422 아님)인지."""
import os

os.environ.setdefault("MOCK_AI", "1")

from fastapi.testclient import TestClient

from main import app

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
        "/api/_echo",
        content=b"{not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 400, f"expected 400, got {res.status_code}"
    body = res.json()
    assert body["success"] is False
    assert "error" in body and "code" in body["error"] and "message" in body["error"]
    # detail 배열이 새어나오면 실패
    assert "detail" not in body
