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


# ── B309: 정크 품목명 필터 (_clean_candidate 유닛) ──
from services.intake_service import _clean_candidate  # noqa: E402


def _cand(**over):
    base = {
        "itemName": "무선 이어폰",
        "price": 219000,
        "boughtAt": "2026-08-14",
        "merchant": "쿠팡",
        "category": "DIGITAL_APPLIANCE",
    }
    base.update(over)
    return base


def test_clean_rejects_unknown_name():
    assert _clean_candidate(_cand(itemName="알 수 없음")) is None


def test_clean_rejects_unknown_name_no_space_and_trailing():
    assert _clean_candidate(_cand(itemName="알수없음  ")) is None


def test_clean_rejects_unknown_variants():
    for junk in ["미상", "없음", "unknown", "N/A", "-", "확인 불가", "물품", "상품", "UNKNOWN"]:
        assert _clean_candidate(_cand(itemName=junk)) is None, junk


def test_clean_passes_normal_candidate():
    c = _clean_candidate(_cand())
    assert c is not None
    assert c["itemName"] == "무선 이어폰"
    assert c["price"] == 219000


def test_clean_rejects_zero_price_and_null_merchant_and_date():
    # 아무 정보도 못 읽은 케이스
    assert _clean_candidate(_cand(price=0, merchant=None, boughtAt=None)) is None


def test_clean_passes_zero_price_when_merchant_present():
    c = _clean_candidate(_cand(price=0, merchant="쿠팡", boughtAt=None))
    assert c is not None
    assert c["price"] == 0
    assert c["merchant"] == "쿠팡"


def test_clean_passes_zero_price_when_date_present():
    c = _clean_candidate(_cand(price=0, merchant=None, boughtAt="2026-08-14"))
    assert c is not None
