from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse
from typing import Optional
import tempfile
import os
import logging
import uuid
import asyncio

# 导入全局状态和配置
from ..transcription_service.core import TranscriptionService
from ..config.shared_state import tasks, tasks_lock
from ..config import shared_state
from ..models.task import TaskResponse, SyncTranscriptionResponse
from ..utils.file_utils import allowed_file
from ..utils.task_utils import _transcribe_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "model_loaded": shared_state.service is not None}


@router.post("/transcribe", response_model=TaskResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
):
    if not shared_state.service:
        raise HTTPException(status_code=500, detail="服务未初始化")

    if not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    try:
        # 保存临时文件
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp:
            temp_audio_path = tmp.name
            content = await file.read()

        # 异步写入文件
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: open(temp_audio_path, "wb").write(content)
        )
        logger.info(f"Saved temporary audio file: {temp_audio_path}")

        # 创建任务
        task_id = str(uuid.uuid4())
        async with tasks_lock:
            tasks[task_id] = {
                "status": "pending",
                "result": None,
                "error": None,
                "filename": file.filename,
                "is_srt": False,
                "language": None,
                "progress": 0.0,
                "partial_result": [],
            }
            logger.info(f"Created task {task_id} for file {file.filename}")

        # 关键修复：使用 asyncio.create_task 创建后台任务，不等待
        task = asyncio.create_task(
            _transcribe_task(
                task_id,
                temp_audio_path,
                language,
                shared_state.service.model_size,
                is_srt=False,
            )
        )
        # 不要 await task，让它在后台运行

        # 立即返回任务ID
        return TaskResponse(status="pending", task_id=task_id)

    except Exception as e:
        # 清理临时文件
        try:
            if "temp_audio_path" in locals() and os.path.exists(temp_audio_path):
                await asyncio.get_event_loop().run_in_executor(
                    None, os.unlink, temp_audio_path
                )
                logger.info(
                    f"Deleted temporary audio file {temp_audio_path} due to error"
                )
        except:
            logger.warning(f"Failed to delete temporary audio file")

        logger.error(f"转录请求处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcribe/srt", response_model=TaskResponse)
async def transcribe_to_srt(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
):
    if not shared_state.service:
        raise HTTPException(status_code=500, detail="服务未初始化")

    if not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    try:
        # 保存临时文件
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp:
            temp_audio_path = tmp.name
            content = await file.read()

        # 异步写入文件
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: open(temp_audio_path, "wb").write(content)
        )
        logger.info(f"Saved temporary audio file: {temp_audio_path}")

        # 创建任务
        task_id = str(uuid.uuid4())
        async with tasks_lock:
            tasks[task_id] = {
                "status": "pending",
                "result": None,
                "error": None,
                "filename": file.filename,
                "is_srt": True,
                "language": None,
                "progress": 0.0,
                "partial_result": [],
            }
            logger.info(f"Created task {task_id} for SRT file {file.filename}")

        # 关键修复：使用 asyncio.create_task 创建后台任务，不等待
        task = asyncio.create_task(
            _transcribe_task(
                task_id,
                temp_audio_path,
                language,
                shared_state.service.model_size,
                is_srt=True,
            )
        )
        # 不要 await task，让它在后台运行

        # 立即返回任务ID
        return TaskResponse(status="pending", task_id=task_id)

    except Exception as e:
        # 清理临时文件
        try:
            if "temp_audio_path" in locals() and os.path.exists(temp_audio_path):
                await asyncio.get_event_loop().run_in_executor(
                    None, os.unlink, temp_audio_path
                )
                logger.info(
                    f"Deleted temporary audio file {temp_audio_path} due to error"
                )
        except:
            logger.warning(f"Failed to delete temporary audio file")

        logger.error(f"SRT转录请求处理失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task/{task_id}")
