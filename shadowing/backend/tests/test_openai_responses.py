from __future__ import annotations

import pytest

from app.services.ai.llm.openai_responses import OpenAIResponsesLLMProvider


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_responses_text_uses_native_endpoint_and_output_blocks(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return _Response({
            "output": [
                {"type": "reasoning", "summary": []},
                {"type": "message", "content": [
                    {"type": "output_text", "text": "Hello "},
                    {"type": "output_text", "text": "world"},
                ]},
            ]
        })

    monkeypatch.setattr("app.services.ai.llm.openai_responses.provider_http.post", fake_post)
    provider = OpenAIResponsesLLMProvider(
        base_url="https://api.example.test/v1/",
        api_key="secret",
        model_name="gpt-test",
    )

    result = provider.generate_text(
        system_prompt="Follow the instructions.",
        user_prompt="Say hello.",
        temperature=0.2,
    )

    assert result == "Hello world"
    assert captured["url"] == "https://api.example.test/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["json"] == {
        "model": "gpt-test",
        "instructions": "Follow the instructions.",
        "input": "Say hello.",
        "temperature": 0.2,
        "store": False,
    }


def test_responses_structured_output_uses_text_format(monkeypatch):
    captured = {}

    def fake_post(_url, **kwargs):
        captured["payload"] = kwargs["json"]
        return _Response({"output_text": '{"title":"Trip"}'})

    monkeypatch.setattr("app.services.ai.llm.openai_responses.provider_http.post", fake_post)
    provider = OpenAIResponsesLLMProvider(
        base_url="https://api.example.test/v1",
        api_key="secret",
        model_name="gpt-test",
        extra_config={"json_mode": "json_schema", "json_schema_name": "practice"},
    )
    schema = {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
        "additionalProperties": False,
    }

    assert provider.generate_json(
        system_prompt="Return a practice.",
        user_prompt="Travel",
        json_schema=schema,
    ) == {"title": "Trip"}
    assert captured["payload"]["text"] == {
        "format": {
            "type": "json_schema",
            "name": "practice",
            "schema": schema,
            "strict": True,
        }
    }
    assert "messages" not in captured["payload"]
    assert "response_format" not in captured["payload"]


def test_responses_json_without_schema_uses_json_object(monkeypatch):
    captured = {}

    def fake_post(_url, **kwargs):
        captured["payload"] = kwargs["json"]
        return _Response({"output": [{"type": "message", "content": [{"type": "output_text", "text": '{"translation":"你好"}'}]}]})

    monkeypatch.setattr("app.services.ai.llm.openai_responses.provider_http.post", fake_post)
    provider = OpenAIResponsesLLMProvider(
        base_url="https://api.example.test/v1",
        api_key="secret",
        model_name="gpt-test",
        extra_config={"json_mode": "json_schema"},
    )

    assert provider.generate_json(system_prompt="Translate.", user_prompt="Hello") == {"translation": "你好"}
    assert captured["payload"]["text"] == {"format": {"type": "json_object"}}


def test_responses_refusal_is_reported_as_an_error(monkeypatch):
    monkeypatch.setattr(
        "app.services.ai.llm.openai_responses.provider_http.post",
        lambda *_args, **_kwargs: _Response({"output": [{"type": "message", "content": [{"type": "refusal", "refusal": "No."}]}]}),
    )
    provider = OpenAIResponsesLLMProvider(
        base_url="https://api.example.test/v1",
        api_key="secret",
        model_name="gpt-test",
    )

    with pytest.raises(ValueError, match="refused"):
        provider.generate_text(system_prompt="", user_prompt="Hello")


def test_responses_connection_check_uses_models_metadata(monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured.update(url=url, **kwargs)
        return _Response({"data": []})

    monkeypatch.setattr("app.services.ai.llm.openai_responses.provider_http.get", fake_get)
    monkeypatch.setattr(
        "app.services.ai.llm.openai_responses.provider_http.post",
        lambda *_args, **_kwargs: pytest.fail("connection check must not create a response"),
    )
    provider = OpenAIResponsesLLMProvider(
        base_url="https://api.example.test/v1",
        api_key="secret",
        model_name="gpt-test",
    )

    assert "metadata endpoint" in provider.test_connection()
    assert captured["url"] == "https://api.example.test/v1/models"
