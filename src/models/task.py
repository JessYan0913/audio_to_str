from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class TaskResponse(BaseModel):
    status: str
    task_id: Optional[str] = None
    subtitles: Optional[List[Dict[str, Any]]] = None
    partial_subtitles: Optional[List[Dict[str, Any]]] = None
    progress: Optional[float] = None
    language: Optional[str] = None
    error: Optional[str] = None


class SyncTranscriptionResponse(BaseModel):
    success: bool
    subtitles: List[Dict[str, Any]] = []
    language: Optional[str] = None
    error: Optional[str] = None
