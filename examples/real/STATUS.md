# 真实模型验证状态

状态：**2026-11-02 三组真实模型对照全部通过**，模型为 deepseek-flash，服务为 api.deepseek.com，thinking disabled。

最终证据位于 `20261102-121118-525417/`，入口为 comparison.json：原时段空闲时保存 18:00，不需确认；原时段冲突时补查并保存 19:00 待确认建议；两次真实 SQLite 保存故障后模型结束，ID 为 null、数据库为空。17 次实际模型决策响应均为 HTTP 200，响应 ID、返回模型名和 token 数保存在 Trace 中。单轮通过不代表多次稳定性或其他模型已经验证。

2026-11-01 在本机实际执行 `python scripts/real_comparison.py`，返回 MODEL_CONFIGURATION_MISSING。未检测到可用 MODEL_API_KEY 和 MODEL_NAME；没有发送模型请求，也没有生成真实模型输出或 Trace。

需要候选人在本地 `.env` 或环境变量配置：

- MODEL_API_KEY：有权限且有可用额度的 API key。
- MODEL_NAME：支持 Chat Completions 原生 function calling 的实际模型名称。
- MODEL_BASE_URL：使用兼容服务时填写正确版本前缀；默认 https://api.openai.com/v1。
- MODEL_TIMEOUT_SECONDS：可选，默认 30 秒。

配置后在项目根目录执行 `python scripts/real_comparison.py`，或使用 README 中实际虚拟环境解释器路径。当前脚本结果写入新的 examples/real/时间戳目录。阅读三个 Trace，确认同请求在空闲与占用条件下的动作差异，以及保存失败时无虚报成功，再补充真实评估结论。

初次交付时本目录没有真实 Trace；以下追加后续真实接口尝试。tests 中的假 HTTP 提供方始终不属于真实模型证据。

## 2026 年 11 月 2 日首次真实请求

用户在本地填写配置并确认后，实际运行了三组对照。产物位于 `20261102-120512-282303/`：三组全部返回 MODEL_AUTH_ERROR，工具调用均为 0，没有草稿；all_acceptance_met 为 false。这些 Trace 是实际 API 失败记录，不能算真实模型业务决策验证。

检查发现模型名配置为 deepseek、端点仍为 api.openai.com/v1，且没有其他环境变量覆盖 .env。用户已在本地修正服务地址和有效模型 ID；旧失败记录未改写。

第二次 `20261102-121014-701231/` 使用正确的 DeepSeek 地址和模型，但由于未关闭 thinking，三组均 HTTP 400，没有工具决策。适配器随后修复为：对 api.deepseek.com 默认显式 disabled；其他端点只有配置 MODEL_THINKING=disabled 时才附带该字段。第三次真实运行才得到上方通过结果。两轮失败均保留，未当作业务验收通过。

对照脚本将结果直接存入 examples/real 的新子目录，数据库保留在被忽略的 runtime 中；验收核对观察后的动作和真实持久状态，API 错误不算业务场景通过。最终离线回归为 83 项通过，报告位于 examples/test-results-real-final/。
