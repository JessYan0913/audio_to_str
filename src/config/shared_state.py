# 共享状态和全局变量
from typing import Optional, Dict, Any
import asyncio
from concurrent.futures import ProcessPoolExecutor
import os

# 全局服务实例和任务存储
service: Optional["TranscriptionService"] = None
tasks: Dict[str, Dict[str, Any]] = {}
tasks_lock = asyncio.Lock()
executor = ProcessPoolExecutor(max_workers=int(os.getenv("MAX_WORKERS", 4)))
