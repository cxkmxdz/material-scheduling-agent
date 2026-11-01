# 素材审核与发布排期 Agent 评估记录

本次离线自动测试实际运行结果为 73 项通过、0 失败、0 错误、0 跳过，运行环境为 Windows 和 Python 3.13.5。依据为 `examples/test-results/summary.json`、`pytest.txt` 和 `pytest.xml`，不是预计测试数量。真实模型尚未验证，不能将以下离线结果当作真实模型效果。

另外在新的 `runtime/clean-venv` 中实际执行 `uv sync --locked --extra dev`，重新安装 19 个包并运行完整测试，同样 73 项通过。独立报告见 `examples/test-results-clean/summary.json`。这是同一台 Windows 机器上的全新虚拟环境验证，不代表另一操作系统或另一 Python 版本已通过。

## 场景和实际结果

下表的每个名称均对应 `examples/mock/<名称>.output.json`、`<名称>.trace.jsonl` 和 `<名称>.database.json`。输入及条件见 `examples/mock/manifest.json`，其中包含实际产物 SHA256。

| 验收点 | 场景 | 预期 | 实际 |
| --- | --- | --- | --- |
| A01 | normal | 审核通过并保存原小时 | completed；18:00；数据库 1 草稿 |
| A02 | missing | 列缺失字段，不保存 | needs_input；缺 asset_url、rights_owner；0 草稿 |
| A03 | risk | 展示阻断规则，不保存 | blocked；DEMO-R001；0 草稿 |
| A04 | conflict | 补查并保存待确认建议 | completed；19:00；pending_confirmation；不占位 |
| A05 | no_slots | 不突破窗口 | blocked；0 草稿 |
| A06 | duplicate | 返回同一记录 | 与 normal 同一 draft_id；数据库仍 1 草稿 |
| A07 | id_conflict | 拒绝覆盖 | failed；REQUEST_ID_CONFLICT；原草稿保留 |
| A08 | save_failure | 两次故障回滚，无假成功 | failed；两次 SAVE_FAILED；ID 为 null；0 草稿 |
| A08 | save_retry | 观察错误后重试成功 | 首次 SAVE_FAILED，第二次 DRAFT_SAVED；1 草稿 |
| A09 | step_limit | 模型轮数耗尽 | incomplete；保留读取观察；0 草稿 |
| A09 | tool_limit | 工具预算耗尽 | incomplete；第二次工具未执行；0 草稿 |
| A10 | multi | 全部子项分别报告 | M01 completed、M02 needs_input、M03 blocked、M04 completed；聚合 needs_input |

## 观察后的动作变化

第一组对照使用同一份 `examples/inputs/normal.json`：normal 的第 3 次工具查询得到 18:00 可用，随后保存；conflict 仅增加已确认占用，第 3 次查询得到冲突，第 4 次改为查询整个窗口，然后保存 19:00 待确认建议。两个 Trace 的动作数量与查询参数不同。

第二组对照仍使用同一请求：normal 一次保存成功；save_retry 在 SQLite INSERT 后实际触发错误并回滚，下一轮 Mock 观察到 SAVE_FAILED 后再调用 save_draft，最终查询数据库有一份草稿。save_failure 两次错误后结束，输出 failed 且数据库为空。

以上两组证实观察影响脚本模拟的下一步和业务执行，**不能证明真实模型依据观察调整行为**。真实对照脚本已经实现，必须配置实际模型才能补齐 A11。

## 自动测试覆盖

`tests/test_acceptance.py` 覆盖业务场景、逐项状态、提前 finish、明确模型错误、非法工具后的修正和 Trace 字段。`tests/test_guards.py` 覆盖伪造审核和 confirmed 参数、未审核或未查时段、缺信息及阻断素材绕过、窗口与整点限制、并发幂等、并发抢同一小时、查询后冲突变化、真实回滚、时区等价请求摘要。

`tests/test_model_and_cli.py` 覆盖函数定义、历史观察回传、401/403/429/500、超时、网络错误、非法响应、假 HTTP 提供方的完整协议循环、密钥脱敏、CLI 子进程运行与防覆盖。假 HTTP 提供方用脚本响应，名称为 FAKE-HTTP-PROVIDER，运行在测试临时目录，没有将其 Trace 放入 examples/real。

`tests/test_example_generation.py` 重新实际执行 12 组示例，校验产物摘要、输出 ID 与数据库导出的一致性，以及重复请求的同一 ID。各业务测试使用独立临时 SQLite；幂等和并发用例有意复用数据库。

## 已发现问题和修复

首轮测试实际为 35 通过、14 失败。错误定位为 drafts INSERT 使用了 9 个占位符，而表有 8 列。改为明确列名和 8 个占位符后，49 项业务及边界测试通过。后续补充接口、CLI 和证据生成测试，并修复 JSON null 参数校验、转义密钥脱敏、注册失败逐项状态和失败后的建议时间展示，得到本文件所述报告。

本文件如与将来的测试报告不一致，应以新运行证据为准并同步更新，不能沿用旧通过数量。

## 真实模型未完成项

`scripts/real_comparison.py` 已实际尝试启动，返回 MODEL_CONFIGURATION_MISSING，未向模型端点发送请求。缺少 MODEL_API_KEY 和 MODEL_NAME；若使用兼容服务，另需正确的 MODEL_BASE_URL 及支持原生函数调用的模型、可用额度和网络。`examples/real/STATUS.md` 明确记录未执行，不存在伪造真实结果。

补齐配置后运行真实对照，验收原时段空闲、仅改变占用、保存故障三组条件，阅读 Trace 解释动作差异，保留实际模型名称、输出、错误和数据库导出。当前未验证任何实际提供方的兼容性、决策稳定性、延迟或成本。

其他限制：演示只检查元数据规则；没有人工确认或真实发布；待确认建议不占位，可能建议同一小时；跨素材不是整批原子事务；每个请求 ID 不允许改内容重提，补齐信息应使用新 ID；本次未实测非 Windows 系统。GitHub URL 与评审权限仍待候选人完成。
