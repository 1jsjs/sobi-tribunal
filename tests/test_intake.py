"""B303 검증: POST /api/intake — MOCK 정상 경로, 파일 누락 400, 큰 파일 400."""
import os

os.environ.setdefault("MOCK_AI", "1")

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

# 1x1 PNG 최소 바이트
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f9f0000000049454e44ae426082"
)


def test_intake_mock_success():
    # MOCK_AI=1 → docs/03 §4 목 candidate가 dossier로 온다.
    res = client.post(
        "/api/intake",
        files={"file": ("evidence.png", PNG_BYTES, "image/png")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    data = body["data"]
    assert data["source"] == "mock"

    dossier = data["dossier"]
    assert dossier["itemName"] == "무선 이어폰"
    assert dossier["price"] == 219000
    assert dossier["category"] == "DIGITAL_APPLIANCE"
    assert dossier["usage"] is None
    assert dossier["story"] is None
    assert "photoKey" in dossier  # S3 로컬 실패 → None 이어도 키는 존재

    # 목은 1건이므로 candidates는 빈 배열
    assert data["candidates"] == []
    assert "photoUrl" in data


def test_intake_missing_file_400():
    res = client.post("/api/intake", data={})
    assert res.status_code == 400, f"expected 400, got {res.status_code}"
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_FILE"
    assert "detail" not in body  # 422 detail 배열이 새면 실패


def test_intake_too_large_400():
    big = b"\x89PNG" + b"\x00" * (5 * 1024 * 1024 + 10)
    res = client.post(
        "/api/intake",
        files={"file": ("big.png", big, "image/png")},
    )
    assert res.status_code == 400
    body = res.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_FILE"


def test_intake_bad_mime_400():
    res = client.post(
        "/api/intake",
        files={"file": ("doc.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "INVALID_FILE"
