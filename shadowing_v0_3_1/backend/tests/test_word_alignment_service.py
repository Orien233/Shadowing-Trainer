from app.services.word_alignment_service import align_word_tokens


def _statuses(payload, side):
    return [token["status"] for token in payload[f"{side}_tokens"]]


def test_align_word_tokens_exact_match():
    payload = align_word_tokens("The quick brown fox.", "the quick brown fox")

    assert _statuses(payload, "reference") == ["correct", "correct", "correct", "correct"]
    assert _statuses(payload, "user") == ["correct", "correct", "correct", "correct"]
    assert payload["summary"]["correct_count"] == 4
    assert payload["summary"]["word_accuracy"] == 1.0


def test_align_word_tokens_deletion():
    payload = align_word_tokens("The quick brown fox", "The brown fox")

    assert _statuses(payload, "reference") == ["correct", "deletion", "correct", "correct"]
    assert payload["reference_tokens"][1]["text"] == "quick"
    assert payload["summary"]["deletion_count"] == 1


def test_align_word_tokens_filler_insertion():
    payload = align_word_tokens("I am ready", "I am um ready")

    filler = payload["user_tokens"][2]
    assert filler["status"] == "filler"
    assert filler["insertion_type"] == "filler"
    assert payload["summary"]["insertion_count"] == 1
    assert payload["summary"]["filler_count"] == 1


def test_align_word_tokens_substitution():
    payload = align_word_tokens("I like cats", "I like dogs")

    assert _statuses(payload, "reference") == ["correct", "correct", "substitution"]
    assert _statuses(payload, "user") == ["correct", "correct", "substitution"]
    assert payload["summary"]["substitution_count"] == 1


def test_align_word_tokens_regular_insertion():
    payload = align_word_tokens("I like cats", "I really like cats")

    inserted = payload["user_tokens"][1]
    assert inserted["status"] == "insertion"
    assert inserted["insertion_type"] == "extra"
    assert payload["summary"]["insertion_count"] == 1


def test_align_word_tokens_empty_user_text():
    payload = align_word_tokens("I like cats", "")

    assert _statuses(payload, "reference") == ["deletion", "deletion", "deletion"]
    assert payload["user_tokens"] == []
    assert payload["summary"]["deletion_count"] == 3
    assert payload["summary"]["word_accuracy"] == 0.0


def test_align_word_tokens_empty_reference_text_marks_all_user_words_as_insertions():
    payload = align_word_tokens("", "um I like cats")

    assert payload["reference_tokens"] == []
    assert _statuses(payload, "user") == ["insertion", "insertion", "insertion", "insertion"]
    assert payload["summary"]["insertion_count"] == 4
    assert payload["summary"]["word_accuracy"] == 0.0
