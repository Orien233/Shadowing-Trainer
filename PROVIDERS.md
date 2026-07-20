# Provider adapter guide

Provider credentials are configured in the application's **Settings** panel.
They are stored only by the backend; provider list responses contain an API-key
mask, and submitting a blank key during an edit retains the stored key.

## Endpoint fields

`Base URL` is descriptor-specific. Read the hint shown by Settings rather than
assuming a common URL shape.

- `base_url`: the adapter appends its documented resource path.
- `full_endpoint`: enter the whole endpoint. In particular, OpenAI-compatible
  TTS and generic compatible ASR do not append `/audio/speech` or
  `/audio/transcriptions`.
- `model_name`: model, deployment, or voice/model identifier required by that
  adapter. For Azure OpenAI it is the deployment name.

## LLM profiles

| Adapter | Structured JSON | Endpoint / notes |
| --- | --- | --- |
| `openai_chat_compatible` | Yes | OpenAI Chat Completions-compatible JSON profile. |
| `openai_responses` | Yes | Native OpenAI Responses API. |
| `azure_openai` | Yes | Azure OpenAI v1 Responses; choose `api-key` or bearer auth. |
| `anthropic_messages` | Yes | Native Messages API; JSON is prompt-enforced. |
| `gemini_generate_content` | Yes | Native Gemini Generate Content API. |
| `deepseek_chat` | Yes | `https://api.deepseek.com/v1`. |
| `qwen_chat` | Yes | DashScope compatible-mode endpoint. |
| `ollama_chat` / `vllm_chat` | Yes | Local OpenAI-compatible servers; API key is optional with `none` auth. |
| `mimo_chat` / `openai_chat_text` | No | Text-only safety profiles; they cannot enable AI Text generation. |

The adapter's capability declaration, not a runtime probe, determines whether
the AI Text button can run. This prevents an arbitrary compatible gateway from
being treated as JSON-capable merely because it accepts a Chat request.

## TTS adapters

| Adapter | Live voice list | Notes |
| --- | --- | --- |
| `openai_audio_tts` | No | Enter the full synthesis URL yourself; static built-in presets are shown. |
| `azure_speech_tts` | Yes | Azure REST SSML; locale, output format, and voice are configurable. |
| `dashscope_tts` | No | DashScope/Qwen non-streaming synthesis. |
| `mimo_tts` | No | Full MiMo Chat Completions endpoint; Base64 audio result. |
| `deepgram_tts` | No | Deepgram Aura model selects the voice. |
| `elevenlabs_tts` | Yes | Voice ID/default voice and ElevenLabs voice metadata. |

In **AI Text**, save generated or pasted text first, choose speed, voice,
accent/locale, gender preference, and an optional model override, then select
**Create TTS practice**. Sentence audio is created through the durable
`tts_synthesis` job, merged, and saved as an ordinary Material with Sentence
records, so no ASR is used to reconstruct known text.

## ASR adapters and scene routing

| Adapter | `transcribe` | `word_timestamps` | Material remote mode |
| --- | --- | --- | --- |
| Local Whisper | Yes | Yes | Always available locally; model stays cached. |
| `openai_whisper_asr` | Yes | Yes | Allowed. |
| `openai_transcribe_asr` | Yes | No | Forced local for material transcription. |
| `openai_compatible_asr` | Yes | No | Forced local for material transcription. |
| `azure_speech_asr` | Yes | Yes | Allowed (Azure Fast Transcription word offsets). |
| `dashscope_asr` | Yes | No | Forced local for material transcription. |
| `mimo_asr` | Yes | No | Forced local for material transcription. |
| `deepgram_asr` | Yes | Yes | Allowed. |
| `elevenlabs_asr` | Yes | Yes | Allowed. |

The two switches are independent:

- **Use Local Whisper for material transcription** controls uploaded material
  processing and needs a remote provider with both `transcribe` and
  `word_timestamps` when switched off.
- **Use Local Whisper for recording evaluation** controls learner-recording
  assessment and needs only `transcribe` when switched off.

If remote capability is missing, Settings locks the relevant switch on and
shows the missing capability. The backend repeats the same check, so a direct
API/database bypass cannot send a timestamp-less ASR result into material
segmentation. Connection-test failures never change this decision.

DashScope is included only for deployments returning an immediate file
transcript. Its batch/polling/realtime workflows are deliberately not
implemented in this synchronous ASR contract.

## Connection tests

Tests are intentionally non-billable:

- LLM profiles that expose a metadata endpoint make a `GET /models`-style
  check and report `verification_level: network`.
- Speech profiles currently validate the selected endpoint/model/credential
  fields without synthesis or transcription and report
  `verification_level: configuration`.

The response always includes the adapter's static capabilities. Errors remove
API keys, authorization headers, and sensitive URL query values before they
reach the UI.
