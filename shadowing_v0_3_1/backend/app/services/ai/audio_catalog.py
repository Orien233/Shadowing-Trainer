"""Static catalog entries for synchronous TTS and ASR protocol adapters."""

from __future__ import annotations

from app.services.ai.adapter_registry import (
    AdapterConfigField,
    AdapterDescriptor,
    AdapterTestStrategy,
    register_adapter,
)
from app.services.ai.asr import (
    AzureSpeechASRProvider,
    DashScopeASRProvider,
    DeepgramASRProvider,
    ElevenLabsASRProvider,
    MiMoASRProvider,
    OpenAICompatibleRemoteASRProvider,
    OpenAITranscribeASRProvider,
    OpenAIWhisperASRProvider,
)
from app.services.ai.tts import (
    AzureSpeechTTSProvider,
    DashScopeTTSProvider,
    DeepgramTTSProvider,
    ElevenLabsTTSProvider,
    MiMoTTSProvider,
    OpenAIAudioTTSProvider,
    OpenAICompatibleTTSProvider,
)


_CONFIG_ONLY = AdapterTestStrategy(
    mode="configuration",
    label="Configuration validation",
    description="Validates required settings locally; no synthesis or transcription request is made.",
)

_OPENAI_VOICES = tuple({"id": item, "name": item.title()} for item in (
    "alloy", "echo", "fable", "onyx", "nova", "shimmer",
))


TTS_ADAPTER_DESCRIPTORS = (
    AdapterDescriptor(
        canonical_key="openai_audio_tts",
        kind="tts",
        # Preserve the legacy class identity as well as its full-endpoint
        # behavior for callers importing OpenAICompatibleTTSProvider.
        adapter_class=OpenAICompatibleTTSProvider,
        aliases=("openai_compatible", "openai-compatible", "openai"),
        capabilities=OpenAIAudioTTSProvider.capabilities,
        label="OpenAI Audio TTS / compatible endpoint",
        endpoint_mode="full_endpoint",
        endpoint_hint="Full synthesis endpoint, e.g. https://api.openai.com/v1/audio/speech (never appended automatically)",
        config_fields=(
            AdapterConfigField("default_voice", "Default voice", "select", default="alloy", options=tuple(item["id"] for item in _OPENAI_VOICES)),
            AdapterConfigField("response_format", "Response format", "select", default="mp3", options=("mp3", "opus", "aac", "flac", "wav", "pcm")),
            AdapterConfigField("instructions", "Voice instructions", placeholder="Optional speaking style instruction"),
        ),
        voice_presets=_OPENAI_VOICES,
        docs_url="https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="azure_speech_tts",
        kind="tts",
        adapter_class=AzureSpeechTTSProvider,
        aliases=("azure_speech", "azure-speech"),
        capabilities=AzureSpeechTTSProvider.capabilities,
        label="Azure Speech TTS",
        endpoint_mode="base_url",
        endpoint_hint="Speech resource endpoint, e.g. https://your-resource.cognitiveservices.azure.com",
        config_fields=(
            AdapterConfigField("default_voice", "Default voice", placeholder="en-US-AvaMultilingualNeural"),
            AdapterConfigField("locale", "Locale", default="en-US", placeholder="en-US"),
            AdapterConfigField("output_format", "Output format", default="audio-24khz-48kbitrate-mono-mp3"),
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="subscription-key", options=("subscription-key", "bearer")),
        ),
        docs_url="https://learn.microsoft.com/azure/ai-services/speech-service/rest-text-to-speech",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="dashscope_tts",
        kind="tts",
        adapter_class=DashScopeTTSProvider,
        aliases=("dashscope-tts", "qwen_tts", "qwen-tts"),
        capabilities=DashScopeTTSProvider.capabilities,
        label="DashScope / Qwen TTS",
        endpoint_mode="base_url",
        endpoint_hint="https://dashscope.aliyuncs.com (the adapter adds the Qwen TTS path)",
        config_fields=(
            AdapterConfigField("default_voice", "Default voice", default="Cherry", placeholder="Cherry"),
            AdapterConfigField("audio_format", "Audio format", "select", default="mp3", options=("mp3", "wav", "pcm")),
            AdapterConfigField("language", "Language", placeholder="English or Chinese"),
        ),
        voice_presets=({"id": "Cherry", "name": "Cherry"},),
        docs_url="https://help.aliyun.com/en/model-studio/qwen-tts-api",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="mimo_tts",
        kind="tts",
        adapter_class=MiMoTTSProvider,
        aliases=("mimo-tts",),
        capabilities=MiMoTTSProvider.capabilities,
        label="MiMo TTS",
        endpoint_mode="full_endpoint",
        endpoint_hint="Full MiMo Chat Completions endpoint, e.g. https://api.xiaomimimo.com/v1/chat/completions",
        config_fields=(
            AdapterConfigField("default_voice", "Default voice", default="mimo_default"),
            AdapterConfigField("audio_format", "Audio format", "select", default="wav", options=("wav", "mp3", "pcm16", "opus", "flac")),
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="bearer", options=("bearer", "api-key")),
            AdapterConfigField("style_instruction", "Voice instructions", placeholder="Optional speaking style instruction"),
        ),
        docs_url="https://api.xiaomimimo.com/",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="deepgram_tts",
        kind="tts",
        adapter_class=DeepgramTTSProvider,
        aliases=("deepgram-tts",),
        capabilities=DeepgramTTSProvider.capabilities,
        label="Deepgram Aura TTS",
        endpoint_mode="base_url",
        endpoint_hint="https://api.deepgram.com/v1 (the adapter adds /speak)",
        config_fields=(
            AdapterConfigField("encoding", "Encoding", "select", default="mp3", options=("mp3", "linear16", "flac", "opus")),
            AdapterConfigField("container", "Container", "select", default="mp3", options=("mp3", "wav", "ogg")),
            AdapterConfigField("sample_rate", "Sample rate", "number", placeholder="24000"),
            AdapterConfigField("bit_rate", "Bit rate", "number", placeholder="128000"),
        ),
        docs_url="https://developers.deepgram.com/docs/text-to-speech",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="elevenlabs_tts",
        kind="tts",
        adapter_class=ElevenLabsTTSProvider,
        aliases=("elevenlabs-tts",),
        capabilities=ElevenLabsTTSProvider.capabilities,
        label="ElevenLabs TTS",
        endpoint_mode="base_url",
        endpoint_hint="https://api.elevenlabs.io/v1 (the adapter adds /text-to-speech/{voice_id})",
        config_fields=(
            AdapterConfigField("default_voice", "Default voice ID", placeholder="Voice ID from ElevenLabs"),
            AdapterConfigField("voice_id", "Voice ID fallback", placeholder="Voice ID from ElevenLabs"),
            AdapterConfigField("output_format", "Output format", default="mp3_44100_128"),
            AdapterConfigField("language_code", "Language code", placeholder="en"),
        ),
        docs_url="https://elevenlabs.io/docs/api-reference/text-to-speech/convert",
        test_strategy=_CONFIG_ONLY,
    ),
)


