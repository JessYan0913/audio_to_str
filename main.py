import os
import requests
import argparse
from transcription_service import TranscriptionService, TranscriptionResult


# download_audio 函数保持不变，但移到 transcription_service.py 中
# 为了保持兼容性，这里保留原函数
def download_audio(url, output_path):
    """下载音频文件"""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"音频文件已下载到 {output_path}")
        return True
    except Exception as e:
        print(f"下载音频失败: {e}")
        return False


# audio_to_srt 功能已迁移到 TranscriptionService 类
# 为了保持向后兼容性，提供一个包装函数
def audio_to_srt(audio_path, output_srt_path, language=None, model_size="base"):
    """将音频转换为 SRT 字幕，支持自动语言检测"""
    try:
        # 创建服务实例
        service = TranscriptionService(model_size=model_size)
        # 执行转录并保存为SRT
        success = service.transcribe_to_srt(audio_path, output_srt_path, language)
        return success
    except Exception as e:
        print(f"转录或生成字幕失败: {e}")
        return False


def main():
    """命令行入口点"""
    # 设置命令行参数
    parser = argparse.ArgumentParser(description="Convert audio to SRT subtitles")
    parser.add_argument("--audio", required=True, help="Path or URL to the audio file")
    parser.add_argument(
        "--output", default="output_subtitles.srt", help="Path to save the SRT file"
    )
    parser.add_argument(
        "--language", default=None, help="Language of the audio (default: auto)"
    )
    parser.add_argument(
        "--model", default="large-v3", help="Whisper model size (default: large-v3)"
    )
    args = parser.parse_args()

    # 处理音频路径
    audio_path = args.audio
    output_srt_path = args.output
    is_url = audio_path.startswith(("http://", "https://"))

    # 如果是 URL，下载音频
    if is_url:
        temp_audio_path = "temp_audio.wav"
        if download_audio(audio_path, temp_audio_path):
            if audio_to_srt(
                temp_audio_path,
                output_srt_path,
                language=args.language,
                model_size=args.model,
            ):
                os.remove(temp_audio_path)
                print(f"临时音频文件 {temp_audio_path} 已删除")
            else:
                print(f"转录失败，保留临时音频文件 {temp_audio_path}")
        else:
            print("音频下载失败，退出")
            return
    else:
        # 检查本地音频文件是否存在
        if not os.path.exists(audio_path):
            print(f"错误：音频文件 {audio_path} 不存在")
            return
        audio_to_srt(
            audio_path, output_srt_path, language=args.language, model_size=args.model
        )


if __name__ == "__main__":
    main()
