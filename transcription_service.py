import whisper
import srt
from datetime import timedelta
import torch
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """转录结果数据类"""

    success: bool
    subtitles: List[Dict[str, Any]]
    language: str
    error: Optional[str] = None


class TranscriptionService:
    """音频转录服务类"""

    def __init__(self, model_size: str = "large-v3"):
        """
        初始化转录服务

        Args:
            model_size: Whisper模型大小
        """
        self.model_size = model_size
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self._load_model()

    def _load_model(self):
        """加载Whisper模型"""
        try:
            logger.info(f"使用设备: {self.device} 加载 {self.model_size} 模型")
            self.model = whisper.load_model(self.model_size, device=self.device)
            logger.info("Whisper 模型加载完成")
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise

    def transcribe(
        self, audio_path: str, language: Optional[str] = None
    ) -> TranscriptionResult:
        """
        转录音频文件

        Args:
            audio_path: 音频文件路径
            language: 音频语言，None表示自动检测

        Returns:
            TranscriptionResult: 转录结果
        """
        try:
            if not self.model:
                return TranscriptionResult(
                    success=False, subtitles=[], language="", error="模型未加载"
                )

            # 转录音频
            result = self.model.transcribe(audio_path, language=language, verbose=True)
            detected_language = result.get("language", "unknown")
            logger.info(f"音频转录完成，检测到的主要语言: {detected_language}")

            # 生成字幕数据
            subtitles = []
            for i, segment in enumerate(result["segments"]):
                start_time = timedelta(seconds=segment["start"])
                end_time = timedelta(seconds=segment["end"])
                subtitle_data = {
                    "index": i + 1,
                    "start": start_time.total_seconds(),
                    "end": start_time.total_seconds(),
                    "content": segment["text"].strip(),
                }
                subtitles.append(subtitle_data)

            return TranscriptionResult(
                success=True, subtitles=subtitles, language=detected_language
            )

        except Exception as e:
            logger.error(f"转录失败: {e}")
            return TranscriptionResult(
                success=False, subtitles=[], language="", error=str(e)
            )

    def transcribe_to_srt(
        self, audio_path: str, output_srt_path: str, language: Optional[str] = None
    ) -> bool:
        """
        将音频转换为SRT字幕文件

        Args:
            audio_path: 音频文件路径
            output_srt_path: 输出SRT文件路径
            language: 音频语言，None表示自动检测

        Returns:
            bool: 是否成功
        """
        try:
            result = self.transcribe(audio_path, language)
            if not result.success:
                return False

            # 生成SRT字幕
            subtitles = []
            for item in result.subtitles:
                subtitle = srt.Subtitle(
                    index=item["index"],
                    start=timedelta(seconds=item["start"]),
                    end=timedelta(seconds=item["end"]),
                    content=item["content"],
                )
                subtitles.append(subtitle)

            # 保存为SRT文件
            with open(output_srt_path, "w", encoding="utf-8") as f:
                f.write(srt.compose(subtitles))

            logger.info(f"SRT 字幕已保存到 {output_srt_path}")
            return True

        except Exception as e:
            logger.error(f"生成SRT文件失败: {e}")
            return False
