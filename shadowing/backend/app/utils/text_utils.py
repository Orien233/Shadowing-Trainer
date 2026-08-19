import re
from difflib import SequenceMatcher


def normalize_text(text: str) -> str:
    cleaned = text.lower().strip()
    cleaned = re.sub(r"[^\w\s']", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def similarity(reference: str, hypothesis: str) -> float:
    return SequenceMatcher(None, normalize_text(reference), normalize_text(hypothesis)).ratio()


def clamp_score(value: float) -> int:
    return int(max(0, min(100, round(value))))
