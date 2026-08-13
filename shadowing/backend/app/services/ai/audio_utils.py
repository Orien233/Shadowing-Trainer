"""Small, dependency-free helpers shared by audio provider adapters.

The adapters intentionally use :mod:`httpx` directly.  Keeping response and
format normalisation here makes the provider-specific modules easier to read
without hiding any provider request semantics.
"""

from __future__ import annotations

from typing import Any, Mapping

from app.services.ai.audio_types import RawPCMFormat


_MEDIA_TYPES_BY_EXTENSION = {
    "aac": "audio/aac",
    "flac": "audio/flac",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "opus": "audio/opus",
    "pcm": "audio/L16",
    "ulaw": "audio/basic",
    "alaw": "audio/basic",
    "wav": "audio/wav",
    "webm": "audio/webm",
}


def require_configured(*, base_url: str, api_key: str, model_name: str, provider_name: str) -> None:
    """Fail locally before a billable request when a provider is incomplete."""
    if not base_url:
        raise ValueError(f"{provider_name} base URL is not configured.")
    if not api_key:
        raise ValueError("Provider API key is not configured.")
    if not model_name:
        raise ValueError(f"{provider_name} model is not configured.")


def configuration_message(*, base_url: str, api_key: str, model_name: str, provider_name: str) -> str:
    """Validate configuration without sending a request or generating audio."""
    require_configured(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        provider_name=provider_name,
    )
    return f"{provider_name} is configured; no billable request was made."


def extension_from_format(value: Any, default: str = "mp3") -> str:
    """Infer a filename extension from common provider output-format values."""
    normalized = str(value or "").lower().replace("_", "-")
    if "riff" in normalized or "wav" in normalized:
        return "wav"
    if "webm" in normalized:
        return "webm"
    if "ogg" in normalized:
        return "ogg"
    if "opus" in normalized:
        return "opus"
    if "flac" in normalized:
        return "flac"
    if "aac" in normalized or "m4a" in normalized:
        return "aac"
    if "ulaw" in normalized or "mu-law" in normalized:
        return "ulaw"
    if "alaw" in normalized or "a-law" in normalized:
        return "alaw"
    if "pcm" in normalized or "linear16" in normalized or "raw" in normalized:
        return "pcm"
    if "mp3" in normalized or "mpeg" in normalized:
        return "mp3"
    return default


def extension_from_media_type(media_type: Any, default: str = "mp3") -> str:
    """Infer an extension from a Content-Type header."""
    normalized = str(media_type or "").split(";", 1)[0].strip().lower()
    media_map = {
        "audio/aac": "aac",
        "audio/flac": "flac",
        "audio/mpeg": "mp3",
        "audio/mp3": "mp3",
        "audio/ogg": "ogg",
        "audio/opus": "opus",
        "audio/wav": "wav",
        "audio/wave": "wav",
        "audio/webm": "webm",
    }
    return media_map.get(normalized, default)


def media_type_for_extension(extension: str, default: str = "application/octet-stream") -> str:
    return _MEDIA_TYPES_BY_EXTENSION.get(extension.lower(), default)


def response_media_type(response: Any, fallback: str) -> str:
    headers = getattr(response, "headers", None)
    if isinstance(headers, Mapping):
        value = headers.get("content-type") or headers.get("Content-Type")
        if value:
            return str(value)
    return fallback


def raw_pcm_from_config(
    config: Mapping[str, Any],
    *,
    default_sample_rate: int | None = None,
    provider_name: str,
) -> RawPCMFormat:
    """Read the explicit PCM decoding fields required by FFmpeg.

    A compatible endpoint must never be guessed from a ``.pcm`` suffix.  Known
    native APIs can supply a documented default sample rate; all other
    adapters require the user to configure it before the billable request.
    """
    sample_rate_value = config.get("pcm_sample_rate")
    if sample_rate_value is None or str(sample_rate_value).strip() == "":
        sample_rate_value = default_sample_rate
    try:
        sample_rate = int(sample_rate_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{provider_name} raw PCM requires pcm_sample_rate before synthesis."
        ) from exc
    try:
        channels = int(config.get("pcm_channels", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{provider_name} pcm_channels must be an integer.") from exc
    sample_format = str(config.get("pcm_sample_format", "s16le")).strip().lower()
    try:
        return RawPCMFormat(
            sample_rate=sample_rate,
            channels=channels,
            sample_format=sample_format,
        )
    except ValueError as exc:
        raise ValueError(f"{provider_name} raw PCM configuration is invalid: {exc}") from exc


def raw_pcm_from_azure_output_format(output_format: str, *, provider_name: str) -> RawPCMFormat | None:
    """Parse Azure's ``raw-24khz-16bit-mono-pcm`` style output names."""
    normalized = output_format.strip().lower().replace("_", "-")
    if "pcm" not in normalized or "riff" in normalized:
        return None
    import re

    rate = re.search(r"(\d+)khz", normalized)
    width = re.search(r"(16|24|32)bit", normalized)
    channels = 2 if "stereo" in normalized else 1 if "mono" in normalized else None
    if not rate or not width or channels is None:
        raise ValueError(
            f"{provider_name} raw PCM output format must state sample rate, bit depth, and mono/stereo."
        )
    sample_format = {"16": "s16le", "24": "s24le", "32": "s32le"}[width.group(1)]
    return RawPCMFormat(sample_rate=int(rate.group(1)) * 1000, channels=channels, sample_format=sample_format)


def raw_pcm_from_elevenlabs_output_format(output_format: str, *, provider_name: str) -> RawPCMFormat | None:
    """Parse ElevenLabs ``pcm_24000`` output format names."""
    normalized = output_format.strip().lower().replace("-", "_")
    if not normalized.startswith("pcm_"):
        return None
    try:
        sample_rate = int(normalized.removeprefix("pcm_").split("_", 1)[0])
    except ValueError as exc:
        raise ValueError(f"{provider_name} PCM output format must include a sample rate.") from exc
    return RawPCMFormat(sample_rate=sample_rate, channels=1, sample_format="s16le")


def as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalized_voices(value: Any) -> list[dict[str, Any]]:
    """Normalize provider voice records to the UI-friendly ``id``/``name`` form."""
    records: list[dict[str, Any]] = []
    for item in as_list(value):
        if isinstance(item, str) and item.strip():
            records.append({"id": item, "name": item})
            continue
        if not isinstance(item, dict):
            continue
        voice_id = item.get("id") or item.get("voice_id") or item.get("ShortName") or item.get("short_name") or item.get("name")
        if not voice_id:
            continue
        name = item.get("name") or item.get("display_name") or item.get("DisplayName") or voice_id
        record: dict[str, Any] = {"id": str(voice_id), "name": str(name)}
        locale = item.get("locale") or item.get("Locale") or item.get("language") or item.get("language_code")
        gender = item.get("gender") or item.get("Gender")
        if locale:
            record["locale"] = str(locale)
        if gender:
            record["gender"] = str(gender)
        records.append(record)
    return records
