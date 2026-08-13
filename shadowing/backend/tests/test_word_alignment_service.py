from app.services.word_alignment_service import align_word_tokens


def _statuses(payload, side):
    return [token["status"] for token in payload[f"{side}_tokens"]]


def test_align_word_tokens_exact_match():
    payload = align_word_tokens("The quick brown fox.", "the quick brown fox")

    assert _statuses(payload, "reference") == ["correct", "correct", "correct", "correct"]
    assert _statuses(payload, "user") == ["correct", "correct", "correct", "correct"]
    assert payload["summary"]["correct_count"] == 4
    assert payload["summary"]["word_accuracy"] == 1.0
    assert payload["language"] == "en"
    assert payload["alignment_mode"] == "word"
    assert payload["support_level"] == "full"


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


def test_chinese_uses_character_alignment_without_spaces():
    payload = align_word_tokens(
        "\u4f60\u597d\uff0c\u4e16\u754c",
        "\u4f60\u597d\u4e16\u754c",
        content_language="zh-CN",
    )

    assert [token["text"] for token in payload["reference_tokens"]] == [
        "\u4f60", "\u597d", "\u4e16", "\u754c",
    ]
    assert _statuses(payload, "reference") == ["correct"] * 4
    assert payload["language"] == "zh-CN"
    assert payload["alignment_mode"] == "unicode_character"
    assert payload["support_level"] == "limited"
    assert payload["summary"]["accuracy_unit"] == "character"


def test_japanese_uses_character_alignment_without_english_morphology_rules():
    payload = align_word_tokens(
        "\u79c1\u306f\u5b66\u751f\u3067\u3059",
        "\u79c1\u306f\u5148\u751f\u3067\u3059",
        content_language="ja",
    )

    assert len(payload["reference_tokens"]) == 6
    assert payload["summary"]["substitution_count"] == 1
    assert payload["summary"]["minor_error_count"] == 0
    assert payload["alignment_mode"] == "unicode_character"


def test_arabic_uses_generic_unicode_words_without_english_filler_rules():
    payload = align_word_tokens(
        "\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645",
        "\u0645\u0631\u062d\u0628\u0627 \u0628\u0627\u0644\u0639\u0627\u0644\u0645 um",
        content_language="ar",
    )

    inserted = payload["user_tokens"][-1]
    assert [token["text"] for token in payload["reference_tokens"]] == [
        "\u0645\u0631\u062d\u0628\u0627", "\u0628\u0627\u0644\u0639\u0627\u0644\u0645",
    ]
    assert inserted["status"] == "insertion"
    assert inserted["insertion_type"] == "extra"
    assert payload["summary"]["filler_count"] == 0
    assert payload["alignment_mode"] == "unicode_word"
    assert payload["support_level"] == "basic"
