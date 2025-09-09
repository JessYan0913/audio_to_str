from pydantic import BaseModel
from typing import Optional


class TaskResponse(BaseModel):
    status: str
    task_id: Optional[str] = None
    subtitles: Optional[list] = None
    partial_subtitles: Optional[list] = None
    progress: Optional[float] = None
    language: Optional[str] = None
    error: Optional[str] = None
