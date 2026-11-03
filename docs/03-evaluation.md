# 素材审核与发布排期 Agent 评估记录

2026-11-02 已完成 deepseek-flash 的同请求三组真实对照，全部达到本次验收判据；最终离线回归实测 83 项通过、0 失败。入口为[真实对照](../examples/real/20261102-121118-525417/comparison.json)、[Trace 复核](../examples/real/20261102-121118-525417/review.json)和[最终测试报告](../examples/test-results-real-final/summary.json)。运行环境为 Windows 和 Python 3.13.5。单次三组通过不能代表多次稳定性或其他模型均已验证。

初次交付的离线结果为 73 项通过，依据为 `examples/test-results/`；后续准备阶段为 82 项通过，依据为 `examples/test-results-followup/`。这些历史报告保留原样，不作为真实模型效果证明。

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

以上两组证实观察影响脚本模拟的下一步和业务执行，**不能证明真实模型依据观察调整行为**。A11 的实际模型证据另见后面的真实对照，不混用 Mock 结论。

## 自动测试覆盖

`tests/test_acceptance.py` 覆盖业务场景、逐项状态、提前 finish、明确模型错误、非法工具后的修正和 Trace 字段。`tests/test_guards.py` 覆盖伪造审核和 confirmed 参数、未审核或未查时段、缺信息及阻断素材绕过、窗口与整点限制、并发幂等、并发抢同一小时、查询后冲突变化、真实回滚、时区等价请求摘要。

`tests/test_model_and_cli.py` 覆盖函数定义、历史观察回传、401/403/429/500、超时、网络错误、非法响应、假 HTTP 提供方的完整协议循环、密钥脱敏、CLI 子进程运行与防覆盖。假 HTTP 提供方用脚本响应，名称为 FAKE-HTTP-PROVIDER，运行在测试临时目录，没有将其 Trace 放入 examples/real。

`tests/test_example_generation.py` 重新实际执行 12 组示例，校验产物摘要、输出 ID 与数据库导出的一致性，以及重复请求的同一 ID。各业务测试使用独立临时 SQLite；幂等和并发用例有意复用数据库。

## 已发现问题和修复

首轮测试实际为 35 通过、14 失败。错误定位为 drafts INSERT 使用了 9 个占位符，而表有 8 列。改为明确列名和 8 个占位符后，49 项业务及边界测试通过。后续补充接口、CLI 和证据生成测试，并修复 JSON null 参数校验、转义密钥脱敏、注册失败逐项状态和失败后的建议时间展示，得到本文件所述报告。

本文件如与将来的测试报告不一致，应以新运行证据为准并同步更新，不能沿用旧通过数量。

## 真实模型对照

实际服务为 api.deepseek.com，配置与服务返回的模型名均为 deepseek-flash。三组使用同一个 req-001、M01、demo 渠道、18:00 hard 要求和 18:00–21:00 窗口，规范化请求 SHA256 为 `ffd6ca864d5dbab25d7837617bbd46e0c9670418b03b825b245b40515fb385a4`。提示、工具和模型配置相同，仅改变各独立数据库的已确认占用或 SQLite 故障注入。thinking 显式 disabled，工具选择 required，一轮一个函数调用；没有运行器预排动作或切换 Mock。

| 条件 | 模型观察后的实际动作 | 最终状态 | 数据库 |
| --- | --- | --- | --- |
| free | 第 3 轮查询 18:00 可用，第 4 轮保存原时段，第 5 轮 finish | completed / saved / not_required | 1 草稿，原时段占位 |
| occupied | 第 3 轮查出冲突，第 4 轮补查完整窗口，第 5 轮选 19:00 保存，第 6 轮 finish | completed / saved / pending_confirmation | 1 建议草稿，不占位，保留 18:00 原要求 |
| save_failure | 第 4 轮保存观察 SAVE_FAILED，第 5 轮重试仍失败，第 6 轮 finish | failed / failed / ID null | 0 草稿，两次 INSERT 均回滚 |

free 共 4 次业务工具调用、5 次实际模型请求；occupied 和 save_failure 分别为 5 次业务工具调用、6 次模型请求。17 个决策响应均 HTTP 200，各自响应 ID、实际模型名和 token 数见 Trace 的 model_response。业务保存失败场景的最终任务状态 failed 是预期正确结果，所以该场景 acceptance_met 为 true；这与前两次接口错误导致未通过有明确区别。

逐条读取 `free.trace.jsonl`、`occupied.trace.jsonl`、`save_failure.trace.jsonl` 并核对数据库导出后，确认模型确实依据不同观察增加替代查询或选择一次重试。`comparison.json` 保存每项检查、动作参数、简短决策说明和观察后的下一步，`manifest.json` 保存原始产物摘要。没有伪造草稿 ID、代替用户确认或执行发布。

## 真实运行暴露的问题及修复

首次 `20261102-120512-282303/` 三组均鉴权失败，工具调用为 0：模型名为 deepseek，但端点仍为 api.openai.com/v1。未发现环境变量覆盖 .env；用户在本地修正服务地址和有效模型 ID。这轮保留为失败证据，不算业务验收。

第二次 `20261102-121014-701231/` 使用 deepseek-flash 和正确地址，但三组均 HTTP 400、工具调用为 0。对错误做不含原文的诊断，确认涉及 thinking 与 tool_choice。根据 [DeepSeek 官方接口说明](https://api-docs.deepseek.com/api/create-chat-completion/)，thinking 模式不支持 required 工具选择。适配器因此对 DeepSeek 官方端点默认显式发送 thinking disabled，其他端点不自动添加该字段；另提供 MODEL_THINKING=disabled 可选配置。修复后先回归测试，再得到上面的第三轮真实通过记录。

本轮还修正原评估脚本只看最终状态的不足，增加观察顺序、后续模型动作、确认状态和数据库一致性检查，避免将 API 错误误判成保存故障验收通过。新增响应 ID、HTTP 状态、返回模型及 token 数记录；不记录错误体、密钥或内部思维链。原缺配置记录 config-check.json 及上述两轮失败证据都未覆盖。

## 限制

本次仅对一个服务、一个模型的一组请求完成三条件对照，未做多次稳定性、其他模型或成本基准。保存失败 Trace 的第 4 轮简短说明将原时段草稿称为 pending proposal，措辞不够精确；工具和最终结构化确认状态均正确为 not_required，说明文字不作为权限或保存事实。该观察如实保留，未润色模型原始记录。

其他限制：演示只检查元数据规则；没有人工确认或真实发布；待确认建议不占位，可能建议同一小时；跨素材不是整批原子事务；每个请求 ID 不允许改内容重提，补齐信息应使用新 ID；本次未实测非 Windows 系统。GitHub URL 和提交版本核对方式见 SUBMISSION.md。

## 提交收尾复核

2026-11-03 仅进行密钥与隐私检查、现有证据摘要复核和文档引用核对，不新增功能，不重新调用真实模型，也未把历史测试标为当日新测试。最终测试仍以上述 2026-11-02 的 83 项报告为准；初次干净环境 73 项报告保留其历史范围。最终提交说明见 [SUBMISSION.md](../SUBMISSION.md)；候选人后续已自行填写人工贡献，并提供 GitHub 仓库地址授权提交。
