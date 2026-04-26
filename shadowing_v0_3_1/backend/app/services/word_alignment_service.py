from __future__ import annotations

import difflib
import re
import string

from dataclasses import dataclass, field
from typing import Any, Literal


AlignmentOperation = Literal["equal", "minor", "substitution", "deletion", "insertion"]

_TOKEN_PATTERN = re.compile(r"\S+")
_APOSTROPHES = {"\u2018": "'", "\u2019": "'", "\u201b": "'", "\u2032": "'"}
_PUNCTUATION_TO_SPACE = str.maketrans({char: " " for char in string.punctuation if char != "'"})

_CONTRACTIONS: dict[str, str] = {
    "aint": "is not",
    "aren't": "are not",
    "arent": "are not",
    "can't": "cannot",
    "cant": "cannot",
    "couldn't": "could not",
    "couldnt": "could not",
    "didn't": "did not",
    "didnt": "did not",
    "doesn't": "does not",
    "doesnt": "does not",
    "don't": "do not",
    "dont": "do not",
    "hadn't": "had not",
    "hadnt": "had not",
    "hasn't": "has not",
    "hasnt": "has not",
    "haven't": "have not",
    "havent": "have not",
    "he'd": "he would",
    "he'll": "he will",
    "he's": "he is",
    "i'd": "i would",
    "i'll": "i will",
    "i'm": "i am",
    "im": "i am",
    "i've": "i have",
    "isn't": "is not",
    "isnt": "is not",
    "it's": "it is",
    "its": "it is",
    "let's": "let us",
    "lets": "let us",
    "mightn't": "might not",
    "mightnt": "might not",
    "mustn't": "must not",
    "mustnt": "must not",
    "shan't": "shall not",
    "shant": "shall not",
    "she'd": "she would",
    "she'll": "she will",
    "she's": "she is",
    "shouldn't": "should not",
    "shouldnt": "should not",
    "that's": "that is",
    "theres": "there is",
    "there's": "there is",
    "they'd": "they would",
    "they'll": "they will",
    "they're": "they are",
    "theyve": "they have",
    "they've": "they have",
    "wasn't": "was not",
    "wasnt": "was not",
    "we'd": "we would",
    "we'll": "we will",
    "we're": "we are",
    "weve": "we have",
    "we've": "we have",
    "weren't": "were not",
    "werent": "were not",
    "what's": "what is",
    "whats": "what is",
    "won't": "will not",
    "wont": "will not",
    "wouldn't": "would not",
    "wouldnt": "would not",
    "you'd": "you would",
    "you'll": "you will",
    "you're": "you are",
    "youre": "you are",
    "youve": "you have",
    "you've": "you have",
}

_SINGLE_FILLERS = {
    "ah",
    "eh",
    "er",
    "erm",
    "hmm",
    "like",
    "mhm",
    "mm",
    "uh",
    "um",
}
_FILLER_PHRASES = {("you", "know")}


@dataclass
class _Token:
    index: int
    text: str
    normalized: str


@dataclass
class _TokenResult:
    index: int
    text: str
    normalized: str
    status: str = "unknown"
    severity: str = "default"
    matched_token_index: int | None = None
    note: str | None = None
    insertion_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "index": self.index,
            "text": self.text,
            "normalized": self.normalized,
            "status": self.status,
            "severity": self.severity,
            "matched_token_index": self.matched_token_index,
        }
        if self.note:
            payload["note"] = self.note
        if self.insertion_type:
            payload["insertion_type"] = self.insertion_type
        return payload


@dataclass(frozen=True)
class _Edit:
    operation: AlignmentOperation
    reference_index: int | None = None
    user_index: int | None = None


@dataclass
class _Summary:
    correct_count: int = 0
    substitution_count: int = 0
    deletion_count: int = 0
    insertion_count: int = 0
    minor_error_count: int = 0
    filler_count: int = 0
    word_accuracy: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "correct_count": self.correct_count,
            "substitution_count": self.substitution_count,
            "deletion_count": self.deletion_count,
            "insertion_count": self.insertion_count,
            "minor_error_count": self.minor_error_count,
            "filler_count": self.filler_count,
            "word_accuracy": self.word_accuracy,
        }


def _replace_apostrophes(text: str) -> str:
    normalized = text
    for source, replacement in _APOSTROPHES.items():
        normalized = normalized.replace(source, replacement)
    return normalized


