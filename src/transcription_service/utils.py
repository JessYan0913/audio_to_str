import soundfile as sf
from datetime import timedelta
import srt


def get_audio_duration(audio_path: str) -> float:
    """获取音频文件的时长（秒）"""
    with sf.SoundFile(audio_path) as f:
        return f.frames / f.samplerate


def create_srt_subtitles(subtitle_data: list) -> str:
    """根据字幕数据创建SRT格式字幕"""
    subtitles = [
        srt.Subtitle(
            index=item["index"],
            start=timedelta(seconds=item["start"]),
            end=timedelta(seconds=item["end"]),
            content=item["content"],
        )
        for item in subtitle_data
    ]
    return srt.compose(subtitles)
