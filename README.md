# Shadowing Trainer v0.3.1

## v0.4: AI text and configurable model providers

The v0.4 project lives in `shadowing_v0_3_1/`. It adds an OpenAI-compatible
provider layer while preserving the existing upload, sentence training,
recording, scoring, word collection, and durable-job workflows.

- **Audio provider contract:** TTS and ASR use OpenAI Audio API request shapes
  (`/audio/speech`, `/audio/transcriptions`) as a common baseline, while the
  application exposes its own `AudioCapability`, `TTSResult`, and `ASRResult`.
  Azure Speech and cached Local Whisper are adapters behind that contract.
- **Provider types currently implemented:** OpenAI-compatible LLM/TTS/remote
  ASR, Azure Speech TTS/ASR, and cached Local Whisper for local ASR.
- **Configuration:** open **Settings** in the application, add an enabled
  provider for LLM/TTS/ASR, then mark one provider per capability as default.
  API keys are stored only by the backend and the list API/UI returns a masked
  value. A blank API-key update keeps the previous key.
- **ASR scene switches:** *Use Local Whisper for material transcription*
  affects uploaded material processing. *Use Local Whisper for recording
  evaluation* affects learner speech scoring. Turning either switch off uses
  the default enabled remote ASR provider and returns a clear error if one has
  not been configured.
- **AI Text:** choose random or manual collected words, select a preset/custom
  topic, language, difficulty and length, then generate and edit the text.
  You can instead paste your own text. Choose TTS speed/voice and create a
  sentence-level TTS practice; on completion it opens in the existing training
  page just like an uploaded material.

Copy `backend/.env.example` to `backend/.env` for local runtime settings. The
legacy `DEEPSEEK_*` values remain a translation compatibility fallback; new
provider credentials should be entered in Settings.

Shadowing Trainer 是一款本地优先（local-first）的英语口语跟读训练 Web 应用。  
它支持从素材上传到句级练习、录音与评分的完整流程。

## 版本日志（v0_3_2）

### 2026-07-15（v0.3.2）

- **持久化任务队列**：录音评分与素材处理均改为 SQLite 任务；上传接口立即返回任务 ID，可通过 `GET /api/jobs/{job_id}` 查询进度、错误和结果，失败任务可手动重试。
- **一致性与迁移**：评分快照已合并到 `app.db`，移除运行时双 SQLite 写入；新增 Alembic 迁移，旧的 `score_history.db` 保留但不导入。
- **媒体安全与视频管线**：上传采用流式 `.part` 写入和 ffprobe 校验；录音限制 90 秒/25 MiB。视频先转码为 `data/videos` 内的 ≤150 MiB MP4，再提取 Whisper 用音频，成功后删除原视频。
- **练习体验**：录音面板支持权限错误、倒计时自动停止、试听、重录、任务进度与评分重试；前端 API 地址支持 `VITE_API_BASE`。

## 版本日志（v0_3_1）

以下日志覆盖 `v0_3_1` 分支的主要变更。

### 2026-04-27（v0.3.1）

- **新增词级对齐反馈**：
  - 新增 `backend/app/services/word_alignment_service.py`，对目标句与用户 ASR 文本做词级对齐。
  - 支持识别正确、近似错误、替换、漏读、插入、重复与 filler 词，并计算 `word_accuracy`。
  - 评测结果的 `raw_metrics` 中新增 `word_alignment`，便于前端展示和后续分析。
- **评分历史支持词级结果回填**：
  - `Evaluation`、`SentenceLatestEvaluationRead` 与最新评分接口会返回 `word_alignment`。
  - 重新进入素材训练页时，可从每句最新评分快照恢复词级反馈。
- **前端新增高亮展示**：
  - 新增 `HighlightedSentence`、`WordAlignmentView` 与 `alignmentColors`，在训练页和评估面板中高亮用户识别结果。
  - 训练句文本可根据上一轮评估结果标注漏读、替换等问题，帮助定位具体错误词。
- **切句与媒体边界更精细**：
  - ASR 处理支持 word timestamps。
  - 切句时记录有效单词边界，并在生成句子音频片段时优先使用词边界加 padding，减少片段首尾静音或截断。
- **测试与仓库维护**：
  - 新增 `backend/tests/test_word_alignment_service.py` 覆盖精确匹配、漏读、插入、filler、替换与空文本场景。
  - `.gitignore` 更新为忽略 `shadowing_v0_3_1/backend/data/` 与前端 TypeScript 构建缓存。

### 2026-04-13（v0.3）

- **评测链路新增静音裁剪（VAD）预处理**：
  - 新增 `backend/app/services/vad_service.py`，基于 `librosa.effects.split` 检测有效语音区间，并支持前后 padding、最短时长兜底和失败回退。
  - `evaluation_service` 改为优先使用裁剪后音频参与 ASR、模仿度分支和韵律分支计算，评测结束后自动清理临时裁剪文件。
