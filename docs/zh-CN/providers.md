# 模型、Adapter 与测试

简体中文 | [English](../en-US/providers.md) · [文档首页](README.md)

Provider 配置由后端持久化。静态 Adapter Catalog 描述协议能提供的最大能力；每个用户配置档再声明它实际允许使用的能力和格式。业务流程只使用两者的交集。

## 当前支持矩阵

| 类型 | 快捷模板 / Adapter | 地址模式 | 可选能力 | 可选格式 |
| --- | --- | --- | --- | --- |
| LLM | OpenAI Chat Completions | Base URL | `generate_text`, `generate_json` | `json_schema`, `response_format`, `prompt_only` |
| TTS | OpenAI Audio TTS | 完整 Endpoint | `synthesize` | WAV, MP3, FLAC, Opus, AAC, PCM |
| TTS | MiMo TTS | 完整 Endpoint | `synthesize` | WAV, MP3, FLAC, Opus, PCM16 |
| ASR | OpenAI Audio Transcription | Base URL | `transcribe`, `word_timestamps` | 不适用 |
| ASR | MiMo ASR | 完整 Endpoint | `transcribe` | 不适用 |

Local Whisper 是系统级本地 ASR 回退，不是数据库中的远程 Provider 配置档。0.4.2 基线只保留 Catalog 中明确支持的适配器；未注册的历史实现已经从运行代码中移除。

## 快捷模板与我的配置

快捷模板是只读元数据，不写入数据库，不能编辑、删除或直接设为默认。点击“使用此模板”后，用户会创建一条独立配置档。配置档可以：

- 自定义名称，同一协议创建多份配置。
- 独立填写地址、API Key、模型和公开扩展参数。
- 选择协议允许范围内的能力与格式。
- 启用、禁用、测试、设为默认或删除。

0.4.2 不读取或升级旧数据库中的 Provider 记录。新基线只允许创建当前支持矩阵中的配置档；其他 Provider 类型会被拒绝，也不会作为内置快捷模板出现。

## 地址填写规则

| Adapter | 应填写内容 | 示例 | 应用追加路径 |
| --- | --- | --- | --- |
| OpenAI Chat | Base URL | `https://api.openai.com/v1` | `/chat/completions`；连接验证使用 `/models` |
| OpenAI ASR | Base URL | `https://api.openai.com/v1` | `/audio/transcriptions` |
| OpenAI TTS | 完整语音 Endpoint | `https://api.openai.com/v1/audio/speech` | 不追加 |
| MiMo TTS / ASR | 完整 Chat Completions Endpoint | `https://api.xiaomimimo.com/v1/chat/completions` | 不追加 |

`full_endpoint` 会原样使用用户填写的 URL。应用不会自动补全 `/audio/speech` 或 `/chat/completions`。例如把 `https://api.xiaomimimo.com/v1` 填入 MiMo 配置会向该地址直接请求，通常得到 `404 Not Found`。

## 能力和格式声明

用户声明是后端强制执行的边界，不只是 UI 提示：

- AI 文本需要默认 LLM 同时启用 `generate_text` 和 `generate_json`。
- `generate_json` 至少需要启用一种 JSON 方式：`json_schema`、`response_format` 或 `prompt_only`。
- TTS 的 `synthesize` 至少需要一种输出格式。
- `word_timestamps` 自动依赖 `transcribe`。
- MiMo ASR 不提供词级时间戳，因此不能声明 `word_timestamps`。

TTS 从配置档已启用的格式中按 `wav → mp3 → flac → opus → aac → pcm` 选择训练输入。所有结果最终都会规范化为句级 24 kHz 单声道 WAV，并合并为整篇 MP3。原始 PCM 必须同时声明采样率、声道数和样本格式。

OpenAI TTS 默认不会因为练习带有语言标签就发送 `instructions`。只有明确确认兼容端点支持该字段时，才启用 `send_language_instruction`；用户填写的音色 instructions 不受此默认规则影响。

## 配置检查与模型测试

设置页提供三个不同等级，响应中的 `verification_level` 会说明实际验证范围：

1. **检查配置（configuration）**：只在后端本地校验必填字段、能力、格式、依赖和 URL 形状，不发送网络请求，也不产生模型费用。
2. **验证连接（network）**：仅当 Adapter 声明安全的无生成请求时访问网络。OpenAI Chat 当前通过 `GET /models` 检查元数据；音频 Adapter 的安全策略仍是本地配置检查，所以“成功”不代表已调用过音频模型。
3. **运行付费测试（inference）**：用户确认后发送最小真实生成、合成或转写请求，可能产生费用，并受模型配额和内容策略影响。

连接失败只返回经过脱敏的可读错误，不改变能力声明、默认 Provider 或 ASR 开关。测试不会持久化“已验证”状态，也不会自动探测或扩展能力。

## 密钥安全

- API Key 只由后端保存；查询和测试响应只返回掩码。
- 编辑时 API Key 留空会保留原值，填写新值才会替换。
- 错误信息会移除完整密钥和敏感请求头。
- 不要把密钥放在 URL、README、`.env.example` 或提交记录中。
- `backend/.env`、数据库和运行数据必须保持 Git 忽略。

## ASR 场景路由

素材转写和录音评估有两个独立偏好：

| 场景 | 远程要求 |
| --- | --- |
| 素材转写 | `transcribe + word_timestamps`，并支持素材语言 |
| 录音评估 | `transcribe`，并支持素材语言 |

运行时路由会同时检查配置档启用状态、默认选择、用户能力、语言支持和 Local Whisper 可用性：

| Local Whisper | 远程满足要求 | 实际路由 |
| --- | --- | --- |
| 可用 | 是 | 按用户场景偏好 |
| 可用 | 否 | 强制本地 |
| 不可用 | 是 | 强制远程 |
| 不可用 | 否 | 返回明确不可用错误 |

MiMo ASR 协议只接受 `auto`、`zh` 和 `en`。应用将规范化的英语标签映射为 `en`，中文标签映射为 `zh`；其他学习语言在发送请求前即判定为不支持，并回退到可用的 Local Whisper，否则返回明确错误。MiMo ASR 也没有词级时间戳，所以不能用于远程素材转写。

OpenAI/Whisper 对简体和繁体中文都使用 `zh` 提示，返回字形取决于模型；使用 `zh-TW` 字符级评分前应先检查转写脚本。

## TTS Job 一致性

TTS Job 会冻结正文、标题、目标/翻译语言、Provider ID 和选项，并把输出放入带 Job ID 的独立目录。编辑文本或重新排队后，旧任务不得回写新练习。失败 Job 只有在快照仍匹配且没有更新任务占用时才能重新取得所有权，否则重试接口返回冲突。
