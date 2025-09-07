# 使用 Python 3.10 基础镜像
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WHISPER_MODEL_SIZE=small \
    PORT=5001

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY pyproject.toml uv.lock ./
COPY . .

# 安装 Python 依赖（使用清华源加速）
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple uv && \
    uv pip install --system -e .

# 创建非特权用户
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# 暴露端口
EXPOSE $PORT

# 启动命令
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "$PORT"]