ASR_ADAPTER_DESCRIPTORS = (
    AdapterDescriptor(
        canonical_key="openai_whisper_asr",
        kind="asr",
        adapter_class=OpenAIWhisperASRProvider,
        aliases=("openai-whisper-asr", "whisper-1"),
        capabilities=OpenAIWhisperASRProvider.capabilities,
        label="OpenAI Whisper ASR (word timestamps)",
        endpoint_mode="base_url",
        endpoint_hint="https://api.openai.com/v1 (the adapter adds /audio/transcriptions)",
        config_fields=(
            AdapterConfigField("language", "Language", placeholder="en"),
            AdapterConfigField("prompt", "Prompt", placeholder="Optional vocabulary hint"),
            AdapterConfigField("temperature", "Temperature", "number", placeholder="0"),
            AdapterConfigField("segment_timestamps", "Request segment timestamps", "boolean", default=True),
        ),
        docs_url="https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="openai_transcribe_asr",
        kind="asr",
        adapter_class=OpenAITranscribeASRProvider,
        aliases=("openai-transcribe-asr", "gpt-4o-transcribe"),
        capabilities=OpenAITranscribeASRProvider.capabilities,
        label="OpenAI GPT Transcribe ASR",
        endpoint_mode="base_url",
        endpoint_hint="https://api.openai.com/v1 (the adapter adds /audio/transcriptions)",
        config_fields=(
            AdapterConfigField("language", "Language", placeholder="en"),
            AdapterConfigField("prompt", "Prompt", placeholder="Optional vocabulary hint"),
            AdapterConfigField("temperature", "Temperature", "number", placeholder="0"),
        ),
        docs_url="https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="openai_compatible_asr",
        kind="asr",
        adapter_class=OpenAICompatibleRemoteASRProvider,
        aliases=("openai_compatible", "openai-compatible", "openai"),
        capabilities=OpenAICompatibleRemoteASRProvider.capabilities,
        label="OpenAI-compatible ASR (text only)",
        endpoint_mode="full_endpoint",
        endpoint_hint="Full transcription endpoint supplied by the provider; no path is appended automatically",
        config_fields=(
            AdapterConfigField("language", "Language", placeholder="en"),
            AdapterConfigField("prompt", "Prompt", placeholder="Optional vocabulary hint"),
            AdapterConfigField("temperature", "Temperature", "number", placeholder="0"),
            AdapterConfigField("response_format", "Response format", placeholder="json"),
        ),
        docs_url="https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="azure_speech_asr",
        kind="asr",
        adapter_class=AzureSpeechASRProvider,
        aliases=("azure_speech", "azure-speech"),
        capabilities=AzureSpeechASRProvider.capabilities,
        label="Azure Speech ASR (word timestamps)",
        endpoint_mode="base_url",
        endpoint_hint="Speech resource endpoint, e.g. https://your-resource.cognitiveservices.azure.com",
        config_fields=(
            AdapterConfigField("language", "Language", default="en-US", placeholder="en-US"),
            AdapterConfigField("api_version", "Speech API version", default="2025-10-15"),
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="subscription-key", options=("subscription-key", "bearer")),
        ),
        docs_url="https://learn.microsoft.com/azure/ai-services/speech-service/rest-speech-to-text",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="dashscope_asr",
        kind="asr",
        adapter_class=DashScopeASRProvider,
        aliases=("dashscope-asr", "qwen_asr", "qwen-asr"),
        capabilities=DashScopeASRProvider.capabilities,
        label="DashScope / Qwen ASR (synchronous response only)",
        endpoint_mode="base_url",
        endpoint_hint="https://dashscope.aliyuncs.com (requires an endpoint that returns an immediate transcript)",
        config_fields=(
            AdapterConfigField("file_url", "Public audio URL", placeholder="Optional URL template; leave blank for supported inline input"),
            AdapterConfigField("language", "Language", placeholder="en"),
            AdapterConfigField("input_key", "Input key", "select", default="file_url", options=("file_url", "file_urls")),
        ),
        docs_url="https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="mimo_asr",
        kind="asr",
        adapter_class=MiMoASRProvider,
        aliases=("mimo-asr",),
        capabilities=MiMoASRProvider.capabilities,
        label="MiMo ASR",
        endpoint_mode="full_endpoint",
        endpoint_hint="Full MiMo Chat Completions endpoint, e.g. https://api.xiaomimimo.com/v1/chat/completions",
        config_fields=(
            AdapterConfigField("language", "Language", default="auto", placeholder="auto"),
            AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="bearer", options=("bearer", "api-key")),
        ),
        docs_url="https://api.xiaomimimo.com/",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="deepgram_asr",
        kind="asr",
        adapter_class=DeepgramASRProvider,
        aliases=("deepgram-asr",),
        capabilities=DeepgramASRProvider.capabilities,
        label="Deepgram ASR (word timestamps)",
        endpoint_mode="base_url",
        endpoint_hint="https://api.deepgram.com/v1 (the adapter adds /listen)",
        config_fields=(
            AdapterConfigField("smart_format", "Smart format", "boolean", default=True),
            AdapterConfigField("punctuate", "Punctuate", "boolean", default=True),
            AdapterConfigField("utterances", "Return utterances", "boolean", default=True),
            AdapterConfigField("diarize", "Diarize speakers", "boolean", default=False),
        ),
        docs_url="https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded",
        test_strategy=_CONFIG_ONLY,
    ),
    AdapterDescriptor(
        canonical_key="elevenlabs_asr",
        kind="asr",
        adapter_class=ElevenLabsASRProvider,
        aliases=("elevenlabs-asr",),
        capabilities=ElevenLabsASRProvider.capabilities,
        label="ElevenLabs Scribe ASR (word timestamps)",
        endpoint_mode="base_url",
        endpoint_hint="https://api.elevenlabs.io/v1 (the adapter adds /speech-to-text)",
        config_fields=(
            AdapterConfigField("language_code", "Language code", placeholder="en"),
            AdapterConfigField("diarize", "Diarize speakers", "boolean", default=False),
            AdapterConfigField("timestamps_granularity", "Timestamp granularity", "select", default="none", options=("none", "word")),
        ),
        docs_url="https://elevenlabs.io/docs/api-reference/speech-to-text/convert",
        test_strategy=_CONFIG_ONLY,
    ),
)


for _descriptor in (*TTS_ADAPTER_DESCRIPTORS, *ASR_ADAPTER_DESCRIPTORS):
    register_adapter(_descriptor)


__all__ = ["ASR_ADAPTER_DESCRIPTORS", "TTS_ADAPTER_DESCRIPTORS"]
