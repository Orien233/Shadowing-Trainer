"""Supported remote audio protocol adapters.

Other adapter implementations remain in the source tree for future work but
are intentionally not registered here.
"""
from app.services.ai.adapter_registry import AdapterConfigField, AdapterDescriptor, AdapterTestStrategy, register_adapter
from app.services.ai.audio_types import ProviderCapability
from app.services.ai.asr.mimo import MiMoASRProvider
from app.services.ai.asr.openai_compatible import OpenAIWhisperASRProvider
from app.services.ai.tts.mimo import MiMoTTSProvider
from app.services.ai.tts.openai_compatible import OpenAICompatibleTTSProvider

_CONFIG_ONLY = AdapterTestStrategy(mode="configuration", label="Configuration validation", description="Validates settings locally; no paid audio request is made.")
_PCM = (
    AdapterConfigField("pcm_sample_rate", "Raw PCM sample rate", "number", placeholder="e.g. 24000"),
    AdapterConfigField("pcm_channels", "Raw PCM channels", "number", default=1, placeholder="1"),
    AdapterConfigField("pcm_sample_format", "Raw PCM sample format", "select", default="s16le", options=("s16le", "s24le", "s32le", "f32le")),
)

TTS_ADAPTER_DESCRIPTORS = (
    AdapterDescriptor(canonical_key="openai_audio_tts", kind="tts", adapter_class=OpenAICompatibleTTSProvider,
        aliases=("openai_compatible", "openai-compatible", "openai"), capabilities=frozenset({ProviderCapability.SYNTHESIZE}),
        format_options=("wav", "mp3", "flac", "opus", "aac", "pcm"), label="OpenAI Audio TTS",
        preset_defaults={"base_url": "https://api.openai.com/v1/audio/speech", "enabled_capabilities": ["synthesize"], "enabled_formats": ["wav"]},
        endpoint_mode="full_endpoint", endpoint_hint="Full endpoint, e.g. https://api.openai.com/v1/audio/speech",
        config_fields=(AdapterConfigField("default_voice", "Default voice", default="alloy"), AdapterConfigField("instructions", "Voice instructions", placeholder="Optional speaking style instruction")) + _PCM,
        docs_url="https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create", test_strategy=_CONFIG_ONLY),
    AdapterDescriptor(canonical_key="mimo_tts", kind="tts", adapter_class=MiMoTTSProvider, aliases=("mimo-tts",),
        capabilities=frozenset({ProviderCapability.SYNTHESIZE}), format_options=("wav", "mp3", "flac", "opus", "pcm16"), label="MiMo TTS",
        preset_defaults={"base_url": "https://api.xiaomimimo.com/v1/chat/completions", "enabled_capabilities": ["synthesize"], "enabled_formats": ["wav"]},
        endpoint_mode="full_endpoint", endpoint_hint="Full MiMo Chat Completions endpoint", config_fields=(
            AdapterConfigField("default_voice", "Default voice", default="mimo_default"), AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="bearer", options=("bearer", "api-key")), AdapterConfigField("style_instruction", "Voice instructions")) + _PCM,
        docs_url="https://api.xiaomimimo.com/", test_strategy=_CONFIG_ONLY),
)
ASR_ADAPTER_DESCRIPTORS = (
    AdapterDescriptor(canonical_key="openai_audio_asr", kind="asr", adapter_class=OpenAIWhisperASRProvider, aliases=("openai_whisper_asr", "openai-whisper-asr", "whisper-1"),
        capabilities=frozenset({ProviderCapability.TRANSCRIBE, ProviderCapability.WORD_TIMESTAMPS}), label="OpenAI Audio Transcription",
        preset_defaults={"base_url": "https://api.openai.com/v1", "enabled_capabilities": ["transcribe", "word_timestamps"], "enabled_formats": []},
        endpoint_mode="base_url", endpoint_hint="https://api.openai.com/v1  (adds /audio/transcriptions)", config_fields=(AdapterConfigField("language", "Language", placeholder="en"), AdapterConfigField("prompt", "Prompt", placeholder="Optional vocabulary hint"), AdapterConfigField("temperature", "Temperature", "number", placeholder="0")), docs_url="https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create", test_strategy=_CONFIG_ONLY),
    AdapterDescriptor(canonical_key="mimo_asr", kind="asr", adapter_class=MiMoASRProvider, aliases=("mimo-asr",), capabilities=frozenset({ProviderCapability.TRANSCRIBE}), label="MiMo ASR",
        preset_defaults={"base_url": "https://api.xiaomimimo.com/v1/chat/completions", "enabled_capabilities": ["transcribe"], "enabled_formats": []}, endpoint_mode="full_endpoint", endpoint_hint="Full MiMo Chat Completions endpoint", config_fields=(AdapterConfigField("language", "Language", default="auto"), AdapterConfigField("auth_scheme", "Authentication scheme", "select", default="bearer", options=("bearer", "api-key"))), docs_url="https://api.xiaomimimo.com/", test_strategy=_CONFIG_ONLY),
)
for _descriptor in (*TTS_ADAPTER_DESCRIPTORS, *ASR_ADAPTER_DESCRIPTORS): register_adapter(_descriptor)
__all__ = ["ASR_ADAPTER_DESCRIPTORS", "TTS_ADAPTER_DESCRIPTORS"]
