# 真实模型三组对照通过记录

2026-11-02 实际调用 api.deepseek.com 的 deepseek-flash，thinking disabled。三组输入、提示、模型和工具一致，仅改变独立数据库中的占用或故障条件。comparison.json 为逐项检查结果，manifest.json 校验原始输入、输出、Trace 和数据库导出的字节摘要。

| 条件 | 实际动作差异 | 确认和保存结果 |
| --- | --- | --- |
| free | 18:00 空闲，直接保存原时段 | not_required / saved，数据库 1 草稿 |
| occupied | 18:00 冲突后补查窗口，改建议 19:00 | pending_confirmation / saved，不占位，数据库 1 草稿 |
| save_failure | 观察 SAVE_FAILED 后重试一次，两次失败后结束 | not_required / failed，ID null，数据库 0 草稿 |

17 次模型决策均有 HTTP 200、真实响应 ID、返回模型名和 token 数记录。read_material、check_rules、query_slots、save_draft 由模型逐轮选择，工具观察返回模型后产生下一步，不使用预写真实决策脚本。保存故障是真实 SQLite INSERT 后错误回滚。

保存失败场景模型第 4 轮的说明使用 pending proposal，措辞较宽泛；结构化确认状态由工具正确推导为 not_required，最终无草稿，未将文字说明当作审批事实。原始说明保留，不事后润色。

这是单个模型的一组三条件验证，不能证明跨模型或多次运行稳定性。review.json 是对实际记录的离线复核，不额外发起模型请求。
