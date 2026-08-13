# Shadowing Trainer v0.4.1

简体中文 | [English](README.en.md)

Shadowing Trainer 是一款本地优先的多语言跟读训练 Web 应用。你可以上传音频或视频，也可以从收藏单词生成练习文本或直接导入文本；系统会将内容整理为句级练习，并提供播放、录音、评分和词级反馈。

## 主要功能

- 上传音频或视频，自动完成转写、分句和翻译。
- 收藏练习中的单词，并按学习语言管理词库。
- 使用 LLM 从收藏单词生成连贯文本，或直接粘贴自己的文本。
- 使用 TTS 创建句级音频，并将结果复用为普通练习素材。
- 逐句播放、循环、录音和查看多维评分反馈。
- 分别配置 LLM、TTS、远程 ASR 和可选的 Local Whisper。
- 中文与英文界面，以及独立的学习语言和翻译语言设置。

详细操作请阅读[用户指南](docs/zh-CN/user-guide.md)。

## 运行前准备

- Python 3.10 或更高版本
- Node.js 18 或更高版本及 npm
- 可从 `PATH` 调用的 FFmpeg 和 ffprobe

Local Whisper 是可选组件；只使用远程 ASR 时无需安装。完整环境说明见[安装与启动](docs/zh-CN/getting-started.md)。

## 快速开始

在仓库根目录配置并启动后端：

```powershell
cd shadowing/backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

在另一个终端启动前端：

```powershell
cd shadowing/frontend
npm install
npm run dev
```

默认地址：

- 前端：<http://localhost:5173>
- 后端 API：<http://localhost:8000>
- OpenAPI 文档：<http://localhost:8000/docs>

首次启动后，请在前端的“设置”页面创建需要的 Provider 配置档。端点填写方式和测试等级见[模型与 Provider 指南](docs/zh-CN/providers.md)。

## 文档

- [文档首页](docs/zh-CN/README.md)
- [安装、升级与启动](docs/zh-CN/getting-started.md)
- [使用指南](docs/zh-CN/user-guide.md)
- [模型接入、能力声明与测试](docs/zh-CN/providers.md)
- [多语言行为与评分边界](docs/zh-CN/multilingual.md)
- [开发、API 与数据目录](docs/zh-CN/development.md)
- [版本记录](docs/zh-CN/changelog.md)

## 重要说明

- 升级已有数据库前请备份 `shadowing/backend/data/`，并执行 `alembic upgrade head`。
- Provider 密钥由后端保存，查询接口只返回掩码；不要将 `.env`、数据库或密钥提交到 Git。
- 本项目的评分结果用于练习反馈，不应视为正式语言能力考试成绩。
- 当前 Git 分支为 `v0_4_1`，运行源码位于版本中立的 `shadowing/` 目录。
