# 第 1 题 素材审核与发布排期 Agent 提交说明

题号：第 1 题。

GitHub 仓库地址：[https://github.com/cxkmxdz/material-scheduling-agent](https://github.com/cxkmxdz/material-scheduling-agent)。默认分支为 main，仓库当前公开。

代码与真实模型证据基准 commit：`057fe6e18afdff870a0fbdf7a36a5fbe7c1112db`。收尾仅调整文档与审查记录；正式提交时以 `git rev-parse HEAD` 获取最终 commit SHA，并与远端实际提交核对。

## 项目简介

项目为内容团队提供素材元数据审核、排期冲突查询和草稿保存。真实模型逐轮选择工具，观察工具返回后决定补查、提出替代时段、重试或结束。程序验证审核及查询证据，保护硬性时间的确认权限，并使用 SQLite 事务和唯一约束实现逐素材幂等、保存时冲突复查及失败回滚。只处理草稿，没有实际发布或代替用户确认的入口。

实现使用 Python、CLI、SQLite、Pydantic、httpx 和 pytest，不使用 Agent 框架。支持 OpenAI 风格 Chat Completions 原生函数调用，提供 real 与明确标注的离线 Mock 两种模型适配器。完整说明见 [README](README.md)、[需求](docs/01-requirements.md)与[技术方案](docs/02-solution.md)。

## 运行入口

在仓库根目录执行以下 PowerShell 命令；已实测环境为 Windows、Python 3.13.5、uv 0.12.3。依赖由 uv.lock 锁定。

```powershell
uv sync --locked --extra dev
.venv\Scripts\python.exe -m scheduling_agent.cli run --mode mock --input examples/inputs/normal.json
.venv\Scripts\python.exe -m pytest -q
```

真实模型需在本地 `.env` 配置 MODEL_API_KEY、MODEL_NAME 和与 key 匹配的 MODEL_BASE_URL；MODEL_TIMEOUT_SECONDS 可选。密钥不在聊天中发送，也不随仓库提交。DeepSeek 官方端点默认显式禁用 thinking；其他兼容端点可选配置 MODEL_THINKING=disabled。配置完成后运行：

```powershell
.venv\Scripts\python.exe scripts/real_comparison.py
```

真实脚本每次写入新的 examples/real/时间戳目录；数据库在被忽略的 runtime 中。更多场景、故障注入及证据生成命令见 README。CLI 的 completed 退出码为 0，needs_input、blocked、failed、incomplete 或启动错误退出码为 2。

## 测试结果

2026-11-02 最终离线回归实际为 **83 项通过，0 失败，0 错误，0 跳过**。覆盖正常排期、缺信息、规则风险、时段冲突、无可用时段、重复提交、请求 ID 冲突、保存失败和回滚、预算耗尽、多素材、确认权限、并发幂等与接口错误等。

证据入口为[最终 pytest 报告](examples/test-results-real-final/summary.json)与[12 组实际 Mock 运行清单](examples/mock/manifest.json)。初次测试及初次全新虚拟环境复测均为 73 项通过，是早期版本的历史报告；不把它们当作最终 83 项的全新环境复测。Mock 和假 HTTP 测试只证明离线流程、工具及协议，不证明真实模型决策效果。

2026-11-03 的收尾工作只复核已有报告、产物摘要和引用，不新增功能、不重跑付费 API，不将旧结果冒充当日新运行。

## 真实模型验证范围

2026-11-02 实际使用 api.deepseek.com 的 deepseek-flash，thinking disabled。三组使用同一个 req-001 请求、M01 素材、demo 渠道、18:00 hard 要求和 18:00–21:00 窗口，提示和工具一致，仅改变独立数据库的占用或保存故障条件。

| 条件 | 模型根据观察采取的动作 | 实际结果 |
| --- | --- | --- |
| 原时段空闲 | 查询后保存原时段 | 18:00；completed / saved / not_required；数据库 1 草稿 |
| 原时段冲突 | 观察冲突后补查完整窗口，提出 19:00 建议 | completed / saved / pending_confirmation；保留原要求；建议不占位 |
| 保存工具失败 | 观察 SAVE_FAILED 后重试一次，再次失败后结束 | failed / save_status failed；draft_id null；数据库为空 |

三组均达到预定验收判据，共 17 次真实模型决策响应，均为 HTTP 200。保存故障是在真实 SQLite INSERT 后触发错误并回滚；该场景任务状态 failed 是预期正确结果。

入口为[三组对照结果](examples/real/20261102-121118-525417/comparison.json)、[输出与 Trace 索引](examples/real/20261102-121118-525417/README.md)、[独立复核](examples/real/20261102-121118-525417/review.json)及[评估文档](docs/03-evaluation.md)。此前鉴权失败和 HTTP 400 的两轮记录保留在 examples/real 中，未当作业务场景通过，也未覆盖。真实 Trace 包含简短公开决策说明、工具观察、响应 ID 和 token 数，不包含密钥或内部思维链。

## 已知限制

- 真实验证仅覆盖一个服务、一个模型、同一请求的三种条件；未进行多次稳定性、跨模型或成本基准。
- 演示规则只检查合成素材元数据，未下载或理解真实视频，不代表真实业务审核标准。
- 没有人工确认和真实发布功能；待确认建议不占位，未来确认前必须再次检查冲突。
- 多素材逐项保存，不保证整批原子性；同一 request_id 内容不可修改，补齐信息应使用新 ID。
- 每项占用固定 1 小时，时间需带时区并对齐整点；默认 24 轮决策、24 次工具调用，大批量可能触限。
- 本次实测 Windows；Linux/macOS 和其他 Python 版本未实测。模型简短说明中存在措辞不够精确的个例，权限与保存事实以工具和结构化状态为准，原始记录未润色。

## 密钥与隐私边界

收尾检查覆盖已跟踪工作文件及现有本地 Git 历史，结合当前本地 key 精确匹配、常见凭据格式、隐私格式与证据引用检查；结果记录于 examples/submission-review.json。扫描不能证明不存在所有未知格式的秘密。

本地 `.env` 保留在本机并被忽略，不是交付文件；数据库、虚拟环境和 runtime 也不随 Git 提交。原始证据保留了不含用户主目录名的本机工作目录路径、请求时间、合成业务数据、模型响应 ID 和 token 数。Git 提交仍含标准作者姓名/邮箱元数据，未擅自改写；候选人在选择公开或私有仓库前应核对这些作者信息的公开范围。

## AI 辅助与人工贡献

AI 辅助范围和实际验证方式见 [04-ai-usage.md](docs/04-ai-usage.md)。Git 作者信息不能证明某段代码由候选人独立编写。

本项目使用 Codex 辅助完成方案细化、代码实现、测试和文档整理。我主要负责阅读题目、确定选题和项目范围，并核对交付内容是否覆盖题目要求。在验证阶段，我查看了测试结果和运行记录，重点关注时段冲突后的调整、待确认状态、重复提交及保存失败的处理。通过本次项目，我进一步理解了模型决策循环与固定流程的区别，以及业务工具校验和运行记录对验证 Agent 行为的作用。项目代码主要由 AI 辅助生成，我目前对部分实现细节的理解仍需加强，后续会继续阅读代码并尝试修改验证。

## 提交版本与访问方式

上述人工贡献由候选人自行填写，不据此追加未经候选人提供的经历或耗时。正式提交时同时提供题号、上述 GitHub URL 和完整 commit SHA；完整 SHA 通过 `git rev-parse HEAD` 获取，并与远端 main 分支核对。当前仓库可公开读取；若可见性发生变化，应再次确认评审访问权限。
