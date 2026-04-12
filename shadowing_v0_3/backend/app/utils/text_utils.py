import re
from difflib import SequenceMatcher


def normalize_text(text: str) -> str:
    cleaned = text.lower().strip()
    cleaned = re.sub(r"[^\w\s']", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def token_recall(reference: str, hypothesis: str) -> float:
    ref_tokens = normalize_text(reference).split()
    hyp_tokens = normalize_text(hypothesis).split()
    if not ref_tokens:
        return 0.0
    matched = sum(1 for token in ref_tokens if token in hyp_tokens)
    return matched / max(len(ref_tokens), 1)


def similarity(reference: str, hypothesis: str) -> float:
    return SequenceMatcher(None, normalize_text(reference), normalize_text(hypothesis)).ratio()


def clamp_score(value: float) -> int:
    return int(max(0, min(100, round(value))))
