from faster_whisper import WhisperModel
import torch
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict, Any, Callable
import logging

from .schemas import TranscriptionResult
from .utils import get_audio_duration, create_srt_subtitles
from .exceptions import ModelLoadError, AudioProcessingError

logger = logging.getLogger(__name__)


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
        self.executor = ThreadPoolExecutor(max_workers=2)  # 用于执行CPU密集型任务
        self._load_model()

    def _load_model(self):
        """加载 faster-whisper 模型"""
        try:
            logger.info(f"使用设备: {self.device} 加载 {self.model_size} 模型")
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type="int8" if self.device == "cpu" else "float16",
            )
            logger.info("faster-whisper 模型加载完成")
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            raise ModelLoadError(f"Failed to load model: {e}")

    def _transcribe_sync(
        self, audio_path: str, language: Optional[str] = None
    ) -> tuple:
        """同步转录方法，在线程池中执行"""
        try:
            if not self.model:
                return False, [], "unknown", "模型未加载"

            # 获取音频总时长
            total_duration = get_audio_duration(audio_path)
            logger.info(f"Audio duration: {total_duration} seconds")

            # 转录音频
            subtitles = []
            segments, info = self.model.transcribe(
                audio_path, language=language, vad_filter=True, beam_size=5
            )

            segment_index = 0
            for segment in segments:
                segment_index += 1
                subtitle_data = {
                    "index": segment_index,
                    "start": segment.start,
                    "end": segment.end,
                    "content": segment.text.strip(),
                }
                subtitles.append(subtitle_data)
                logger.info(f"Segment {segment_index}: {subtitle_data['content']}")

            detected_language = info.language if info else "unknown"
            logger.info(f"音频转录完成，检测到的主要语言: {detected_language}")

            return True, subtitles, detected_language, None

        except Exception as e:
            logger.error(f"转录失败: {e}")
            raise AudioProcessingError(f"Transcription failed: {e}")

    async def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        progress_callback: Optional[
            Callable[[float, List[Dict[str, Any]], str], None]
        ] = None,
    ) -> TranscriptionResult:
        """
        转录音频文件（异步版本）

        Args:
            audio_path: 音频文件路径
            language: 音频语言，None表示自动检测
            progress_callback: 回调函数，用于实时更新进度和中间字幕

        Returns:
            TranscriptionResult: 转录结果
        """
        try:
            # 如果有进度回调，需要实现渐进式更新
            if progress_callback:
                return await self._transcribe_with_progress(
                    audio_path, language, progress_callback
                )

            # 简单情况下直接在线程池中执行
            loop = asyncio.get_event_loop()
            success, subtitles, detected_language, error = await loop.run_in_executor(
                self.executor, self._transcribe_sync, audio_path, language
            )

            return TranscriptionResult(
                success=success,
                subtitles=subtitles,
                language=detected_language,
                error=error,
            )

        except Exception as e:
            logger.error(f"转录失败: {e}")
            return TranscriptionResult(
                success=False, subtitles=[], language="", error=str(e)
            )

    async def _transcribe_with_progress(
        self,
        audio_path: str,
        language: Optional[str],
        progress_callback: Callable[[float, List[Dict[str, Any]], str], None],
    ) -> TranscriptionResult:
        """带进度回调的转录方法"""
        try:
            if not self.model:
                return TranscriptionResult(
                    success=False, subtitles=[], language="", error="模型未加载"
                )

            # 获取音频总时长
            loop = asyncio.get_event_loop()

            total_duration = await loop.run_in_executor(
                self.executor, get_audio_duration, audio_path
            )
            logger.info(f"Audio duration: {total_duration} seconds")

            # 在线程池中执行转录，但需要定期检查进度
            def transcribe_with_callback():
                subtitles = []
                segments, info = self.model.transcribe(
                    audio_path, language=language, vad_filter=True, beam_size=5
                )

                segment_index = 0
                for segment in segments:
                    segment_index += 1
                    subtitle_data = {
                        "index": segment_index,
                        "start": segment.start,
                        "end": segment.end,
                        "content": segment.text.strip(),
                    }
                    subtitles.append(subtitle_data)

                    # 计算进度并调用回调（需要在主线程中执行）
                    progress = min(segment.end / total_duration * 100, 100.0)

                    # 将回调调度到主事件循环
                    asyncio.run_coroutine_threadsafe(
                        progress_callback(progress, subtitles, info.language), loop
                    )

                    logger.info(
                        f"Segment {segment_index}: {subtitle_data['content']}, progress: {progress:.2f}%"
                    )

                return subtitles, info.language

            subtitles, detected_language = await loop.run_in_executor(
                self.executor, transcribe_with_callback
            )

            logger.info(f"音频转录完成，检测到的主要语言: {detected_language}")

            return TranscriptionResult(
                success=True, subtitles=subtitles, language=detected_language
            )

        except Exception as e:
            logger.error(f"转录失败: {e}")
            return TranscriptionResult(
                success=False, subtitles=[], language="", error=str(e)
            )

    async def transcribe_to_srt(
        self,
        audio_path: str,
        output_srt_path: str,
        language: Optional[str] = None,
        progress_callback: Optional[
            Callable[[float, List[Dict[str, Any]], str], None]
        ] = None,
    ) -> bool:
        """
        将音频转换为SRT字幕文件（异步版本）

        Args:
            audio_path: 音频文件路径
            output_srt_path: 输出SRT文件路径
            language: 音频语言，None表示自动检测
            progress_callback: 回调函数，用于实时更新进度和中间字幕

        Returns:
            bool: 是否成功
        """
        try:
            result = await self.transcribe(audio_path, language, progress_callback)
            if not result.success:
                return False

            # 在线程池中生成SRT文件
            def generate_srt():
                # 生成SRT字幕
                srt_content = create_srt_subtitles(result.subtitles)

                # 保存为SRT文件
                with open(output_srt_path, "w", encoding="utf-8") as f:
                    f.write(srt_content)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, generate_srt)

            logger.info(f"SRT 字幕已保存到 {output_srt_path}")
            return True

        except Exception as e:
            logger.error(f"生成SRT文件失败: {e}")
            return False

    def __del__(self):
        """清理资源"""
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False)
