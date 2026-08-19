# 安装、升级与启动

简体中文 | [English](../en-US/getting-started.md) · [文档首页](README.md)

## 环境要求

- Python 3.10 或更高版本（建议 3.12）。
- Node.js 20.19 或更高版本及 npm。
- FFmpeg 与 ffprobe，并可从终端的 `PATH` 调用。
- SQLite 由 Python 依赖提供，无需独立安装数据库服务。

确认媒体工具：

```powershell
ffmpeg -version
ffprobe -version
```

## 安装后端

在仓库根目录执行：

```powershell
cd shadowing/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

CMD 激活命令为 `.venv\Scripts\activate.bat`；macOS/Linux 使用 `source .venv/bin/activate`，并将 `Copy-Item` 替换为 `cp`。

`requirements.txt` 安装远程 Provider 和基础音频处理所需依赖，不包含 Local Whisper。运行设置主要来自 `backend/.env`，Provider 地址、模型和密钥则在前端“设置”页面保存到数据库。

## 可选安装 Local Whisper

只有需要本地素材转写或本地录音 ASR 时才安装：

```powershell
cd shadowing/backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements-local-whisper.txt
```

首次加载模型可能需要下载。可在 `.env` 中配置：

- `WHISPER_MODEL`：模型名称。
- `WHISPER_DEVICE`：例如 `cpu` 或 `cuda`。
- `WHISPER_COMPUTE_TYPE`：例如 `int8`、`float16`。
- `WHISPER_MODEL_DIR`：模型缓存目录。
- `WHISPER_ALLOW_DOWNLOAD`：是否允许自动下载。

设置页面可以检查运行环境、主动加载或释放模型；打开设置页面本身不会加载模型。远程和本地 ASR 的选择规则见 [Provider 指南](providers.md#asr-场景路由)。

## 安装前端

打开另一个终端：

```powershell
cd shadowing/frontend
npm install
npm run dev
```

默认前端地址为 <http://localhost:5173>，后端地址为 <http://localhost:8000>。前端 API 地址默认指向本机后端；需要覆盖时设置 `VITE_API_BASE`。

## 首次配置

1. 打开“设置”，选择 UI、学习内容和翻译语言。
2. 从快捷模板创建所需 LLM、TTS 或 ASR 配置档。
3. 填写地址、API Key、模型、能力和格式，然后保存。
4. 先执行本地配置检查；需要时再执行连接验证或付费测试。
5. 将可用配置档设为对应能力的默认 Provider。
6. 若要使用远程 ASR，检查素材转写和录音评估两个独立场景开关。

端点规则和能力依赖见[模型与 Provider](providers.md)。

## 0.4.2 全新基线

0.4.2 不支持将旧安装的 `shadowing/backend/data/app.db` 升级或 stamp。停止前后端并先备份整个 `shadowing/backend/data/`；经用户明确决定后，仅将旧的 `app.db` 移走或删除。不要删除数据目录中的素材、音频、视频、录音或模型。

然后安装依赖并创建新数据库：

```powershell
cd shadowing/backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
```

`alembic upgrade head` 只用于这个全新数据库基线；不要对旧 `app.db` 执行升级、stamp 或手工复制迁移中的表。

## 验证安装

```powershell
cd shadowing/backend
.\.venv\Scripts\python.exe -m pytest -q

cd ../frontend
npm test
npm run build
```

如果前端显示 `Failed to fetch`，优先检查后端是否监听 8000 端口、`VITE_API_BASE` 是否正确，以及 `.env` 中的 `CORS_ORIGINS` 是否包含当前前端地址。
