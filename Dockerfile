FROM python:3.10

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WHISPER_MODEL_SIZE=small \
    PORT=5001

# 安装系统依赖和 pip
RUN apt-get update && apt-get install -y \
        build-essential \
        libsndfile1 \
        ffmpeg \
    && pip install --no-cache-dir uv \
    && rm -rf /var/lib/apt/lists/*

# 复制项目配置文件
COPY pyproject.toml uv.lock ./

# 复制源码到 /app/src
COPY src ./src

# 安装项目依赖 (editable install)
RUN uv pip install --system -e .

# 创建非特权用户
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

EXPOSE $PORT

# 启动 uvicorn 服务
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "5001"]
