# Shadowing Trainer 文档

简体中文 | [English](../en-US/README.md) · [返回项目首页](../../README.md)

这里保存 Shadowing Trainer v0.4.1 的详细使用和开发文档。根目录 README 只提供最短启动路径；安装、模型配置和具体工作流以本目录文档为准。

## 开始使用

1. [安装、升级与启动](getting-started.md)：准备 Python、Node.js、FFmpeg、数据库和可选 Local Whisper。
2. [使用指南](user-guide.md)：配置语言与模型，上传素材，生成文本并完成跟读评分。
3. [模型与 Provider](providers.md)：了解 Adapter、能力、格式、端点和三种测试等级。

## 参考

- [多语言行为](multilingual.md)：语言快照、Provider 语言限制、分句和评分边界。
- [开发与 API](development.md)：技术栈、目录、数据文件、主要接口和验证命令。
- [版本记录](changelog.md)：v0.4.1 及先前版本的主要变化。

## 文档约定

- 每个中文页面顶部都有对应英文页面链接，英文页面也可切回中文。
- UI 中的 Provider Catalog 和后端注册表是模型支持范围的最终事实来源；文档用于解释其行为。
- 文档命令默认从仓库根目录执行，源码目录为 `shadowing/`。
