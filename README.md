# Shadowing Trainer v0.2

本仓库是一个可本地部署的英语 Shadowing 训练工具，覆盖「素材上传 → 转写切句 → 翻译 → 逐句播放 → 跟读录音 → 自动评分」完整闭环。

---

## 1. 项目概览

### 1.1 你可以用它做什么

- 上传音频或视频素材（`audio/*, video/*`）
- 后端自动抽取统一音轨（wav）并进行 Whisper 转写
- 基于标点+时长规则自动切句
- 逐句调用翻译（DeepSeek，可降级到原文）
- 在前端进行逐句播放、跳句、单句循环
- 录音后自动获得完整度/流畅度/同步度/发音等评分

### 1.2 技术栈

**后端**

- FastAPI
- SQLModel + SQLite
- faster-whisper
- FFmpeg / ffprobe
- librosa / soundfile
- httpx

**前端**

- React 18
- TypeScript
- Vite

---

## 2. 本次更新内容（基于代码实现总结）

> 以下为本次 v0.2 中最关键、且已在代码中落地的更新点。

### 2.1 练习区新增视频联动播放（针对视频素材）

- 新增视频流接口：`GET /api/materials/{material_id}/video`
- 素材为 `video` 类型时，练习区展示视频播放器
- 视频与音频在播放/暂停状态保持联动

### 2.2 建立统一时间轴：音频、视频、句子三方同步

- 句子优先使用 `original_start_time / original_end_time` 做定位
- 拖动视频进度会同步更新音频与当前句索引
- 拖动下方时间轴也会同时更新音频与视频位置
- 上一句/下一句、播放当前句都落在同一条时间轴上

### 2.3 句子级音频元数据入库，支持精准跳转与评分时长

`sentence` 表新增字段并在处理阶段填充：

- `original_start_time`：句子在原始媒体中的起始时间
- `original_end_time`：句子在原始媒体中的结束时间
- `clip_audio_path`：拆句后音频文件路径
- `clip_duration`：句子音频时长（优先用于评估参考时长）

### 2.4 新增处理锁与心跳机制，避免并发处理冲突

`material` 表新增：

- `processing_owner`
- `processing_started_at`
- `processing_heartbeat_at`

并配套：

- 抢占锁逻辑（可处理 stale lock）
- 后台心跳续约
- 超时任务自动修复（标记为 `failed`）

### 2.5 关闭应用流程完善（清理录音 + 后端优雅退出）

- 前端「Close App」按钮先调用 `DELETE /api/recordings/cleanup`
- 清理成功后调用 `POST /api/system/shutdown`
- 降低本地反复调试时的录音残留问题

---

## 3. 目录结构

```text
shadowing_v0_2/
├─ backend/
│  ├─ app/
│  │  ├─ api/            # 路由层（materials/sentences/recordings/evaluations/system）
│  │  ├─ services/       # 核心业务（转写、切句、翻译、评估、媒体处理）
│  │  ├─ models/         # SQLModel 数据模型
│  │  ├─ schemas/        # 请求/响应 schema
│  │  ├─ core/           # 配置与数据库初始化
│  │  └─ main.py
│  └─ requirements.txt
├─ frontend/
│  ├─ src/components/    # 上传、素材列表、训练、录音、评估面板
│  └─ src/lib/api.ts
└─ README.md
```

---

## 4. 环境准备

### 4.1 安装 FFmpeg

```bash
ffmpeg -version
ffprobe -version
```

Windows 可使用：

```bash
winget install Gyan.FFmpeg
```

### 4.2 安装 PyTorch（可选，但 faster-whisper 通常需要）

**CPU：**

```bash
pip install torch torchvision torchaudio
```

**CUDA 12.1：**

```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

---

## 5. 快速启动

### 5.1 启动后端

```bash
cd backend
python -m venv .venv
```

激活虚拟环境后安装依赖：

```bash
pip install -r requirements.txt
```

启动服务：

```bash
uvicorn app.main:app --reload --port 8000
```

### 5.2 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认地址：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`

---

## 6. 配置说明（后端）

后端通过 `pydantic-settings` 读取以下文件（按顺序覆盖）：

1. `backend/.env`
2. `backend/.env.local`
3. `backend/.env.example`

常用变量：

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
PROCESSING_LOCK_TIMEOUT_SECONDS=1800
PROCESSING_LOCK_HEARTBEAT_SECONDS=10
```

---

## 7. 数据目录

默认在 `backend/data` 下创建：

- `materials/`：原始上传文件
- `audio/`：素材统一音频
- `audio/sentences/material_{id}/`：句子拆分音频
- `recordings/`：用户跟读录音
- `app.db`：SQLite 数据库

---

## 8. 数据库迁移说明

应用启动时会自动执行轻量迁移：

- `sentence` 表补齐 v0.2 时间轴与切句音频字段
- `material` 表补齐处理锁字段
- 对历史数据回填 `original_*` 和 `clip_duration` 基础值

---

## 9. 核心 API

### 9.1 素材

- `POST /api/materials/upload`
- `GET /api/materials`
- `GET /api/materials/{material_id}`
- `POST /api/materials/{material_id}/process`
- `GET /api/materials/{material_id}/audio`
- `GET /api/materials/{material_id}/video`

### 9.2 句子

- `GET /api/materials/{material_id}/sentences`

### 9.3 录音与评估

- `POST /api/recordings/upload`
- `GET /api/evaluations/{evaluation_id}`
- `DELETE /api/recordings/cleanup`

### 9.4 系统

- `POST /api/system/shutdown`

---

## 10. 注意事项

- 首次运行 `faster-whisper` 可能下载模型，耗时较长。
- 未配置 `DEEPSEEK_API_KEY` 时，翻译会自动降级（返回原文）。
- 当前评分用于训练反馈，不等价于标准化口语考试评分。
