FROM python:3.10

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WHISPER_MODEL_SIZE=small \
    PORT=8000 \
    HF_HOME=/home/app/.cache/huggingface

# 安装系统依赖和 pip
RUN apt-get update && apt-get install -y \
        build-essential \
        libsndfile1 \
        ffmpeg \
        git \
    && pip install --no-cache-dir uv huggingface_hub \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY src ./src

# 安装项目依赖
RUN uv pip install --system -e .

# 下载 faster-whisper 模型（放到 Hugging Face 默认缓存目录）
RUN huggingface-cli download Systran/faster-whisper-small --local-dir ${HF_HOME}/hub/models--Systran--faster-whisper-small

# 创建非特权用户
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app /home/app
USER app

EXPOSE $PORT

CMD ["sh", "-c", "uvicorn src.app:app --host 0.0.0.0 --port $PORT"]