def _expand_contraction(token: str) -> str:
    if token in _CONTRACTIONS:
        return _CONTRACTIONS[token]

    suffix_expansions = (
        ("n't", " not"),
        ("'re", " are"),
        ("'ve", " have"),
        ("'ll", " will"),
        ("'d", " would"),
        ("'m", " am"),
    )
    for suffix, replacement in suffix_expansions:
        if token.endswith(suffix) and len(token) > len(suffix):
            return f"{token[: -len(suffix)]}{replacement}"

    if token.endswith("'s") and len(token) > 2:
        return f"{token[:-2]} is"

    return token


def normalize_token_text(text: str) -> str:
    """Normalize one display token while keeping contraction expansions simple."""
    lowered = _replace_apostrophes(text).lower().strip()
    lowered = lowered.strip(string.punctuation.replace("'", ""))
    if not lowered:
        return ""

    expanded = _expand_contraction(lowered)
    expanded = expanded.translate(_PUNCTUATION_TO_SPACE)
    expanded = expanded.replace("'", "")
    return " ".join(part for part in expanded.split() if part)


def tokenize_for_alignment(text: str) -> list[dict[str, Any]]:
    """Return frontend-facing tokens without losing the original display text."""
    tokens: list[_Token] = []
    for raw_match in _TOKEN_PATTERN.finditer(text or ""):
        raw_text = raw_match.group(0)
        normalized = normalize_token_text(raw_text)
        if not normalized:
            continue
        tokens.append(
            _Token(
                index=len(tokens),
                text=raw_text,
                normalized=normalized,
            )
        )
    return [_token_to_dict(token) for token in tokens]


def align_word_tokens(source_text: str, asr_text: str) -> dict[str, Any]:
    """Align reference and learner ASR text at word level for UI highlighting."""
    reference_tokens = [
        _Token(**token) for token in tokenize_for_alignment(source_text)
    ]
    user_tokens = [_Token(**token) for token in tokenize_for_alignment(asr_text)]

    reference_results = [_result_from_token(token) for token in reference_tokens]
    user_results = [_result_from_token(token) for token in user_tokens]

    if not reference_tokens:
        for user_result in user_results:
            user_result.status = "insertion"
            user_result.severity = "minor"
            user_result.insertion_type = "extra"
            user_result.note = "Extra learner word without a reference sentence."
        summary = _build_summary(reference_results, user_results, reference_count=0)
        return _build_payload(reference_results, user_results, summary)

    if not user_tokens:
        for reference_result in reference_results:
            reference_result.status = "deletion"
            reference_result.severity = "major"
            reference_result.note = "Missing in learner ASR."
        summary = _build_summary(
            reference_results,
            user_results,
            reference_count=len(reference_tokens),
        )
        return _build_payload(reference_results, user_results, summary)

    edits = _align_tokens(reference_tokens, user_tokens)
    insertion_indices: set[int] = set()

    for edit in edits:
        if edit.operation == "equal":
            _mark_pair(
                reference_results[edit.reference_index],
                user_results[edit.user_index],
                status="correct",
                severity="correct",
            )
        elif edit.operation == "minor":
            _mark_pair(
                reference_results[edit.reference_index],
                user_results[edit.user_index],
                status="minor",
                severity="minor",
            )
            reference_results[edit.reference_index].note = "Close but not exact."
            user_results[edit.user_index].status = "substitution"
            user_results[edit.user_index].note = "Close match to the reference word."
        elif edit.operation == "substitution":
            _mark_pair(
                reference_results[edit.reference_index],
                user_results[edit.user_index],
                status="substitution",
                severity="major",
            )
            reference_results[edit.reference_index].note = "Different learner word."
            user_results[edit.user_index].note = "Different from the aligned reference word."
        elif edit.operation == "deletion":
            reference_result = reference_results[edit.reference_index]
            reference_result.status = "deletion"
            reference_result.severity = "major"
            reference_result.note = "Missing in learner ASR."
        elif edit.operation == "insertion":
            insertion_indices.add(edit.user_index)

    _mark_user_insertions(user_results, user_tokens, insertion_indices)
    _mark_unknown_reference_tokens(reference_results)
    _mark_unknown_user_tokens(user_results)

    summary = _build_summary(
        reference_results,
        user_results,
        reference_count=len(reference_tokens),
    )
    return _build_payload(reference_results, user_results, summary)


def _token_to_dict(token: _Token) -> dict[str, Any]:
    return {
        "index": token.index,
        "text": token.text,
        "normalized": token.normalized,
    }


