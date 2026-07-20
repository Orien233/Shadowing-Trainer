from app.services.ai.asr.base import ASRProvider
from app.services.ai.asr.local_whisper import LocalWhisperASRProvider
from app.services.ai.asr.openai_compatible import (
    OpenAICompatibleRemoteASRProvider,
    OpenAITranscribeASRProvider,
    OpenAIWhisperASRProvider,
)
from app.services.ai.asr.azure_speech import AzureSpeechASRProvider
from app.services.ai.asr.dashscope import DashScopeASRProvider
from app.services.ai.asr.mimo import MiMoASRProvider
from app.services.ai.asr.deepgram import DeepgramASRProvider
from app.services.ai.asr.elevenlabs import ElevenLabsASRProvider

__all__ = [
    "ASRProvider",
    "LocalWhisperASRProvider",
    "OpenAIWhisperASRProvider",
    "OpenAITranscribeASRProvider",
    "OpenAICompatibleRemoteASRProvider",
    "AzureSpeechASRProvider",
    "DashScopeASRProvider",
    "MiMoASRProvider",
    "DeepgramASRProvider",
    "ElevenLabsASRProvider",
]
