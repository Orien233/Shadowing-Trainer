import asyncio

from app.services import translation_service


class RecordingProvider:
    def __init__(self, response: dict[str, object] | None = None) -> None:
        self.response = response or {"translation": "translated"}
        self.calls: list[dict[str, object]] = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_translate_sentence_uses_catalog_languages_in_both_prompts():
    provider = RecordingProvider({"translation": "\ud55c\uad6d\uc5b4 \ubc88\uc5ed"})

    result = asyncio.run(
        translation_service.translate_sentence(
            "\u3053\u3093\u306b\u3061\u306f",
            source_language="ja",
            target_language="ko",
            provider=provider,
        )
    )

    assert result == "\ud55c\uad6d\uc5b4 \ubc88\uc5ed"
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert "Japanese (ja)" in call["system_prompt"]
    assert "Korean (ko)" in call["system_prompt"]
    assert "Japanese (ja)" in call["user_prompt"]
    assert "Korean (ko)" in call["user_prompt"]
    assert "Simplified Chinese" not in call["system_prompt"]


def test_same_language_translation_returns_original_without_provider_call():
    provider = RecordingProvider()

    result = asyncio.run(
        translation_service.translate_sentence(
            "  Preserve this exactly.  ",
            source_language="fr",
            target_language="fr",
            provider=provider,
        )
    )

    assert result == "  Preserve this exactly.  "
    assert provider.calls == []


def test_batch_same_language_returns_originals_without_resolving_provider(monkeypatch):
    def fail_provider_resolution(*_args, **_kwargs):
        raise AssertionError("Provider resolution must be skipped for same-language translation")

    monkeypatch.setattr(translation_service, "get_provider", fail_provider_resolution)

    result = asyncio.run(
        translation_service.translate_sentences(
            ["  one  ", "two"], source_language="de", target_language="de"
        )
    )

    assert result == ["  one  ", "two"]


def test_failed_batch_translation_returns_blank_not_diagnostic_text():
    class FailingProvider:
        def generate_json(self, **_kwargs):
            raise ValueError("malformed provider response")

    result = asyncio.run(
        translation_service._translate_with_fallback(
            "Hello", FailingProvider(), "en", "es"
        )
    )

    assert result == ""


def test_missing_provider_does_not_fail_the_material_or_tts_batch(monkeypatch):
    monkeypatch.setattr(
        translation_service,
        "require_provider_capabilities",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("No default LLM provider is configured")
        ),
    )

    result = asyncio.run(
        translation_service.translate_sentences(
            ["Hello.", "Goodbye."],
            source_language="en",
            target_language="zh-CN",
        )
    )

    assert result == ["", ""]
