"""B302/B302b 검증: 파싱 함수 + 제공자 분기 (LLM 실호출 없음)."""
import os

os.environ.setdefault("MOCK_AI", "1")

import pytest

from services import llm_service as llm


def test_extract_text_skips_thinking_block():
    # Sonnet 5가 첫 블록으로 thinking을 반환하는 상황. text 블록을 찾아야 한다.
    body = {
        "content": [
            {"type": "thinking", "thinking": "음, 이건 이어폰이군..."},
            {"type": "text", "text": "판결문 원고입니다"},
        ]
    }
    assert llm._extract_text(body) == "판결문 원고입니다"


def test_extract_text_raises_when_no_text_block():
    body = {"content": [{"type": "thinking", "thinking": "..."}]}
    with pytest.raises(ValueError):
        llm._extract_text(body)


def test_extract_json_with_markdown_fence():
    raw = "설명 한 줄\n```json\n{\"itemName\": \"무선 이어폰\", \"price\": 219000}\n```\n끝"
    data = llm.extract_json(raw)
    assert data["itemName"] == "무선 이어폰"
    assert data["price"] == 219000


def test_extract_json_bare_object():
    raw = '{"candidates": [{"itemName": "브로콜리"}]}'
    data = llm.extract_json(raw)
    assert data["candidates"][0]["itemName"] == "브로콜리"


def test_extract_json_invalid_raises():
    with pytest.raises(ValueError):
        llm.extract_json("여기엔 JSON이 없소")


def test_mock_ai_raises_mockaierror():
    # MOCK_AI=1이면 call_text/call_vision은 호출자에게 MockAIError를 던진다.
    with pytest.raises(llm.MockAIError):
        llm.call_text("system", "user")
    with pytest.raises(llm.MockAIError):
        llm.call_vision("system", "user", b"\x00\x01", "image/jpeg")


def test_mock_wins_over_gemini(monkeypatch):
    # MOCK_AI=1 + AI_PROVIDER=gemini여도 mock이 우선 → MockAIError.
    monkeypatch.setenv("MOCK_AI", "1")
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    assert llm.provider() == "mock"
    with pytest.raises(llm.MockAIError):
        llm.call_text("system", "user")
    with pytest.raises(llm.MockAIError):
        llm.call_vision("system", "user", b"\x00\x01", "image/jpeg")


def test_gemini_without_api_key_raises_runtimeerror(monkeypatch):
    # AI_PROVIDER=gemini + GOOGLE_API_KEY 미설정 → 실호출 전에 RuntimeError.
    monkeypatch.delenv("MOCK_AI", raising=False)
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert llm.provider() == "gemini"
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY not set"):
        llm.call_text("system", "user")
    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY not set"):
        llm.call_vision("system", "user", b"\x00\x01", "image/jpeg")