- **评测结果可观测性增强**：
  - `raw_metrics` 增加 `vad` 元数据。
  - 评测标签合并逻辑优化，能同时保留 VAD 标签与原有诊断标签。
- **配置与测试运行配置补充**：
  - `config.py` 新增 `enable_trim_silence` 和 `trim_*` 参数及校验规则。
  - 新增 `backend/pytest.ini`，并在 `.gitignore` 补充 pytest 运行期目录忽略项。

### 2026-04-13（5fa70a4）评分结果数据系统

- **新增评分结果快照子系统**：
  - 新增 `score_database.py`、`material_sentence_score` 模型、对应 schema 与 service。
  - 录音上传评测完成后，按素材/句子落库保存最新评分快照。
- **后端接口扩展**：
  - 新增 `GET /api/materials/{material_id}/latest-evaluations`，用于按素材拉取每句最新评分。
  - 删除素材时同步清理对应评分快照数据。
  - 评分快照不可用时，支持从主库评测表回退读取。
- **前端联动**：
  - 新增最新评分相关类型与 API 封装。
  - 素材加载时并发拉取句子与最新评分，在训练页回填历史评分结果。

### 2026-04-13（41bf5c8）已知问题修复

- **媒体处理与切句稳定性增强**：
  - `media_service` 重构切片边界计算，补齐最小时长、边界夹紧与相邻片段防重叠处理。
  - 媒体类型检测改为基于 `ffprobe` 流信息，提升音视频识别鲁棒性。
- **训练页行为修复**：
  - `SentenceTrainer` 时间轴构建与同步逻辑优化，音频/视频模式下定位与回放更稳定。
  - 媒体加载失败提示更明确，减少“处理成功但无法播放”的误判。

### 2026-04-13（40ffc0b）仓库清理

- 清理误提交和冗余文件，减少仓库噪音。
- 调整忽略规则，避免测试运行临时文件再次进入版本控制。

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
- 支持词级对齐反馈，标出漏读、替换、插入、重复和 filler 词。
- 支持每句最新评分与词级反馈快照回填。
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
shadowing_v0_3_1/
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
cd shadowing_v0_3_1/backend
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

首次启动前或部署升级时执行：

```bash
alembic upgrade head
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
cd shadowing_v0_3_1/frontend
npm install
npm run dev
```

默认本地地址：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`

## 环境变量（`backend/.env`）

```env
APP_NAME=Shadowing Trainer
APP_VERSION=0.3.1
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

ENABLE_WAVLM_SCORE=true
ENABLE_PROSODY_SCORE=true
ENABLE_TRIM_SILENCE=true
EVAL_WEIGHT_CONTENT=0.40
EVAL_WEIGHT_IMITATION=0.35
EVAL_WEIGHT_PROSODY=0.25
TRIM_TOP_DB=30
TRIM_PAD_SEC=0.20
TRIM_MIN_DURATION_SEC=0.30
```

## 数据存储

后端运行期数据位于 `backend/data`：

- `materials/` 原始上传文件
- `audio/` 标准化后的整段音频
- `audio/sentences/material_{id}/` 句子切片 WAV 文件
- `recordings/` 用户录音文件及其转换产物
- `app.db` SQLite 数据库
- `videos/` 视频转码产物（最多 150 MiB）

## 数据库说明

启动时会自动执行轻量级 schema 迁移。  
当前迁移包含新增的句子字段：

- `original_start_time`
- `original_end_time`
- `clip_audio_path`
- `clip_duration`
- `raw_metrics.word_alignment` 中保存词级对齐结果。

旧数据行会以安全默认值进行回填。

## API 概览

### 素材（Materials）

- `POST /api/materials/upload`
- `GET /api/materials`
- `GET /api/materials/{material_id}`
- `POST /api/materials/{material_id}/process`
- `DELETE /api/materials/{material_id}`
- `GET /api/materials/{material_id}/latest-evaluations`
- `GET /api/materials/{material_id}/audio`
- `GET /api/materials/{material_id}/video`

### 句子（Sentences）

- `GET /api/materials/{material_id}/sentences`

### 录音与评估（Recordings & Evaluation）

- `POST /api/recordings/upload`
- `DELETE /api/recordings/cleanup`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/retry`
- `GET /api/evaluations/{evaluation_id}`

### 系统（System）

- `POST /api/system/shutdown`

## 备注

- 首次运行 `faster-whisper` 可能会下载模型文件，耗时会更长。
- 若 `DEEPSEEK_API_KEY` 为空，翻译会回退为占位提示信息。
- 本评分流程用于练习反馈，不适用于考试等语言能力评估场景。
