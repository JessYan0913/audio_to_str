from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class TranscriptionResult:
    """转录结果数据类"""

    success: bool
    subtitles: List[Dict[str, Any]]
    language: str
    error: Optional[str] = None
