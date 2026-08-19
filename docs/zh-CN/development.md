# 开发、API 与数据目录

简体中文 | [English](../en-US/development.md) · [文档首页](README.md)

## 技术栈

- 后端：Python、FastAPI、SQLModel、SQLite、Alembic、httpx。
- 媒体与评分：FFmpeg/ffprobe、librosa、soundfile、NumPy；Local Whisper 为可选依赖。
- 前端：React 18、TypeScript、Vite、Vitest。
- 异步工作：数据库持久化 Job 队列，覆盖素材处理、录音评估和 TTS。

## 项目结构

```text
Shadowing_v0_4/
├─ README.md
├─ README.en.md
├─ docs/
│  ├─ zh-CN/
│  └─ en-US/
└─ shadowing/
   ├─ backend/
   │  ├─ alembic/
   │  ├─ app/
   │  │  ├─ api/
   │  │  ├─ models/
   │  │  ├─ schemas/
   │  │  └─ services/
   │  └─ tests/
   ├─ frontend/
   │  └─ src/
   │     ├─ app/
   │     ├─ features/
   │     │  ├─ materials/
   │     │  ├─ practice/
   │     │  ├─ vocabulary/
   │     │  ├─ create-practice/
   │     │  └─ settings/
   │     ├─ i18n/
   │     └─ lib/
   └─ shared/
      └─ language_catalog.json
```

源码目录使用版本中立名称 `shadowing/`；Git 分支记录版本，不再随发布重命名运行目录。前端代码按产品功能归档，跨端语言目录只在 `shared/language_catalog.json` 维护一份；API 路由只负责 HTTP 编排，耗时素材处理和 Provider 测试位于独立服务。

## 运行数据

默认数据根目录为 `shadowing/backend/data/`，并被 Git 忽略：

- `app.db`：Material、Sentence、Recording、Evaluation、Job、收藏词和 Provider 配置。
- `materials/`：原始上传。
- `audio/`：规范化完整音频、句级 WAV 和 TTS 输出。
- `videos/`：视频转码结果。
- `recordings/`：用户录音及中间产物。
- `models/`：可选本地模型缓存。

所有文件清理都应限制在数据目录内。不要提交数据库、媒体、模型、临时 `.part` 文件或 Provider 密钥。

## 主要 API

运行后可在 `/docs` 查看完整 OpenAPI。常用端点：

| 域 | 端点 |
| --- | --- |
| 语言 | `GET /api/languages`; `GET/PUT /api/languages/preferences` |
| 素材 | `POST /api/materials/upload`; `GET /api/materials`; `POST /api/materials/{id}/process`; `DELETE /api/materials/{id}` |
| 句子 | `GET /api/materials/{id}/sentences`; `GET /api/materials/{id}/latest-evaluations` |
| 收藏词 | `POST /api/words/collect`; `GET /api/words/collections`; `DELETE /api/words/collections/{id}` |
| 文本练习 | `GET /api/text-practices`; `POST /generate`; `POST /import`; `PATCH /{id}`; `POST /{id}/tts` |
| Provider | `GET /api/providers/catalog`; Provider CRUD、测试、音色、本地 ASR 状态和 ASR 场景设置 |
| 录音与评分 | `POST /api/recordings/upload`; `GET /api/evaluations/{id}` |
| Job | `GET /api/jobs/{id}`; `POST /api/jobs/{id}/retry` |

API Key 读取必须保持遮罩；业务服务应通过 Provider Factory/Router 获取实例，不能直接读取厂商配置。

## 数据库迁移

Schema 变更必须新增 Alembic revision，不应在启动时临时新增新字段。执行：

```powershell
cd shadowing/backend
.\.venv\Scripts\Activate.ps1
alembic heads
alembic upgrade head
```

0.4.2 是全新数据库基线：旧的 `app.db` 不得执行升级或 stamp。先备份整个数据目录，再由用户明确决定移走或删除旧 `app.db`，保留目录中的素材、音频、视频、录音和模型；随后只对新数据库执行 `alembic upgrade head`。不承诺旧数据库的兼容升级。

## 验证命令

后端：

```powershell
cd shadowing/backend
.\.venv\Scripts\python.exe -m pytest -q
```

前端：

```powershell
cd shadowing/frontend
npm test
npm run typecheck
npm run build
```

提交前还应检查：

```powershell
git diff --check
git status --short
git ls-files --others --exclude-standard
```

Provider、语言和任务改动至少应覆盖 Factory、能力门控、API Key 脱敏、ASR 路由、TTS 快照/恢复、0.4.2 新库基线以及前后端回归。
