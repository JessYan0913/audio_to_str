# Audio to SRT 转换器

一个将音频文件转换为SRT字幕的工具，支持命令行和API两种调用方式。

## 功能特性

- 支持多种音频格式（mp3, wav, m4a, ogg, flac）
- 自动语言检测
- GPU加速（如果可用）
- 支持命令行和HTTP API调用
- 大模型支持（支持Whisper的base, small, medium, large等模型）

## 安装

```bash
# 使用uv安装依赖（推荐）
uv pip install -e .
```

## 使用方式

### 1. 命令行使用

```bash
# 转换本地音频文件
python main.py --audio path/to/audio.mp3 --output subtitles.srt

# 转换远程音频文件
python main.py --audio https://example.com/audio.mp3 --output subtitles.srt

# 指定语言
python main.py --audio audio.mp3 --output subtitles.srt --language en

# 使用不同大小的模型
python main.py --audio audio.mp3 --output subtitles.srt --model medium
```

### 2. API 使用

启动API服务：

```bash
python app.py
```

服务将运行在 `http://localhost:5000`

#### API 端点

- `GET /health` - 健康检查
- `POST /transcribe` - 创建异步转录任务，返回任务ID
- `GET /tasks/<task_id>` - 查询任务状态
- `POST /transcribe/srt` - 创建异步SRT转录任务，返回任务ID
- `GET /tasks/<task_id>/download` - 下载已完成的SRT文件
- `DELETE /tasks/<task_id>/cleanup` - 清理任务临时文件

#### 示例：使用curl调用API

```bash
# 创建转录任务
curl -X POST http://localhost:5000/transcribe \
  -F "file=@audio.mp3" \
  -F "language=en" \
  -F "model_size=medium"

# 响应示例
{
  "task_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "processing",
  "message": "转录任务已创建，可通过 /tasks/<task_id> 查询状态"
}

# 查询任务状态
curl -X GET http://localhost:5000/tasks/123e4567-e89b-12d3-a456-426614174000

# 创建SRT转录任务
curl -X POST http://localhost:5000/transcribe/srt \
  -F "file=@audio.mp3" \
  -F "language=en"

# 下载已完成的SRT文件
curl -X GET http://localhost:5000/tasks/123e4567-e89b-12d3-a456-426614174000/download \
  -o subtitles.srt

# 清理任务
curl -X DELETE http://localhost:5000/tasks/123e4567-e89b-12d3-a456-426614174000/cleanup
```

#### JSON响应示例

```json
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
```

## 配置

可以通过环境变量进行配置：

- `PORT`: API服务端口（默认5000）
- `WHISPER_MODEL_SIZE`: 默认模型大小（默认large-v3）
- `MAX_CONTENT_LENGTH`: 最大上传文件大小（默认100MB）

## 项目结构

```
.
├── main.py            # 命令行入口
├── app.py             # API服务
├── transcription_service.py  # 核心转录服务
├── pyproject.toml     # 项目依赖
└── README.md          # 项目文档
```

## 依赖

- Python 3.8+
- Flask
- Whisper
- torch
- requests
- srt

## Docker 部署

本项目提供完整的Docker部署支持，包含Dockerfile和docker-compose.yml配置文件。

### 构建和运行Docker容器

```bash
# 构建镜像
docker build -t audio-to-srt .

# 运行容器
docker run -p 5001:5001 audio-to-srt
```

### 使用Docker Compose

```bash
# 启动服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### Docker 环境变量

可以通过环境变量配置Docker容器：

```bash
# 创建 .env 文件
echo "PORT=5001
WHISPER_MODEL_SIZE=small
MAX_WORKERS=4" > .env

# 使用环境变量启动
docker-compose up -d
```

### Docker Compose 配置说明

- 服务名称: `audio-to-srt`
- 映射端口: `${PORT:-5001}:5001` (默认5001)
- 环境变量: 
  - `WHISPER_MODEL_SIZE`: 模型大小 (默认small)
  - `MAX_WORKERS`: 最大工作进程数 (默认4)
- 数据卷: 将本地logs目录挂载到容器内，用于持久化日志
- 重启策略: `unless-stopped`
- 健康检查: 每30秒检查一次 `/health` 端点

### 生产环境建议

1. **模型选择**: 根据硬件资源选择合适的模型大小
   - `tiny/small`: 适合CPU环境
   - `medium/large`: 需要GPU支持，提供更高精度

2. **资源限制**: 在docker-compose.yml中添加资源限制

```yaml
services:
  audio-to-srt:
    # ... 其他配置
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
```

3. **持久化存储**: 确保日志和临时文件有足够空间

4. **监控**: 配置外部监控系统监控容器健康状态

## 许可证

MIT