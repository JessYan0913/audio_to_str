import torch
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from transcription_service import TranscriptionService, TranscriptionResult
import tempfile
import os
import logging
from typing import Optional, Dict, Any
import uuid
import asyncio
from fastapi.responses import FileResponse
from pydantic import BaseModel
from concurrent.futures import ProcessPoolExecutor
import whisper
import srt
from datetime import timedelta
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
    language: Optional[str] = None
    error: Optional[str] = None


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _run_transcription(
    audio_path: str, language: Optional[str], model_size: str, is_srt: bool = False
) -> Dict:
    """在进程中运行转录任务"""
    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = whisper.load_model(model_size, device=device)
        logger.info(f"Running transcription for {audio_path}, is_srt={is_srt}")
        if is_srt:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as tmp_srt:
                temp_srt_path = tmp_srt.name
                logger.info(f"Created temporary SRT file: {temp_srt_path}")
            result = model.transcribe(audio_path, language=language, verbose=True)
            if not result.get("segments"):
                logger.error("Transcription failed: no segments found")
                return {"success": False, "error": "转录失败", "result": None}

            subtitles = []
            for i, segment in enumerate(result["segments"]):
                subtitle = srt.Subtitle(
                    index=i + 1,
                    start=timedelta(seconds=segment["start"]),
                    end=timedelta(seconds=segment["end"]),
                    content=segment["text"].strip(),
                )
                subtitles.append(subtitle)
            with open(temp_srt_path, "w", encoding="utf-8") as f:
                f.write(srt.compose(subtitles))
            logger.info(f"SRT file written to {temp_srt_path}")
            return {
                "success": True,
                "result": temp_srt_path,
                "language": result.get("language", "unknown"),
            }
        else:
            result = model.transcribe(audio_path, language=language, verbose=True)
            subtitles = [
                {
                    "index": i + 1,
                    "start": segment["start"],
                    "end": segment["end"],
                    "content": segment["text"].strip(),
                }
                for i, segment in enumerate(result["segments"])
            ]
            return {
                "success": True,
                "result": {
                    "subtitles": subtitles,
                    "language": result.get("language", "unknown"),
                },
                "language": result.get("language", "unknown"),
            }
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return {"success": False, "error": str(e), "result": None}


async def _transcribe_task(
    task_id: str,
    temp_audio_path: str,
    language: Optional[str],
    model_size: str,
    is_srt: bool = False,
):
    """异步转录任务"""
    try:
        async with tasks_lock:
            tasks[task_id]["status"] = "processing"
            logger.info(f"Task {task_id} started processing")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor, _run_transcription, temp_audio_path, language, model_size, is_srt
        )
        logger.info(f"Transcription result for task {task_id}: {result}")

        async with tasks_lock:
            if result["success"]:
                tasks[task_id]["status"] = "completed"
                tasks[task_id]["result"] = result["result"]
                tasks[task_id]["language"] = result["language"]
                logger.info(f"Task {task_id} completed successfully")
            else:
                tasks[task_id]["status"] = "failed"
                tasks[task_id]["error"] = result["error"]
                logger.error(f"Task {task_id} failed: {result['error']}")
    except Exception as e:
        async with tasks_lock:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["error"] = str(e)
            logger.error(f"Task {task_id} failed with exception: {e}")
    finally:
        try:
            await loop.run_in_executor(None, os.unlink, temp_audio_path)
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
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp:
            temp_audio_path = tmp.name
            content = await file.read()
            with open(temp_audio_path, "wb") as f:
                f.write(content)
            logger.info(f"Saved temporary audio file: {temp_audio_path}")

        task_id = str(uuid.uuid4())
        async with tasks_lock:
            tasks[task_id] = {
                "status": "pending",
                "result": None,
                "error": None,
                "filename": file.filename,
                "is_srt": False,
                "language": None,
            }
            logger.info(f"Created task {task_id} for file {file.filename}")

        asyncio.create_task(
            _transcribe_task(
                task_id, temp_audio_path, language, service.model_size, is_srt=False
            )
        )
        return TaskResponse(status="pending", task_id=task_id)

    except Exception as e:
        try:
            if "temp_audio_path" in locals():
                await asyncio.get_event_loop().run_in_executor(
                    None, os.unlink, temp_audio_path
                )
                logger.info(
                    f"Deleted temporary audio file {temp_audio_path} due to error"
                )
        except:
            logger.warning(f"Failed to delete temporary audio file {temp_audio_path}")
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
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp:
            temp_audio_path = tmp.name
            content = await file.read()
            with open(temp_audio_path, "wb") as f:
                f.write(content)
            logger.info(f"Saved temporary audio file: {temp_audio_path}")

        task_id = str(uuid.uuid4())
        async with tasks_lock:
            tasks[task_id] = {
                "status": "pending",
                "result": None,
                "error": None,
                "filename": file.filename,
                "is_srt": True,
                "language": None,
            }
            logger.info(f"Created task {task_id} for SRT file {file.filename}")

        asyncio.create_task(
            _transcribe_task(
                task_id, temp_audio_path, language, service.model_size, is_srt=True
            )
        )
        return TaskResponse(status="pending", task_id=task_id)

    except Exception as e:
        try:
            if "temp_audio_path" in locals():
                await asyncio.get_event_loop().run_in_executor(
                    None, os.unlink, temp_audio_path
                )
                logger.info(
                    f"Deleted temporary audio file {temp_audio_path} due to error"
                )
        except:
            logger.warning(f"Failed to delete temporary audio file {temp_audio_path}")
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
        logger.info(f"Task {task_id}: status={task['status']}, is_srt={task['is_srt']}")

        status = task["status"]
        if status in ["pending", "processing"]:
            return TaskResponse(status=status)

        if status == "failed":
            return TaskResponse(status=status, error=task["error"])

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
                            await loop.run_in_executor(None, os.unlink, temp_srt_path)
                            async with tasks_lock:
                                del tasks[task_id]
                            logger.info(f"Cleanup completed for task {task_id}")
                        except Exception as e:
                            logger.warning(f"清理任务 {task_id} 失败: {e}")

                    asyncio.create_task(cleanup())
                    return response
                else:
                    logger.error(f"SRT file {temp_srt_path} does not exist")
                    raise HTTPException(status_code=500, detail="SRT文件不存在")
            else:
                result = TaskResponse(
                    status=status,
                    subtitles=task["result"]["subtitles"],
                    language=task["result"]["language"],
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
