# 为 TraceForge 做贡献

感谢你帮助大家更轻松地理解 Agent 轨迹。

## 开发环境

```bash
git clone https://github.com/abc123dx/traceforge-otel.git
cd traceforge-otel
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

提交 Pull Request 前请运行：

```bash
ruff check .
ruff format --check .
mypy
pytest
traceforge demo
```

## 设计原则

1. **本地优先。** 核心分析不得依赖账号、Collector 或网络请求。
2. **证据优先。** 每项发现都应回溯到具体 span 和有文档说明的启发式规则。
3. **绝不丢失输入。** 解析器兼容性应只增不减，并保留未知 attributes。
4. **自动化稳定。** JSON schema 属于公共 API；破坏性修改必须先讨论。
5. **成本诚实。** 没有维护与版本化方案时，不得硬编码供应商价格。

## Pull Request

请让改动保持聚焦；新增行为应附测试；用户可见契约变化时应同步更新示例和文档。
新增语义约定别名时，请加入能体现对应导出器表示方式的 fixture。

只使用合成轨迹数据。禁止提交生产轨迹、prompt、API key、个人信息或客户标识符。
