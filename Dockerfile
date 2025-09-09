# Builder 阶段：安装依赖和构建应用
FROM python:3.10-slim AS builder

WORKDIR /app

# 安装系统依赖（仅构建时需要）
# 注意：移除 build-essential 和 git 以避免网络下载问题
# uv 可以直接安装 Python 包，通常不需要编译工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
RUN pip install --no-cache-dir uv

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY src ./src

# 安装项目依赖到系统 Python
RUN uv pip install --system -e .

# Runtime 阶段：最小化运行时镜像
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WHISPER_MODEL_SIZE=small \
    PORT=8000 \
    HF_HOME=/home/app/.cache/huggingface

# 安装运行时系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends --fix-missing \
        libsndfile1 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 阶段复制已安装的 Python 包
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 复制应用源代码
COPY src ./src

# 创建非特权用户
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app /home/app

USER app

EXPOSE $PORT

CMD ["sh", "-c", "uvicorn src.app:app --host 0.0.0.0 --port $PORT"]
