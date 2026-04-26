# Shadowing Trainer v0.2（此分支停止更新）

Shadowing Trainer 是一款本地优先（local-first）的英语口语跟读训练 Web 应用。  
它支持从素材上传到句级练习、录音与评分的完整流程。

## 变更摘要（v0_2 分支）

本分支包含以下主要更新：

### 新增功能

- **素材上传后自动触发处理**：
  - 上传成功后会尝试自动进入 `processing`。
  - 前端上传组件会自动调用处理接口。
  - 后端上传接口也会尝试抢占处理锁并启动后台任务。
- **素材安全删除（级联清理 + 文件清理）**：
  - 新增 `DELETE /api/materials/{material_id}`。
  - 级联删除关联的 `sentence` / `recording` / `evaluation` 数据。
  - 取消进行中的处理任务。
  - 安全删除原始素材、统一音轨、切句音频目录、录音产物等。
  - 带有“仅允许删除 `data` 目录内文件”的安全保护。
- **素材操作菜单**：
  - 素材列表每项新增 “...” 菜单。
  - 支持 `Start Processing` / `Reprocess` / `Delete`。
  - 展示 `Processing` / `Deleting` 状态。
- **删除后的选中项兜底**：
  - 删除当前选中的素材后，自动切换到列表第一个素材；若列表为空则置空选中项。
- **分句训练时间轴增强**：
  - 时间轴按“句子段 + 静音空白段（gap）”构建。
  - 支持 gap 段导航。
  - 支持 `Auto Play`（自动播下一段）与 `Loop Segment`（单段循环），两者互斥。
  - 在 gap 段自动隐藏录音/评分面板。
- **视频训练体验增强**：
  - 练习页内嵌视频播放器。
  - 视频播放进度与分段时间轴双向同步（拖动/播放/倍速都同步）。

### UI 改动项

- **素材区**：
  - 列表项由“按钮式操作”改为“菜单式操作”。
  - 新增 `Processing/Deleting` 文案。
  - 列表布局对齐方式调整，更适配多行内容。
- **上传区 / 列表区**：
  - 标题去掉步骤编号（如“1/2/4”）。
- **练习区**：
  - 进度条改为“当前段内进度”。
  - 新增 `Global Position`（全局时间）提示。
  - 遇到静音段时显示 `[Silent Segment]` 提示与说明文案。
- **样式增强**：
  - 新增下拉菜单样式（浮层、阴影、危险操作红色）。
  - 新增视频容器 16:9 自适应框（`object-fit: contain`）。
  - 整体交互风格更偏“卡片 + 操作菜单”。

### 文档

- `README.md` 放在仓库根目录维护。
- 文档补充了 v0_2 变更摘要、Quick Start、API 列表（包含新增 `DELETE` 接口）。

## 核心功能

- 上传音频或视频素材。
- 自动提取并标准化音频为 WAV（16kHz、单声道）。
- 使用 `faster-whisper` 进行 ASR 转写。
- 基于 ASR 输出进行句子切分。
- 通过 DeepSeek API 将句子翻译为简体中文。
- 支持句级播放与时间轴拖拽定位。
- 上传录音并自动评分：
  - 完整度（Completeness）
  - 流利度（Fluency）
  - 同步度（Sync）
  - 发音（Pronunciation）
- 支持对已有素材重新处理。
- 支持素材级删除与数据/文件清理。

## 架构

### 后端

- Python 3.10+
- FastAPI
- SQLModel + SQLite
- `faster-whisper`
- FFmpeg / ffprobe
- librosa + soundfile
- httpx（用于 DeepSeek 翻译请求）

### 前端

- React 18
- TypeScript
- Vite

## 项目结构

```text
shadowing_v0_2/
  backend/
    app/
    data/                 # 运行期数据（git 忽略）
    requirements.txt
    .env                  # 本地配置（不提交）
  frontend/
    src/
  README.md
```

## 运行前准备

1. Python 3.10 或更高版本 （测试使用3.12）
2. Node.js 18+ 与 npm
3. `PATH` 中可用 FFmpeg 与 ffprobe

验证 FFmpeg：

```bash
ffmpeg -version
ffprobe -version
```

可选：若需启用 Whisper 的 GPU 加速，需要安装支持 CUDA 的 PyTorch。

## 快速开始

### 1) 配置后端

```bash
cd shadowing_v0_2/backend
python -m venv .venv
```

激活虚拟环境：

- PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

- CMD：

```bat
.venv\Scripts\activate.bat
```

- macOS/Linux：

```bash
source .venv/bin/activate
```

安装后端依赖：

```bash
pip install -r requirements.txt
```

安装 PyTorch（任选其一）：

- CPU：

```bash
pip install torch torchvision torchaudio
```

- CUDA 12.1：

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

创建 `backend/.env`（示例见下文），然后启动后端：

```bash
uvicorn app.main:app --reload --port 8000
```

### 2) 配置前端

```bash
cd shadowing_v0_2/frontend
npm install
npm run dev
```

默认本地地址：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`

## 环境变量（`backend/.env`）

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

TRANSLATION_CONCURRENCY=5
TRANSLATION_REQUEST_TIMEOUT_SECONDS=60
TRANSLATION_MAX_RETRIES=2
TRANSLATION_RETRY_BASE_SECONDS=0.8
TRANSLATION_MAX_CONNECTIONS=200
TRANSLATION_MAX_KEEPALIVE_CONNECTIONS=50

PROCESSING_LOCK_TIMEOUT_SECONDS=1800
PROCESSING_LOCK_HEARTBEAT_SECONDS=10
```

## 数据存储

后端运行期数据位于 `backend/data`：

- `materials/` 原始上传文件
- `audio/` 标准化后的整段音频
- `audio/sentences/material_{id}/` 句子切片 WAV 文件
- `recordings/` 用户录音文件及其转换产物
- `app.db` SQLite 数据库

## 数据库说明

启动时会自动执行轻量级 schema 迁移。  
当前迁移包含新增的句子字段：

- `original_start_time`
- `original_end_time`
- `clip_audio_path`
- `clip_duration`

旧数据行会以安全默认值进行回填。

## API 概览

### 素材（Materials）

- `POST /api/materials/upload`
- `GET /api/materials`
- `GET /api/materials/{material_id}`
- `POST /api/materials/{material_id}/process`
- `DELETE /api/materials/{material_id}`
- `GET /api/materials/{material_id}/audio`
- `GET /api/materials/{material_id}/video`

### 句子（Sentences）

- `GET /api/materials/{material_id}/sentences`

### 录音与评估（Recordings & Evaluation）

- `POST /api/recordings/upload`
- `DELETE /api/recordings/cleanup`
- `GET /api/evaluations/{evaluation_id}`

### 系统（System）

- `POST /api/system/shutdown`

## 备注

- 首次运行 `faster-whisper` 可能会下载模型文件，耗时会更长。
- 若 `DEEPSEEK_API_KEY` 为空，翻译会回退为占位提示信息。
- 本评分流程用于练习反馈，不适用于考试等语言能力评估场景。
