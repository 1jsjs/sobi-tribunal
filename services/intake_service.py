"""기소 — 사진 → 조서 (비전 추출 + S3 업로드).

- Bedrock 비전 호출(docs/03 §1 프롬프트 그대로) → candidates 파싱·검증
- MOCK_AI=1(또는 mock 제공자) → docs/03 §4의 목 candidates
- 비전 파싱 실패 → candidates: [] (호출자가 200으로 수동 입력 안내). 500 금지.
- S3 업로드 실패 → photoKey/photoUrl null로 계속. 예외 전파 금지.
"""
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from constants import CATEGORIES
from services import llm_service as llm

logger = logging.getLogger("bedrock")

# ── S3 설정 (tech-constraints: 버킷/엔드포인트 고정, region 하드코딩 금지) ──
S3_BUCKET = "hackathon-e1-t07-docs"
S3_ENDPOINT_URL = "https://s3.eu-west-2.amazonaws.com"
PRESIGN_TTL = 12 * 60 * 60  # 12시간

# s3 클라이언트 — 모듈 전역 lazy 싱글톤 (커넥션 재사용).
# 로컬(자격증명 없음)에서 임포트만으로 예외가 나면 안 되므로 첫 호출 시점에 생성한다.
_s3_client = None


def _s3():
    global _s3_client
    if _s3_client is None:
        import boto3

        _s3_client = boto3.client("s3", endpoint_url=S3_ENDPOINT_URL)
    return _s3_client

# ── 비전 프롬프트 (docs/03 §1 그대로) ────────────────────────────────
VISION_SYSTEM = """너는 소비 재판소의 서기다. 증거 사진에서 구매 정보를 추출해 조서를 작성한다.
사진은 셋 중 하나다: ①결제내역/주문내역 화면 캡처 ②종이 영수증 ③가격이 보이는 제품 사진.
반드시 아래 JSON 하나만 출력한다. 설명·마크다운 금지.
{"candidates": [{"itemName": "품목명(한국어, 15자 이내)", "price": 숫자(원),
  "boughtAt": "YYYY-MM-DD" 또는 null, "merchant": "가맹점/브랜드" 또는 null,
  "category": "FASHION_BEAUTY|FOOD_DINING|DIGITAL_APPLIANCE|HOBBY_LEISURE|LIVING_GROCERY|OTHER"}]}
규칙:
- 결제내역 캡처에 거래가 여러 건이면 보이는 건을 전부 candidates에 담는다(최대 8건).
- 영수증·제품 사진이면 대표 1건만. 영수증의 개별 품목은 합치지 말고 총액 기준 1건.
- 금액이 안 보이면 price는 0. 확실치 않은 필드는 null. 지어내지 않는다.
- 품목명은 상품 코드가 아니라 사람이 알아보는 이름으로."""

VISION_USER = "조서를 작성하라."

MEDIA_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

# docs/03 §4 목 candidates
MOCK_CANDIDATES = [
    {
        "itemName": "무선 이어폰",
        "price": 219000,
        "boughtAt": "2026-08-14",
        "merchant": "쿠팡",
        "category": "DIGITAL_APPLIANCE",
    }
]


def _clean_candidate(raw) -> dict | None:
    """candidate 1건을 계약 규칙에 맞게 정규화. 못 쓰면 None."""
    if not isinstance(raw, dict):
        return None

    name = raw.get("itemName")
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()[:15]  # 15자 잘라내기

    # price 정수화, 음수→0
    price = raw.get("price", 0)
    try:
        price = int(round(float(price)))
    except (TypeError, ValueError):
        price = 0
    if price < 0:
        price = 0

    bought_at = raw.get("boughtAt")
    if not isinstance(bought_at, str) or not bought_at.strip():
        bought_at = None

    merchant = raw.get("merchant")
    if not isinstance(merchant, str) or not merchant.strip():
        merchant = None
    else:
        merchant = merchant.strip()

    category = raw.get("category")
    if category not in CATEGORIES:  # 6종 외 → OTHER
        category = "OTHER"

    return {
        "itemName": name,
        "price": price,
        "boughtAt": bought_at,
        "merchant": merchant,
        "category": category,
    }


def _extract_candidates(image_bytes: bytes, media_type: str):
    """비전 호출 → candidates 리스트. (candidates, source) 반환.

    실패(파싱 불가·AI 오류)해도 예외를 던지지 않고 ([], source)로 돌려준다.
    """
    try:
        raw = llm.call_vision(
            VISION_SYSTEM, VISION_USER, image_bytes, media_type, use_thinking=False
        )
        source = "bedrock"
    except llm.MockAIError:
        cleaned = [c for c in (_clean_candidate(x) for x in MOCK_CANDIDATES) if c]
        return cleaned, "mock"
    except Exception as e:
        logger.error("Bedrock 호출 실패: %s", e)
        return [], "bedrock"

    try:
        data = llm.extract_json(raw)
        items = data.get("candidates", [])
        if not isinstance(items, list):
            return [], source
        cleaned = [c for c in (_clean_candidate(x) for x in items[:8]) if c]
        return cleaned, source
    except Exception as e:
        logger.error("Bedrock 호출 실패: 조서 파싱 실패 %s", e)
        return [], source


def _upload_to_s3(image_bytes: bytes, media_type: str):
    """S3 업로드 + presigned GET(12h). 실패 시 (None, None). 예외 전파 금지."""
    ext = MEDIA_TYPES.get(media_type, "jpg")
    key = f"evidence/{uuid.uuid4().hex}.{ext}"
    try:
        s3 = _s3()
        s3.put_object(
            Bucket=S3_BUCKET, Key=key, Body=image_bytes, ContentType=media_type
        )
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key},
            ExpiresIn=PRESIGN_TTL,
        )
        return key, url
    except Exception as e:
        logger.error("S3 업로드 실패: %s", e)
        return None, None


def process_intake(image_bytes: bytes, media_type: str) -> dict:
    """사진 1장 → intake 응답 data (api-contract §POST /api/intake).

    {"dossier": {...}, "candidates": [...], "photoUrl": ..., "source": ...}

    비전 추출과 S3 업로드는 서로 독립적이므로 동시에 실행한다(지연 단축).
    각 함수가 실패를 자체 흡수하므로(([],src)·(None,None)) 병렬로 돌려도 동작 불변.
    """
    with ThreadPoolExecutor(max_workers=2) as ex:
        vision_future = ex.submit(_extract_candidates, image_bytes, media_type)
        s3_future = ex.submit(_upload_to_s3, image_bytes, media_type)
        candidates, source = vision_future.result()
        photo_key, photo_url = s3_future.result()

    if candidates:
        first = candidates[0]
    else:
        # 비전 실패: 빈 조서(프론트가 수동 입력으로 채운다)
        first = {
            "itemName": "",
            "price": 0,
            "boughtAt": None,
            "merchant": None,
            "category": "OTHER",
        }

    dossier = {
        "itemName": first["itemName"],
        "price": first["price"],
        "boughtAt": first["boughtAt"],
        "merchant": first["merchant"],
        "category": first["category"],
        "usage": None,
        "story": None,
        "photoKey": photo_key,
    }

    # candidates: 2건 이상일 때만 전체 배열, 아니면 []
    out_candidates = candidates if len(candidates) >= 2 else []

    return {
        "dossier": dossier,
        "candidates": out_candidates,
        "photoUrl": photo_url,
        "source": source,
    }
