from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from transcription_service import TranscriptionService
import tempfile
import os
import logging
from typing import Optional, Dict, Any
import uuid
import asyncio
from fastapi.responses import FileResponse
from pydantic import BaseModel
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局服务实例和任务存储
service: Optional[TranscriptionService] = None
tasks: Dict[str, Dict[str, Any]] = {}
tasks_lock = asyncio.Lock()
executor = ProcessPoolExecutor(max_workers=int(os.getenv("MAX_WORKERS", 4)))

# 配置
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB 限制
ALLOWED_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "flac"}


# 任务状态响应模型
class TaskResponse(BaseModel):
    status: str
    task_id: Optional[str] = None
    subtitles: Optional[list] = None
    partial_subtitles: Optional[list] = None
    progress: Optional[float] = None
    language: Optional[str] = None
    error: Optional[str] = None


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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
            success = await service.transcribe_to_srt(
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
            result = await service.transcribe(
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    global service
    try:
        model_size = os.getenv("WHISPER_MODEL_SIZE", "small")
        service = TranscriptionService(model_size=model_size)
        logger.info(f"Transcription service initialized with {model_size} model")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize transcription service: {e}")
        raise
    finally:
        pass


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "model_loaded": service is not None}


@app.post("/transcribe", response_model=TaskResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
):
    if not service:
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
                task_id, temp_audio_path, language, service.model_size, is_srt=False
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


@app.post("/transcribe/srt", response_model=TaskResponse)
async def transcribe_to_srt(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
):
    if not service:
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
                task_id, temp_audio_path, language, service.model_size, is_srt=True
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


@app.get("/task/{task_id}")
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


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 5001))
    uvicorn.run(app, host="0.0.0.0", port=port)
