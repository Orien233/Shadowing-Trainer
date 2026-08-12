"""Canonical language tags used by the UI and learning workflows.

The catalog deliberately contains the product's supported languages rather than
accepting arbitrary strings.  This gives persisted preferences and materials a
stable BCP-47 representation while leaving the adapters free to translate a
canonical tag into a provider-specific parameter later.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageDescriptor:
    code: str
    english_name: str
    native_name: str


LANGUAGE_CATALOG: tuple[LanguageDescriptor, ...] = (
    LanguageDescriptor("en", "English", "English"),
    LanguageDescriptor("zh-CN", "Chinese (Simplified)", "简体中文"),
    LanguageDescriptor("zh-TW", "Chinese (Traditional)", "繁體中文"),
    LanguageDescriptor("ja", "Japanese", "日本語"),
    LanguageDescriptor("ko", "Korean", "한국어"),
    LanguageDescriptor("es", "Spanish", "Español"),
    LanguageDescriptor("fr", "French", "Français"),
    LanguageDescriptor("de", "German", "Deutsch"),
    LanguageDescriptor("it", "Italian", "Italiano"),
    LanguageDescriptor("pt", "Portuguese", "Português"),
    LanguageDescriptor("ru", "Russian", "Русский"),
    LanguageDescriptor("ar", "Arabic", "العربية"),
)

SUPPORTED_LANGUAGE_CODES: tuple[str, ...] = tuple(item.code for item in LANGUAGE_CATALOG)
SUPPORTED_UI_LOCALES: tuple[str, ...] = ("zh-CN", "en-US")
_CANONICAL_BY_FOLDED_TAG = {item.code.casefold(): item.code for item in LANGUAGE_CATALOG}
_CANONICAL_BY_FOLDED_TAG.update({
    "zh_cn": "zh-CN",
    "zh_tw": "zh-TW",
})

ASR_AUTO_LANGUAGE = "auto"
UNDETERMINED_LANGUAGE = "und"


class LanguageValidationError(ValueError):
    """Raised when a language tag is not allowed for a given field."""


def normalize_ui_locale(value: str | None) -> str:
    """Normalize the smaller set of locales for which the UI has a catalog."""
    candidate = str(value or "").strip().replace("_", "-").casefold()
    aliases = {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "en": "en-US",
        "en-us": "en-US",
    }
    normalized = aliases.get(candidate)
    if normalized:
        return normalized
    supported = ", ".join(SUPPORTED_UI_LOCALES)
    raise LanguageValidationError(f"Unsupported UI locale '{value}'. Supported: {supported}.")


def normalize_language_tag(
    value: str | None,
    *,
    allow_auto: bool = False,
    allow_undetermined: bool = False,
) -> str:
    """Return the catalog's canonical BCP-47 tag.

    ``auto`` is only an ASR instruction meaning *ask the provider to detect the
    spoken language*.  ``und`` means that a language is genuinely unknown; it
    is data, not an ASR instruction.  Callers must opt in to each explicitly.
    """
    candidate = str(value or "").strip()
    if not candidate:
        raise LanguageValidationError("A language code is required.")

    folded = candidate.casefold().replace("_", "-")
    if folded == ASR_AUTO_LANGUAGE:
        if allow_auto:
            return ASR_AUTO_LANGUAGE
        raise LanguageValidationError("'auto' is only valid for ASR language detection.")
    if folded == UNDETERMINED_LANGUAGE:
        if allow_undetermined:
            return UNDETERMINED_LANGUAGE
        raise LanguageValidationError("'und' is only valid when the content language is unknown.")

    normalized = _CANONICAL_BY_FOLDED_TAG.get(folded)
    if normalized:
        return normalized
    supported = ", ".join(SUPPORTED_LANGUAGE_CODES)
    raise LanguageValidationError(f"Unsupported language code '{candidate}'. Supported: {supported}.")


def language_catalog_payload() -> list[dict[str, str]]:
    return [
        {
            "code": item.code,
            "english_name": item.english_name,
            "native_name": item.native_name,
        }
        for item in LANGUAGE_CATALOG
    ]
