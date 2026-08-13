# Multilingual behaviour and boundaries

[简体中文](../zh-CN/multilingual.md) | English · [Documentation home](README.md)

## Three independent languages

| Setting | Allowed values | Purpose |
| --- | --- | --- |
| `ui_locale` | `zh-CN`, `en-US` | Interface copy and status labels only |
| `learning_language` | Controlled content-language catalog | Default body language for new uploads and text practices |
| `translation_language` | Controlled content-language catalog | Default language for new sentence translations and AI explanations |

Changing the UI locale does not translate stored content. Changing a global learning or translation preference affects only content created afterwards; Materials and Text Practices retain their language snapshots.

## Content-language catalog

The backend accepts these canonical BCP-47 tags:

| Tag | Language | Tag | Language |
| --- | --- | --- | --- |
| `en` | English | `zh-CN` | Chinese, Simplified |
| `zh-TW` | Chinese, Traditional | `ja` | Japanese |
| `ko` | Korean | `es` | Spanish |
| `fr` | French | `de` | German |
| `it` | Italian | `pt` | Portuguese |
| `ru` | Russian | `ar` | Arabic |

Input casing and underscores in `zh_cn` or `zh_tw` are normalized. Unknown content languages are rejected. `auto` is reserved for ASR parameters that explicitly support automatic detection and cannot be a learning language; `und` is allowed only where the backend explicitly represents an unknown language.

## Language hand-offs

| Workflow | Behaviour |
| --- | --- |
| Upload | The request supplies content and translation languages; the Material stores both |
| Material processing | Content language goes to ASR and segmentation; the translation target comes from the Material |
| Collected words | Words are saved, queried, and deduplicated within a canonical language |
| AI Text | Target language limits eligible collections; generated/imported text saves target and translation languages |
| TTS | Queueing freezes both languages; the task language overrides any provider default |
| Recording evaluation | The service reads the parent Material language and passes it to ASR and scoring strategies |

When source and translation languages match, translation returns the source without calling an LLM. Translation is enrichment: if no eligible LLM exists or one sentence fails, the material or TTS practice still becomes usable with an empty translation and a UI-localized status.

## Collections and AI Text

Collected words use Unicode NFKC and `casefold` for their deduplication key while preserving visible casing and combining marks. Random selection queries only the target language, and manual selection validates every collection language; mixed-language selection returns a validation error.

The LLM prompt uses language names and BCP-47 tags without binding to a vendor. Used-word checking applies token boundaries to whitespace languages and normalized substrings to non-whitespace scripts, avoiding false positives such as treating English `he` as used inside `the`.

## Provider language limits

An explicit task language takes precedence over a Material/Text Practice snapshot, which takes precedence over the provider default. The current service rejects a TTS language override that conflicts with the Text Practice target language, preventing synthesized speech and Material metadata from disagreeing.

- OpenAI ASR receives a primary language code when needed, for example `zh-CN → zh`.
- MiMo ASR accepts only `auto`, `zh`, and `en`; other languages use Local Whisper or fail explicitly.
- Local Whisper receives the task language for the selected scene and reuses its in-process model cache.
- OpenAI TTS records language in internal metadata by default and does not automatically send compatibility-sensitive `instructions`.

See [ASR scene routing](providers.md#asr-scene-routing) for the full route matrix.

## Segmentation and scoring boundaries

Material segmentation prefers ASR segment and word timestamps. Chinese and Japanese fragments are joined without inserted spaces; other catalog languages use spaces by default. TTS sentence splitting supports common Latin, CJK, Arabic, and Devanagari terminators while avoiding periods inside decimals and domain names. It remains a conservative rule set, not a full linguistic tokenizer.

Scoring exposes the actual alignment mode instead of calling every result “word accuracy”:

| Content language | Alignment mode | Support level |
| --- | --- | --- |
| English | word | full |
| Chinese, Japanese, Korean | Unicode character | limited |
| Other catalog languages | Unicode token | basic |

English contraction, filler, singular/plural, and minor morphology rules are never applied to non-English text. Evaluation `raw_metrics` stores `language`, `alignment_mode`, and `support_level`, and the frontend labels word, character, or token accuracy accordingly. Chinese/Japanese collection display uses browser `Intl.Segmenter`; evaluation tokens only project status and never replace or damage source punctuation and spacing.

Prosody, pitch, and duration metrics can still guide multilingual practice, but they are not calibrated for every language and should be interpreted together with alignment results and listening judgment.
