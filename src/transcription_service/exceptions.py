class TranscriptionError(Exception):
    """转录服务基础异常"""

    pass


class ModelLoadError(TranscriptionError):
    """模型加载异常"""

    pass


class AudioProcessingError(TranscriptionError):
    """音频处理异常"""

    pass
