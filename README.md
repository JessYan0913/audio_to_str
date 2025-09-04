# Audio to SRT 字幕转换工具

将音频文件转换为 SRT 字幕文件的工具，使用 OpenAI 的 Whisper 语音识别模型实现音频转文字和时间戳生成。

## 功能特点

- 音频转文字：使用 Whisper 模型将音频内容转换为文本
- 时间戳生成：为识别出的文本生成精确的时间戳
- SRT 格式输出：将识别结果导出为标准的 SRT 字幕文件
- 多语言支持：自动检测音频语言或指定特定语言

## 环境要求

- Python 3.10 或更高版本
- uv 包管理器（推荐）

## 使用 uv 启动项目（推荐方式）

[uv](https://github.com/astral-sh/uv) 是一个极速的 Python 包管理器和项目管理工具，可以显著提高依赖安装速度。

### 安装 uv

```bash
# 使用 pip 安装
pip install uv

# 或者使用包管理器安装（如 brew）
brew install uv
```

### 克隆和初始化项目

```bash
# 克隆项目
git clone <repository-url>
cd audio_to_srt

# 使用 uv 安装依赖
uv pip install .
```

### 运行项目

```bash
# 使用 uv 直接运行（推荐）
uv run python main.py

# 或者激活虚拟环境后运行
uv venv
source .venv/bin/activate  # Linux/macOS
python main.py
```

## 传统方式安装和运行

### 安装依赖

```bash
pip install -r requirements.txt
```

或者直接安装项目依赖：

```bash
pip install openai-whisper srt requests
```

### 运行项目

```bash
python main.py
```

## 使用说明

1. 将音频文件放置在项目目录中
2. 修改 [main.py](file:///Users/yanheng/Documents/work/audio_to_srt/main.py) 中的 `audio_path` 变量，指向你的音频文件路径
3. 运行程序：`uv run python main.py` 或 `python main.py`
4. 程序将在当前目录生成 `output_subtitles.srt` 字幕文件

## 配置说明

在 [main.py](file:///Users/yanheng/Documents/work/audio_to_srt/main.py) 中可以配置以下参数：

- `audio_path`: 音频文件路径
- `output_srt_path`: 输出 SRT 文件路径
- `language`: 指定音频语言（可选，设为 None 时自动检测）

## 依赖说明

- `openai-whisper`: OpenAI 开发的语音识别模型
- `srt`: SRT 字幕文件处理库
- `requests`: HTTP 请求库，用于下载音频文件