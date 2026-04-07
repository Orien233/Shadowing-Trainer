# Shadowing Trainer V0.1

一个本地运行的影子跟读最小可用版（MVP）：

- 上传音频/视频素材
- Whisper 转写
- 自动切句
- DeepSeek 翻译（无 Key 时使用降级占位）
- 逐句播放
- 跟读录音
- 基础评估（完整性 / 流畅度 / 同步度 / 综合分）

> 这个版本重点是把「从素材到跟读反馈」的最短闭环先跑通，目录拆分尽量解耦，方便继续加收藏、用户母语、多 Provider 等能力。

---

## 1. 技术栈

### 后端
- Python 3.10+
- FastAPI
- SQLModel
- faster-whisper
- FFmpeg
- librosa / soundfile
- httpx

### 前端
- React
- TypeScript
- Vite

---

## 2. 目录结构

```text
shadowing_v0_1/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── materials.py
│   │   │   ├── sentences.py
│   │   │   ├── recordings.py
│   │   │   └── evaluations.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── database.py
│   │   ├── models/
│   │   │   ├── material.py
│   │   │   ├── sentence.py
│   │   │   ├── recording.py
│   │   │   └── evaluation.py
│   │   ├── schemas/
│   │   │   ├── material.py
│   │   │   ├── sentence.py
│   │   │   ├── recording.py
│   │   │   └── evaluation.py
│   │   ├── services/
│   │   │   ├── media_service.py
│   │   │   ├── transcription_service.py
│   │   │   ├── segmentation_service.py
│   │   │   ├── translation_service.py
│   │   │   └── evaluation_service.py
│   │   ├── utils/
│   │   │   └── text_utils.py
│   │   └── main.py
│   ├── data/
│   │   ├── materials/
│   │   ├── audio/
│   │   ├── recordings/
│   │   ├── cache/
│   │   └── app.db
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── MaterialUploader.tsx
│   │   │   ├── MaterialList.tsx
│   │   │   ├── SentenceTrainer.tsx
│   │   │   ├── RecorderPanel.tsx
│   │   │   └── EvaluationPanel.tsx
│   │   ├── lib/
│   │   │   └── api.ts
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── types.ts
│   │   └── styles.css
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts
└── README.md
```

---

## 3. 环境配置

## 3.1 安装 FFmpeg

必须先装 FFmpeg，并确保命令行可用：

```bash
ffmpeg -version
ffprobe -version
```

### Windows
推荐：
- `winget install Gyan.FFmpeg`
- 或手动安装后把 `ffmpeg/bin` 加到 PATH

### macOS
```bash
brew install ffmpeg
```

### Ubuntu / Debian
```bash
sudo apt update
sudo apt install ffmpeg -y
```

---

## 3.2 后端启动

```bash
cd backend
python -m venv .venv
```

### Windows
```bash
.venv\Scripts\activate
```

### macOS / Linux
```bash
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

复制环境变量：

```bash
cp .env.example .env
```

启动后端：

```bash
uvicorn app.main:app --reload --port 8000
```

---

## 3.3 前端启动

```bash
cd frontend
npm install
npm run dev
```

默认地址：
- 前端: `http://localhost:5173`
- 后端: `http://localhost:8000`

---

## 4. .env 配置说明

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

### 说明
- `WHISPER_MODEL`: `tiny / base / small / medium / large-v3`
- `DEEPSEEK_API_KEY`: 用于翻译和更自然的文字反馈；为空时走本地降级逻辑

---

## 5. MVP 流程

1. 上传素材
2. 后端保存原始文件
3. FFmpeg 统一提取音频
4. faster-whisper 转写
5. 自动合并 segment 做训练切句
6. DeepSeek 翻译（或降级）
7. 前端逐句播放
8. 用户录音跟读
9. 后端转写录音并做基础评估
10. 前端展示分数和文字反馈

---

## 6. 当前已实现接口

### 素材
- `POST /api/materials/upload`
- `GET /api/materials`
- `GET /api/materials/{material_id}`
- `POST /api/materials/{material_id}/process`
- `GET /api/materials/{material_id}/audio`

### 句子
- `GET /api/materials/{material_id}/sentences`

### 录音 + 评估
- `POST /api/recordings/upload`
- `GET /api/evaluations/{evaluation_id}`

---

## 7. 下一步建议

V0.2 可以直接往下加：

- 用户母语 / 反馈语言设置
- 自定义 LLM Provider
- 难句收藏
- 复练页
- 手动调句
- 任务队列化

---

## 8. 注意事项

### 8.1 faster-whisper 首次加载较慢
第一次跑会下载模型。

### 8.2 翻译降级逻辑
如果没配 DeepSeek Key，系统仍可跑通，但翻译会退化为简单占位文本，方便先验证训练主流程。

### 8.3 基础评估不是专业发音评分
当前版本更适合作为「练习辅助评分」，不是考试级评测器。

### 8.4 视频文件支持
上传视频后会自动抽取音频用于后续处理。

---