def _result_from_token(token: _Token) -> _TokenResult:
    return _TokenResult(
        index=token.index,
        text=token.text,
        normalized=token.normalized,
    )


def _mark_pair(
    reference_result: _TokenResult,
    user_result: _TokenResult,
    *,
    status: str,
    severity: str,
) -> None:
    reference_result.status = status
    reference_result.severity = severity
    reference_result.matched_token_index = user_result.index
    user_result.status = "correct" if status == "correct" else "substitution"
    user_result.severity = severity
    user_result.matched_token_index = reference_result.index


def _mark_user_insertions(
    user_results: list[_TokenResult],
    user_tokens: list[_Token],
    insertion_indices: set[int],
) -> None:
    for user_index in sorted(insertion_indices):
        user_result = user_results[user_index]
        insertion_type, note = _classify_insertion(user_tokens, user_index, insertion_indices)
        user_result.status = "filler" if insertion_type == "filler" else "insertion"
        user_result.severity = "default" if insertion_type == "filler" else "minor"
        user_result.insertion_type = insertion_type
        user_result.note = note


def _classify_insertion(
    user_tokens: list[_Token],
    user_index: int,
    insertion_indices: set[int],
) -> tuple[str, str]:
    normalized = user_tokens[user_index].normalized
    previous_token = user_tokens[user_index - 1] if user_index > 0 else None
    next_token = user_tokens[user_index + 1] if user_index + 1 < len(user_tokens) else None

    if (
        previous_token
        and previous_token.normalized == normalized
        and user_index - 1 not in insertion_indices
    ) or (
        next_token
        and next_token.normalized == normalized
        and user_index + 1 not in insertion_indices
    ):
        return "repetition", "Repeated learner word."

    if _is_filler_token(user_tokens, user_index, insertion_indices):
        return "filler", "Filler word not present in the reference."

    return "extra", "Extra learner word not present in the reference."


def _is_filler_token(
    user_tokens: list[_Token],
    user_index: int,
    insertion_indices: set[int],
) -> bool:
    normalized = user_tokens[user_index].normalized
    if normalized in _SINGLE_FILLERS:
        return True

    previous_token = user_tokens[user_index - 1] if user_index > 0 else None
    next_token = user_tokens[user_index + 1] if user_index + 1 < len(user_tokens) else None
    if (
        previous_token
        and user_index - 1 in insertion_indices
        and (previous_token.normalized, normalized) in _FILLER_PHRASES
    ):
        return True
    if (
        next_token
        and user_index + 1 in insertion_indices
        and (normalized, next_token.normalized) in _FILLER_PHRASES
    ):
        return True
    return False


def _mark_unknown_reference_tokens(reference_results: list[_TokenResult]) -> None:
    for result in reference_results:
        if result.status == "unknown":
            result.status = "deletion"
            result.severity = "major"
            result.note = "Missing in learner ASR."


def _mark_unknown_user_tokens(user_results: list[_TokenResult]) -> None:
    for result in user_results:
        if result.status == "unknown":
            result.status = "insertion"
            result.severity = "minor"
            result.insertion_type = "extra"
            result.note = "Extra learner word not present in the reference."


def _align_tokens(reference_tokens: list[_Token], user_tokens: list[_Token]) -> list[_Edit]:
    reference_norms = [token.normalized for token in reference_tokens]
    user_norms = [token.normalized for token in user_tokens]
    matcher = difflib.SequenceMatcher(None, reference_norms, user_norms, autojunk=False)

    edits: list[_Edit] = []
    for tag, ref_start, ref_end, user_start, user_end in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(ref_end - ref_start):
                edits.append(_Edit("equal", ref_start + offset, user_start + offset))
        elif tag == "delete":
            for ref_index in range(ref_start, ref_end):
                edits.append(_Edit("deletion", ref_index, None))
        elif tag == "insert":
            for user_index in range(user_start, user_end):
                edits.append(_Edit("insertion", None, user_index))
        elif tag == "replace":
            edits.extend(
                _align_replace_block(
                    reference_tokens,
                    user_tokens,
                    ref_start,
                    ref_end,
                    user_start,
                    user_end,
                )
            )

    return edits


