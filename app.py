from flask import Flask, request, jsonify, send_file
from transcription_service import TranscriptionService, TranscriptionResult
import tempfile
import os
import logging
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import uuid
import threading

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 配置
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB 限制
ALLOWED_EXTENSIONS = {"mp3", "wav", "m4a", "ogg", "flac"}

# 全局服务实例和执行器
service: Optional[TranscriptionService] = None
executor: Optional[ThreadPoolExecutor] = None
# 任务存储
tasks: Dict[str, Dict[str, Any]] = {}
tasks_lock = threading.Lock()


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.before_first_request
def initialize_service():
    """在第一个请求前初始化服务"""
    global service
    if service is None:
        try:
            model_size = os.getenv("WHISPER_MODEL_SIZE", "large-v3")
            service = TranscriptionService(model_size=model_size)
            logger.info(f"Transcription service initialized with {model_size} model")
        except Exception as e:
            logger.error(f"Failed to initialize transcription service: {e}")
            raise


@app.route("/health", methods=["GET"])
def health_check():
    """健康检查端点"""
    return jsonify({"status": "healthy", "model_loaded": service is not None})


@app.route("/transcribe", methods=["POST"])
def transcribe_audio():
    """
    转录音频文件API端点

    POST /transcribe
    Content-Type: multipart/form-data

    Form data:
    - file: 音频文件
    - language: 可选，音频语言
    - model_size: 可选，模型大小

    Returns:
    {
        "success": true,
        "subtitles": [
            {
                "index": 1,
                "start": 0.0,
                "end": 5.5,
                "content": "Hello world"
            }
        ],
        "language": "en",
        "error": null
    }
    """
    global service

    # 确保服务已初始化
    if service is None:
        try:
            initialize_service()
        except Exception as e:
            return (
                jsonify(
                    {
                        "success": False,
                        "subtitles": [],
                        "language": "",
                        "error": f"服务初始化失败: {str(e)}",
                    }
                ),
                500,
            )

    # 检查是否有文件上传
    if "file" not in request.files:
        return (
            jsonify(
                {
                    "success": False,
                    "subtitles": [],
                    "language": "",
                    "error": "未提供音频文件",
                }
            ),
            400,
        )

    file = request.files["file"]

    # 检查文件名
    if file.filename == "":
        return (
            jsonify(
                {
                    "success": False,
                    "subtitles": [],
                    "language": "",
                    "error": "未选择文件",
                }
            ),
            400,
        )

    # 检查文件扩展名
    if not allowed_file(file.filename):
        return (
            jsonify(
                {
                    "success": False,
                    "subtitles": [],
                    "language": "",
                    "error": "不支持的文件格式",
                }
            ),
            400,
        )

    # 获取可选参数
    language = request.form.get("language", None)
    model_size = request.form.get("model_size", None)

    # 创建临时文件
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp:
            file.save(tmp.name)
            temp_audio_path = tmp.name

        # 如果指定了不同的模型大小，需要重新初始化服务
        if model_size and model_size != service.model_size:
            try:
                service = TranscriptionService(model_size=model_size)
            except Exception as e:
                return (
                    jsonify(
                        {
                            "success": False,
                            "subtitles": [],
                            "language": "",
                            "error": f"模型加载失败: {str(e)}",
                        }
                    ),
                    500,
                )

        # 执行转录
        result = service.transcribe(temp_audio_path, language)

        # 清理临时文件
        try:
            os.unlink(temp_audio_path)
        except Exception as e:
            logger.warning(f"无法删除临时文件 {temp_audio_path}: {e}")

        # 返回结果
        return jsonify(
            {
                "success": result.success,
                "subtitles": result.subtitles,
                "language": result.language,
                "error": result.error,
            }
        )

    except Exception as e:
        # 确保清理临时文件
        try:
            if "temp_audio_path" in locals():
                os.unlink(temp_audio_path)
        except:
            pass

        logger.error(f"转录请求处理失败: {e}")
        return (
            jsonify(
                {"success": False, "subtitles": [], "language": "", "error": str(e)}
            ),
            500,
        )


@app.route("/transcribe/srt", methods=["POST"])
def transcribe_to_srt():
    """
    转录音频并直接返回SRT文件

    POST /transcribe/srt
    Content-Type: multipart/form-data

    Form data:
    - file: 音频文件
    - language: 可选，音频语言
    - model_size: 可选，模型大小
    """
    global service

    # 确保服务已初始化
    if service is None:
        try:
            initialize_service()
        except Exception as e:
            return (
                jsonify({"success": False, "error": f"服务初始化失败: {str(e)}"}),
                500,
            )

    # 检查是否有文件上传
    if "file" not in request.files:
        return jsonify({"success": False, "error": "未提供音频文件"}), 400

    file = request.files["file"]

    # 检查文件名
    if file.filename == "":
        return jsonify({"success": False, "error": "未选择文件"}), 400

    # 检查文件扩展名
    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "不支持的文件格式"}), 400

    # 获取可选参数
    language = request.form.get("language", None)
    model_size = request.form.get("model_size", None)

    # 创建临时文件
    try:
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp:
            file.save(tmp.name)
            temp_audio_path = tmp.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as tmp_srt:
            temp_srt_path = tmp_srt.name

        # 如果指定了不同的模型大小，需要重新初始化服务
        if model_size and model_size != service.model_size:
            try:
                service = TranscriptionService(model_size=model_size)
            except Exception as e:
                return (
                    jsonify({"success": False, "error": f"模型加载失败: {str(e)}"}),
                    500,
                )

        # 执行转录并保存为SRT
        success = service.transcribe_to_srt(temp_audio_path, temp_srt_path, language)

        # 清理临时文件
        try:
            os.unlink(temp_audio_path)
        except Exception as e:
            logger.warning(f"无法删除临时音频文件 {temp_audio_path}: {e}")

        if success:
            # 返回SRT文件
            return send_file(
                temp_srt_path,
                as_attachment=True,
                download_name=f"transcription_{os.path.splitext(file.filename)[0]}.srt",
                mimetype="text/srt",
            )
        else:
            try:
                os.unlink(temp_srt_path)
            except:
                pass
            return jsonify({"success": False, "error": "转录失败"}), 500

    except Exception as e:
        # 确保清理临时文件
        try:
            if "temp_audio_path" in locals():
                os.unlink(temp_audio_path)
        except:
            pass
        try:
            if "temp_srt_path" in locals():
                os.unlink(temp_srt_path)
        except:
            pass

        logger.error(f"SRT转录请求处理失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    # 从环境变量获取端口，默认5000
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
