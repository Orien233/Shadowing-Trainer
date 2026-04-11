# Shadowing Trainer V0.2

本项目是一个本地运行的英语 Shadowing 练习工具，支持从素材导入到跟读评估的完整流程。

## 功能概览

- 导入音频/视频素材
- 自动抽取音频并转写（Whisper）
- 自动切句与翻译（DeepSeek，可降级）
- 逐句播放 + 跟读录音
- 跟读评分（完整度、流畅度、同步度、发音）
- 视频播放联动练习区（V0.2 新增）

## V0.2 更新重点

### 1) 练习区增加视频播放器

- 对于视频素材，在右侧练习区上方显示视频窗口。
- 视频源接口：`GET /api/materials/{material_id}/video`

### 2) 视频与音频进度双向同步

- 练习区音频时间轴会驱动视频进度。
- 拖动视频进度条会同步更新下方音频练习进度。
- 逐句播放、上一句/下一句跳转都会落到同一条时间轴。

### 3) 句子级音频映射数据入库

每条句子在素材处理阶段会额外记录：

- `original_start_time`：在原始媒体中的起始时间
- `original_end_time`：在原始媒体中的结束时间
- `clip_audio_path`：拆分后的句子音频路径
- `clip_duration`：拆分音频的实际时长（ffprobe）

这些字段用于实现“原始视频时间轴 <-> 练习区音频时间轴”的精准跳转。

## 技术栈

### 后端

- Python 3.10+
- FastAPI
- SQLModel + SQLite
- faster-whisper
- FFmpeg / ffprobe
- librosa / soundfile
- httpx

### 前端

- React
- TypeScript
- Vite

## 环境准备

### 1) 安装 FFmpeg

先确认命令可用：

```bash
ffmpeg -version
ffprobe -version
```

Windows 推荐：

```bash
winget install Gyan.FFmpeg
```

### 2) 安装 PyTorch（可选，启用 CUDA 加速）

faster-whisper 依赖 PyTorch。可选安装 CUDA 版本以加速音频转写。

**纯 CPU 模式（慢但无需 GPU）：**
```bash
pip install torch torchvision torchaudio
```

**CUDA 12.1 模式（需 NVIDIA GPU）：**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

查看 CUDA 版本：
```bash
nvidia-smi  # 查看驱动和 CUDA 版本
```

> 注：cu121 与 CUDA 13.x 向后兼容。如需其他版本，see [PyTorch 官网](https://pytorch.org)

## 快速启动

### 1) 启动后端

```bash
cd backend
python -m venv .venv
```

Windows PowerShell 激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

Windows CMD 激活：

```bat
.venv\Scripts\activate.bat
```

macOS/Linux 激活：

```bash
source .venv/bin/activate
```

安装依赖并启动：

```bash
pip install -r requirements.txt
# 如需加速，再安装 PyTorch CUDA 版本（见"环境准备"章节）

copy .env.example .env   # Windows，可手动复制
# 编辑 .env，根据配置选择 CPU 或 CUDA 模式
uvicorn app.main:app --reload --port 8000
```

**配置说明（.env）：**
```ini
# CPU 模式（默认，慢但兼容性好）
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8

# CUDA 模式（需配置 PyTorch，快速但需 GPU）
WHISPER_DEVICE=cuda
WHISPER_COMPUTE_TYPE=float16  # 8GB+ GPU；如显存不足改用 int8 或 int8_float16

# 翻译API并发数（避免触发速率限制）
TRANSLATION_CONCURRENCY=5  # 建议值: 2-10，根据API限制调整
```

### 2) 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认地址：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`

## 数据目录

后端默认使用 `backend/data`：

- `materials/`：原始上传文件
- `audio/`：素材抽取后的统一音频
- `audio/sentences/material_{id}/`：句子拆分音频（V0.2 新增）
- `recordings/`：用户跟读录音
- `app.db`：SQLite 数据库

## 数据库与迁移说明

V0.2 在 `sentence` 表新增以下列：

- `original_start_time`
- `original_end_time`
- `clip_audio_path`
- `clip_duration`

应用启动时会自动执行轻量迁移（`ALTER TABLE`），并回填历史数据基础值。

> 建议：旧素材可点击“重新处理”一次，以生成完整的句子拆分音频和精确时长。

## 核心接口

### 素材

- `POST /api/materials/upload`
- `GET /api/materials`
- `GET /api/materials/{material_id}`
- `POST /api/materials/{material_id}/process`
- `GET /api/materials/{material_id}/audio`
- `GET /api/materials/{material_id}/video`（V0.2 新增）

### 句子

- `GET /api/materials/{material_id}/sentences`

### 录音与评估

- `POST /api/recordings/upload`
- `GET /api/evaluations/{evaluation_id}`
- `DELETE /api/recordings/cleanup`

## .env 示例

```env
APP_NAME=Shadowing Trainer
DEBUG=true
HOST=0.0.0.0
PORT=8000

CORS_ORIGINS=http://localhost:5173

DATA_DIR=./data
WHISPER_MODEL=small
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8

DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_KEY=
```

## 注意事项

- 首次运行 faster-whisper 可能下载模型，耗时较长。
- `DEEPSEEK_API_KEY` 为空时，翻译会走降级逻辑。
- 当前评分为练习反馈用途，不是考试级语音测评。
