"""Small, dependency-free helpers for keeping provider credentials private."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_SENSITIVE_QUERY_KEYS = {
    "access_key",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "credential",
    "key",
    "secret",
    "signature",
    "sig",
    "token",
}
_HEADER_SECRET = re.compile(
    r"(?i)\b(authorization|x-api-key|api-key|ocp-apim-subscription-key|xi-api-key)\s*[:=]\s*(?:bearer\s+)?[^\s,;\]\}]+"
)
_INLINE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password)\b\s*[:=]\s*(['\"]?)[^\s,'\"}\]]+"
)


def sanitize_url(value: str | None) -> str | None:
    """Return an endpoint safe to put in an API response or error message."""
    if not value:
        return value
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value.split("?", 1)[0]
    if not parsed.query:
        return value
    query = [
        (key, "[redacted]" if key.lower() in _SENSITIVE_QUERY_KEYS else item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


def redact_provider_error(error: Exception | str, *secrets: str | None, limit: int = 500) -> str:
    """Make a readable provider error without echoing credentials.

    The function intentionally skips empty secrets: replacing an empty string
    would insert a redaction marker between every character of the message.
    """
    message = str(error)
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[redacted]")
    message = _HEADER_SECRET.sub(lambda match: f"{match.group(1)}: [redacted]", message)
    message = _INLINE_SECRET.sub(lambda match: f"{match.group(1)}={match.group(2)}[redacted]", message)
    message = re.sub(
        r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|secret|signature|sig)=)[^&\s]+",
        r"\1[redacted]",
        message,
    )
    return message[:limit]
