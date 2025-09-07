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
    && uv pip install --system -e . \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
COPY . .

RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

EXPOSE $PORT
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port $PORT"]
