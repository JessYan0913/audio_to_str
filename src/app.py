from fastapi import FastAPI
from .transcription_service.core import TranscriptionService
import os
import logging
from contextlib import asynccontextmanager

# 导入配置和状态
from .config.shared_state import service
from .routes.transcription import router as transcription_router

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    from .config import shared_state
    try:
        model_size = os.getenv("WHISPER_MODEL_SIZE", "small")
        shared_state.service = TranscriptionService(model_size=model_size)
        logger.info(f"Transcription service initialized with {model_size} model")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize transcription service: {e}")
        raise
    finally:
        pass


app = FastAPI(lifespan=lifespan)

# 注册路由
app.include_router(transcription_router)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 5001))
    uvicorn.run(app, host="0.0.0.0", port=port)
