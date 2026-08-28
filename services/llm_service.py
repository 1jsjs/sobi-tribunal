"""LLM 공통 서비스 (텍스트 + 비전) — 제공자 분기.

제공자(tech-constraints §AI 제공자 분기·§5 검증 사다리):
- `mock`    : pytest 기본. MockAIError를 던져 각 서비스가 자기 목 응답을 쓰게 한다.
              MOCK_AI=1이면 AI_PROVIDER 값과 무관하게 무조건 mock이다.
- `bedrock` : 기본(서버). Claude Sonnet 5 invoke_model. 이 경로 코드는 B302 그대로.
- `gemini`  : 로컬 검증 전용(google-genai). 서버·데모엔 절대 올리지 않는다.
              같은 프롬프트가 같은 extract_json을 타야 로컬 검증이 Bedrock 프롬프트
              검증이 되므로 JSON 모드·response_schema를 쓰지 않는다.

함정 대응:
- §1: 응답 content 배열에서 type=="text" 블록만 골라 쓴다. content[0] 직접 접근 금지.
       Sonnet 5는 첫 블록으로 thinking을 줄 수 있다. max_tokens는 2048 이상.
- §2: 요청에 샘플링 파라미터(온도·상위확률)를 넣지 않는다. 넣으면 ValidationException.
- §5: 로컬 통과(mock/gemini)를 Bedrock 검증으로 치지 않는다.

region_name·자격증명은 서버 env(AWS_DEFAULT_REGION 등)에서 온다. 하드코딩 금지.
GOOGLE_API_KEY는 로컬 셸 env로만 주입한다(코드·리포 커밋 금지).
"""
import base64
import json
import logging
import os

logger = logging.getLogger("bedrock")

MODEL_ID = "global.anthropic.claude-sonnet-5"
ANTHROPIC_VERSION = "bedrock-2023-05-31"
MAX_TOKENS = 4096  # 2048은 8문 한국어 재작성이 잘려 JSON이 깨짐 (서버 실측)

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"


class MockAIError(Exception):
    """MOCK_AI=1(또는 mock 제공자)일 때 던진다. 호출자가 자기 목 응답으로 폴백하라는 신호."""


def _is_mock() -> bool:
    return os.environ.get("MOCK_AI") == "1"


def provider() -> str:
    """활성 AI 제공자. MOCK_AI=1이면 무조건 mock(기존 동작 보존)."""
    if _is_mock():
        return "mock"
    return os.environ.get("AI_PROVIDER", "bedrock")


def _gemini_model() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def _gemini_client():
    """google-genai 클라이언트. GOOGLE_API_KEY 없으면 즉시 RuntimeError."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")
    from google import genai

    return genai.Client(api_key=api_key)


def _gemini_text(system: str, user: str) -> str:
    """Gemini 텍스트 호출. JSON 모드·response_schema 미사용(같은 프롬프트→같은 파싱)."""
    client = _gemini_client()  # GOOGLE_API_KEY 없으면 여기서 RuntimeError
    from google.genai import types

    try:
        resp = client.models.generate_content(
            model=_gemini_model(),
            contents=user,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return resp.text
    except Exception as e:
        logger.error("LLM 호출 실패(gemini): %s", e)
        raise


def _gemini_vision(system: str, user: str, image_bytes: bytes, media_type: str) -> str:
    """Gemini 비전 호출(이미지 파트 + 텍스트). JSON 모드 미사용."""
    client = _gemini_client()  # GOOGLE_API_KEY 없으면 여기서 RuntimeError
    from google.genai import types

    try:
        resp = client.models.generate_content(
            model=_gemini_model(),
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=media_type),
                user,
            ],
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return resp.text
    except Exception as e:
        logger.error("LLM 호출 실패(gemini): %s", e)
        raise


# bedrock-runtime 클라이언트 — 모듈 전역 lazy 싱글톤 (커넥션 재사용).
# 로컬(자격증명 없음)에서 임포트만으로 예외가 나면 안 되므로 첫 호출 시점에 생성한다.
_bedrock_client = None


def _client():
    # region_name 지정 금지 — 서버 env(AWS_DEFAULT_REGION)를 따른다.
    global _bedrock_client
    if _bedrock_client is None:
        import boto3

        _bedrock_client = boto3.client("bedrock-runtime")
    return _bedrock_client


def _extract_text(response_body: dict) -> str:
    """content 배열에서 type=='text'인 첫 블록의 text를 반환. content[0] 직접 접근 금지."""
    for block in response_body.get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text", "")
    raise ValueError("Bedrock 응답에 text 블록이 없소")


def _invoke(body: dict) -> str:
    client = _client()
    resp = client.invoke_model(modelId=MODEL_ID, body=json.dumps(body))
    payload = json.loads(resp["body"].read())
    return _extract_text(payload)


def _maybe_disable_thinking(body: dict, use_thinking: bool) -> dict:
    """use_thinking=False면 bedrock body에 thinking 비활성 블록을 추가한다.

    ⚠️ temperature 사건과 같은 클래스의 파라미터다 — 모델이 거부하면 조용히 폴백(AI 실종).
    로컬로 검증 불가. 배포 후 app.log 실측 필요(tech-constraints §5 사다리 ③).
    """
    if not use_thinking:
        body["thinking"] = {"type": "disabled"}
    return body


def call_text(system: str, user: str, use_thinking: bool = True) -> str:
    """텍스트 프롬프트 호출. 실패 시 로깅 후 예외 재발생(폴백은 호출자 몫).

    use_thinking=False → bedrock에 thinking 비활성(스타일링·비전용). gemini 경로는 무시.
    """
    p = provider()
    if p == "mock":
        raise MockAIError("mock 제공자: call_text 미호출")
    if p == "gemini":
        return _gemini_text(system, user)

    body = {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [{"role": "user", "content": [{"type": "text", "text": user}]}],
    }
    body = _maybe_disable_thinking(body, use_thinking)
    try:
        return _invoke(body)
    except Exception as e:
        logger.error("Bedrock 호출 실패: %s", e)
        raise


def call_vision(
    system: str, user: str, image_bytes: bytes, media_type: str, use_thinking: bool = True
) -> str:
    """비전 프롬프트 호출(이미지 1장 base64 첨부). 실패 시 로깅 후 예외 재발생.

    use_thinking=False → bedrock에 thinking 비활성. gemini 경로는 무시.
    """
    p = provider()
    if p == "mock":
        raise MockAIError("mock 제공자: call_vision 미호출")
    if p == "gemini":
        return _gemini_vision(system, user, image_bytes, media_type)

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    body = {
        "anthropic_version": ANTHROPIC_VERSION,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": user},
                ],
            }
        ],
    }
    body = _maybe_disable_thinking(body, use_thinking)
    try:
        return _invoke(body)
    except Exception as e:
        logger.error("Bedrock 호출 실패: %s", e)
        raise


def extract_json(raw: str) -> dict:
    """첫 '{'부터 마지막 '}'까지 잘라 json.loads. 실패 시 ValueError.

    마크다운 펜스(```json ... ```)나 앞뒤 설명이 섞여 있어도 통과시킨다.
    """
    if raw is None:
        raise ValueError("빈 응답")
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("응답에서 JSON 객체를 찾지 못했소")
    snippet = raw[start : end + 1]
    try:
        return json.loads(snippet, strict=False)  # Claude가 문자열 안에 실제 개행을 넣음 (서버 실측)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}") from e
