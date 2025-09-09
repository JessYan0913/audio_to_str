"""
transcription_service - 音频转录服务包
"""

from .core import TranscriptionService
from .schemas import TranscriptionResult
from .exceptions import TranscriptionError, ModelLoadError, AudioProcessingError

__all__ = [
    "TranscriptionService",
    "TranscriptionResult",
    "TranscriptionError",
    "ModelLoadError",
    "AudioProcessingError",
]

__version__ = "0.1.0"