def _align_replace_block(
    reference_tokens: list[_Token],
    user_tokens: list[_Token],
    ref_start: int,
    ref_end: int,
    user_start: int,
    user_end: int,
) -> list[_Edit]:
    ref_block = reference_tokens[ref_start:ref_end]
    user_block = user_tokens[user_start:user_end]
    rows = len(ref_block) + 1
    cols = len(user_block) + 1
    scores = [[0.0 for _ in range(cols)] for _ in range(rows)]
    backtrace: list[list[AlignmentOperation | None]] = [
        [None for _ in range(cols)] for _ in range(rows)
    ]

    for row in range(1, rows):
        scores[row][0] = float(row)
        backtrace[row][0] = "deletion"
    for col in range(1, cols):
        scores[0][col] = float(col)
        backtrace[0][col] = "insertion"

    for row in range(1, rows):
        for col in range(1, cols):
            ref_token = ref_block[row - 1]
            user_token = user_block[col - 1]
            substitution_operation, substitution_cost = _replacement_cost(ref_token, user_token)

            candidates = (
                (scores[row - 1][col - 1] + substitution_cost, substitution_operation),
                (scores[row - 1][col] + 1.0, "deletion"),
                (scores[row][col - 1] + 1.0, "insertion"),
            )
            best_score, best_operation = min(candidates, key=lambda item: item[0])
            scores[row][col] = best_score
            backtrace[row][col] = best_operation

    edits: list[_Edit] = []
    row = len(ref_block)
    col = len(user_block)
    while row > 0 or col > 0:
        operation = backtrace[row][col]
        if operation in {"equal", "minor", "substitution"}:
            edits.append(
                _Edit(
                    operation,
                    ref_start + row - 1,
                    user_start + col - 1,
                )
            )
            row -= 1
            col -= 1
        elif operation == "deletion":
            edits.append(_Edit("deletion", ref_start + row - 1, None))
            row -= 1
        else:
            edits.append(_Edit("insertion", None, user_start + col - 1))
            col -= 1

    edits.reverse()
    return edits


def _replacement_cost(reference_token: _Token, user_token: _Token) -> tuple[AlignmentOperation, float]:
    if reference_token.normalized == user_token.normalized:
        return "equal", 0.0
    if _is_minor_mismatch(reference_token.normalized, user_token.normalized):
        return "minor", 0.5
    return "substitution", 1.0


def _is_minor_mismatch(reference: str, user: str) -> bool:
    if not reference or not user:
        return False
    if reference == user:
        return True
    if _simple_singular(reference) == _simple_singular(user) and min(len(reference), len(user)) > 3:
        return True
    if max(len(reference), len(user)) >= 5 and _levenshtein_distance(reference, user) <= 1:
        return True
    return difflib.SequenceMatcher(None, reference, user, autojunk=False).ratio() >= 0.78


def _simple_singular(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token


def _levenshtein_distance(first: str, second: str) -> int:
    if first == second:
        return 0
    if not first:
        return len(second)
    if not second:
        return len(first)

    previous = list(range(len(second) + 1))
    for row_index, first_char in enumerate(first, start=1):
        current = [row_index]
        for col_index, second_char in enumerate(second, start=1):
            current.append(
                min(
                    previous[col_index] + 1,
                    current[col_index - 1] + 1,
                    previous[col_index - 1] + (0 if first_char == second_char else 1),
                )
            )
        previous = current
    return previous[-1]


def _build_summary(
    reference_results: list[_TokenResult],
    user_results: list[_TokenResult],
    *,
    reference_count: int,
) -> _Summary:
    summary = _Summary(
        correct_count=sum(1 for token in reference_results if token.status == "correct"),
        substitution_count=sum(1 for token in reference_results if token.status == "substitution"),
        deletion_count=sum(1 for token in reference_results if token.status == "deletion"),
        insertion_count=sum(
            1 for token in user_results if token.status in {"insertion", "filler"}
        ),
        minor_error_count=sum(1 for token in reference_results if token.status == "minor"),
        filler_count=sum(1 for token in user_results if token.status == "filler"),
    )

    if reference_count == 0:
        summary.word_accuracy = 1.0 if summary.insertion_count == 0 else 0.0
        return summary

    error_count = (
        summary.substitution_count
        + summary.deletion_count
        + summary.insertion_count
        + 0.5 * summary.minor_error_count
    )
    summary.word_accuracy = round(max(0.0, 1.0 - error_count / reference_count), 4)
    return summary


def _build_payload(
    reference_results: list[_TokenResult],
    user_results: list[_TokenResult],
    summary: _Summary,
) -> dict[str, Any]:
    return {
        "reference_tokens": [token.to_dict() for token in reference_results],
        "user_tokens": [token.to_dict() for token in user_results],
        "summary": summary.to_dict(),
    }
