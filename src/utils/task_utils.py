import tempfile
import os
import logging
import asyncio
from typing import Optional

from ..config.shared_state import tasks, tasks_lock
from ..config import shared_state
from ..transcription_service.core import TranscriptionService

logger = logging.getLogger(__name__)


async def _transcribe_task(
    task_id: str,
    temp_audio_path: str,
    language: Optional[str],
    model_size: str,
    is_srt: bool = False,
):
    """异步转录任务 - 确保在后台真正异步执行"""
    try:
        async with tasks_lock:
            tasks[task_id]["status"] = "processing"
            tasks[task_id]["progress"] = 0.0
            tasks[task_id]["partial_result"] = []
            tasks[task_id]["language"] = None
            logger.info(f"Task {task_id} started processing")

        # 定义进度回调函数
        async def progress_callback(
            progress: float, subtitles: list, detected_language: str
        ):
            async with tasks_lock:
                if task_id in tasks:  # 防止任务被删除后仍然更新
                    tasks[task_id]["progress"] = progress
                    tasks[task_id]["partial_result"] = subtitles.copy()
                    tasks[task_id]["language"] = detected_language
                    logger.info(f"Task {task_id} progress: {progress:.2f}%")

        # 关键修复：确保转录操作真正异步执行
        if is_srt:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as tmp_srt:
                temp_srt_path = tmp_srt.name

            # 使用 asyncio.create_task 确保异步执行
            success = await shared_state.service.transcribe_to_srt(
                temp_audio_path, temp_srt_path, language, progress_callback
            )

            async with tasks_lock:
                if task_id in tasks:  # 防止任务被删除
                    if success:
                        tasks[task_id]["status"] = "completed"
                        tasks[task_id]["result"] = temp_srt_path
                        tasks[task_id]["progress"] = 100.0
                        logger.info(f"Task {task_id} completed successfully")
                    else:
                        tasks[task_id]["status"] = "failed"
                        tasks[task_id]["error"] = "SRT转录失败"
                        logger.error(f"Task {task_id} failed: SRT转录失败")
        else:
            # 使用 asyncio.create_task 确保异步执行
            result = await shared_state.service.transcribe(
                temp_audio_path, language, progress_callback
            )

            async with tasks_lock:
                if task_id in tasks:  # 防止任务被删除
                    if result.success:
                        tasks[task_id]["status"] = "completed"
                        tasks[task_id]["result"] = {
                            "subtitles": result.subtitles,
                            "language": result.language,
                        }
                        tasks[task_id]["progress"] = 100.0
                        tasks[task_id]["partial_result"] = result.subtitles
                        tasks[task_id]["language"] = result.language
                        logger.info(f"Task {task_id} completed successfully")
                    else:
                        tasks[task_id]["status"] = "failed"
                        tasks[task_id]["error"] = result.error
                        logger.error(f"Task {task_id} failed: {result.error}")

    except asyncio.CancelledError:
        logger.info(f"Task {task_id} was cancelled")
        async with tasks_lock:
            if task_id in tasks:
                tasks[task_id]["status"] = "failed"
                tasks[task_id]["error"] = "任务被取消"
    except Exception as e:
        async with tasks_lock:
            if task_id in tasks:
                tasks[task_id]["status"] = "failed"
                tasks[task_id]["error"] = str(e)
                logger.error(f"Task {task_id} failed with exception: {e}")
    finally:
        # 清理临时文件
        try:
            if os.path.exists(temp_audio_path):
                await asyncio.get_event_loop().run_in_executor(
                    None, os.unlink, temp_audio_path
                )
                logger.info(f"Deleted temporary audio file {temp_audio_path}")
        except Exception as e:
            logger.warning(f"无法删除临时音频文件 {temp_audio_path}: {e}")
