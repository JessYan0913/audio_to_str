#!/bin/bash

# Audio to SRT 源码启动脚本
# 用于在 Ubuntu 系统上直接从源码启动应用

set -e

echo "=== Audio to SRT 源码启动脚本 ==="

# 检查 Python 版本
echo "检查 Python 版本..."
python_version=$(python3 --version | grep -oP 'Python \K\d+\.\d+')
if [[ $(echo "$python_version < 3.10" | bc -l) -eq 1 ]]; then
    echo "错误：需要 Python 3.10 或更高版本，当前版本：$python_version"
    exit 1
fi
echo "Python 版本检查通过：$python_version"

# 更新包列表
echo "更新包列表..."
sudo apt-get update

# 安装系统依赖
echo "安装系统依赖..."
sudo apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    python3-pip \
    curl

# 安装 uv 包管理器（如果未安装）
if ! command -v uv &> /dev/null; then
    echo "安装 uv 包管理器..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# 激活虚拟环境（可选）
echo "创建并激活虚拟环境..."
uv venv --python python3.10
source .venv/bin/activate

# 安装 Python 依赖
echo "安装 Python 依赖..."
uv pip install -e .

# 设置环境变量
export WHISPER_MODEL_SIZE=${WHISPER_MODEL_SIZE:-small}
export PORT=${PORT:-8000}
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUNBUFFERED=1
export HF_HOME=${HF_HOME:-$HOME/.cache/huggingface}

echo "环境变量设置完成："
echo "  - WHISPER_MODEL_SIZE: $WHISPER_MODEL_SIZE"
echo "  - PORT: $PORT"
echo "  - HF_HOME: $HF_HOME"

# 创建必要的目录
mkdir -p "$HOME/.cache/huggingface"

# 启动应用
echo "启动 Audio to SRT Web 服务..."
echo "服务将在 http://localhost:$PORT 启动"
echo "服务将在后台运行，终端关闭后服务将继续运行"
echo "日志将输出到 nohup.out 文件"
echo "要停止服务，请使用 kill 命令或重启系统"
echo ""

nohup uvicorn src.app:app --host 0.0.0.0 --port $PORT --reload &
echo "服务已启动，进程 ID: $!"