async def get_task_status(task_id: str, request: Request):
    async def task_status_inner():
        loop = asyncio.get_event_loop()
        async with tasks_lock:
            if task_id not in tasks:
                raise HTTPException(status_code=404, detail="任务不存在")
            task = tasks[task_id].copy()  # 复制任务数据
        logger.info(
            f"Task {task_id}: status={task['status']}, is_srt={task['is_srt']}, progress={task['progress']}"
        )

        status = task["status"]
        if status == "pending":
            return TaskResponse(
                status=status,
                task_id=task_id,
                progress=task["progress"],
                partial_subtitles=task["partial_result"],
            )

        if status == "processing":
            return TaskResponse(
                status=status,
                task_id=task_id,
                progress=task["progress"],
                partial_subtitles=task["partial_result"],
                language=task["language"],
            )

        if status == "failed":
            return TaskResponse(
                status=status,
                task_id=task_id,
                error=task["error"],
                progress=task["progress"],
                partial_subtitles=task["partial_result"],
            )

        if status == "completed":
            if task["is_srt"]:
                temp_srt_path = task["result"]
                file_exists = await loop.run_in_executor(
                    None, os.path.exists, temp_srt_path
                )
                if file_exists:
                    logger.info(f"SRT file exists: {temp_srt_path}")
                    response = FileResponse(
                        temp_srt_path,
                        filename=f"transcription_{os.path.splitext(task['filename'])[0]}.srt",
                        media_type="text/srt",
                    )

                    async def cleanup():
                        try:
                            logger.info(
                                f"Cleaning up SRT file {temp_srt_path} and task {task_id}"
                            )
                            await asyncio.sleep(1)  # 确保 FileResponse 完成
                            await loop.run_in_executor(None, os.unlink, temp_srt_path)
                            async with tasks_lock:
                                del tasks[task_id]
                            logger.info(f"Cleanup completed for task {task_id}")
                        except Exception as e:
                            logger.warning(f"清理任务 {task_id} 失败: {e}")

                    asyncio.get_event_loop().call_later(
                        2, lambda: asyncio.create_task(cleanup())
                    )
                    return response
                else:
                    logger.error(f"SRT file {temp_srt_path} does not exist")
                    raise HTTPException(status_code=500, detail="SRT文件不存在")
            else:
                result = TaskResponse(
                    status=status,
                    task_id=task_id,
                    subtitles=task["result"]["subtitles"],
                    language=task["result"]["language"],
                    progress=100.0,
                )
                async with tasks_lock:
                    del tasks[task_id]
                return result

    try:
        return await asyncio.wait_for(task_status_inner(), timeout=30)  # 设置30秒超时
    except asyncio.TimeoutError:
        logger.error(f"Task {task_id} request timed out")
        raise HTTPException(status_code=504, detail="请求超时")


@router.post("/transcribe/sync", response_model=SyncTranscriptionResponse)
async def transcribe_audio_sync(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
):
    """同步转录接口，用于处理小音频片段"""
    if not shared_state.service:
        raise HTTPException(status_code=500, detail="服务未初始化")

    if not allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    temp_audio_path = None
    try:
        # 保存临时文件
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp:
            temp_audio_path = tmp.name
            content = await file.read()
            tmp.write(content)

        logger.info(f"Saved temporary audio file for sync processing: {temp_audio_path}")

        # 直接调用转录服务并等待结果
        result = await shared_state.service.transcribe(temp_audio_path, language)

        if result.success:
            return SyncTranscriptionResponse(
                success=True,
                subtitles=result.subtitles,
                language=result.language,
            )
        else:
            return SyncTranscriptionResponse(
                success=False, error=result.error or "转录失败"
            )

    except Exception as e:
        logger.error(f"同步转录请求处理失败: {e}")
        # 确保即使发生异常也返回标准的响应模型
        return SyncTranscriptionResponse(success=False, error=str(e))

    finally:
        # 清理临时文件
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.unlink(temp_audio_path)
                logger.info(f"Deleted temporary audio file {temp_audio_path}")
            except Exception as e:
                logger.warning(f"无法删除临时音频文件 {temp_audio_path}: {e}")
