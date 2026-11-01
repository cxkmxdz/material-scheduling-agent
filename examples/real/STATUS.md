# 真实模型验证状态

状态：**not_run，未验证**。

2026-11-01 在本机实际执行 `python scripts/real_comparison.py`，返回 MODEL_CONFIGURATION_MISSING。未检测到可用 MODEL_API_KEY 和 MODEL_NAME；没有发送模型请求，也没有生成真实模型输出或 Trace。

需要候选人在本地 `.env` 或环境变量配置：

- MODEL_API_KEY：有权限且有可用额度的 API key。
- MODEL_NAME：支持 Chat Completions 原生 function calling 的实际模型名称。
- MODEL_BASE_URL：使用兼容服务时填写正确版本前缀；默认 https://api.openai.com/v1。
- MODEL_TIMEOUT_SECONDS：可选，默认 30 秒。

配置后在项目根目录执行 `python scripts/real_comparison.py`，或使用 README 中实际虚拟环境解释器路径。结果写入新的 runtime/real-* 目录。阅读三个 Trace，确认同请求在空闲与占用条件下的动作差异，以及保存失败时无虚报成功，再补充真实评估结论。

本目录没有真实 Trace。tests 中的假 HTTP 提供方不属于真实模型证据。
