# 更新日志

TraceForge 的重要变更均记录在此。

项目遵循[语义化版本](https://semver.org/lang/zh-CN/)，日志结构参考
[Keep a Changelog](https://keepachangelog.com/zh-CN/)。

## [未发布]

## [0.1.1] - 2026-07-17

### 变更

- README、贡献指南、安全策略、更新日志与演示横幅改为中文优先；
- 汉化 CLI 帮助、自有错误消息、Rich 终端摘要及自包含 HTML 报告；
- 汉化合成示例中的自然语言，同时保持命令、flags、OTLP/OpenTelemetry 字段、
  span attribute 键、JSON schema/keys 和状态值兼容；
- 保持 `schema_version` 为 `1.0`，现有自动化无需迁移。

## [0.1.0] - 2026-07-17

### 新增

- OTLP JSON 与 JSONL span 规范化；
- GenAI 语义约定中的模型、Token、操作与工具提取；
- 基于独占时间的关键路径、工具错误与重试循环分析；
- 用户可配置的精确、前缀和通配符 Token 价格；
- Rich 终端摘要、稳定 JSON 与自包含 HTML 报告；
- 内置演示、真实感示例、强类型 API、测试与多版本 CI。

[未发布]: https://github.com/abc123dx/traceforge-otel/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/abc123dx/traceforge-otel/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/abc123dx/traceforge-otel/releases/tag/v0.1.0
