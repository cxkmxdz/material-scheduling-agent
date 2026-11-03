# 第 1 题 素材审核与发布排期 Agent

为内容团队读取素材元数据、执行演示规则审核、查询冲突并保存排期草稿。项目只处理草稿；没有发布和代替用户确认的能力。

**本地实现和离线验收可运行。真实 API 对照进度与证据见 examples/real/STATUS.md。Mock 是脚本模拟，不能证明真实模型效果。**

## 评审入口

- 最终提交说明：[SUBMISSION.md](SUBMISSION.md)，包含仓库地址与候选人自行填写的贡献记录
- 最终离线回归 83 项通过：[summary.json](examples/test-results-real-final/summary.json)
- 已通过的真实三组对照：[comparison.json](examples/real/20261102-121118-525417/comparison.json)
- 需求和全部验收点：[01-requirements.md](docs/01-requirements.md)
- 设计和权限边界：[02-solution.md](docs/02-solution.md)
- 实际结果和限制：[03-evaluation.md](docs/03-evaluation.md)
- AI 使用记录：[04-ai-usage.md](docs/04-ai-usage.md)
- 实施复盘：[05-retrospective.md](docs/05-retrospective.md)
- 实际输出索引：[examples/mock/manifest.json](examples/mock/manifest.json)
- 初次离线报告 73 项通过：[summary.json](examples/test-results/summary.json)
- 初次全新环境复测 73 项通过：[summary.json](examples/test-results-clean/summary.json)
- 真实验证状态：[examples/real/STATUS.md](examples/real/STATUS.md)

## 安装

命令在项目根目录执行。需要 Python 3.11+ 和 uv；本次测试环境为 Windows、Python 3.13.5、uv 0.12.3。直接依赖固定版本，`uv.lock` 锁定传递依赖。不使用 Agent 框架。

```powershell
uv sync --locked --extra dev
.venv\Scripts\python.exe -m scheduling_agent.cli --help
```

Linux/macOS 将下列命令中的 `.venv\Scripts\python.exe` 换成 `.venv/bin/python`；本次未实测这些系统。

## 运行正常场景

空数据库会自动初始化。以下时间戳后缀使多次执行不覆盖运行证据；同一数据库上的相同请求返回同一草稿。

```powershell
$runTag = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
.venv\Scripts\python.exe -m scheduling_agent.cli run --mode mock --input examples/inputs/normal.json --db runtime/normal.sqlite --output "runtime/normal-$runTag.json" --trace "runtime/normal-$runTag.jsonl"
.venv\Scripts\python.exe -m scheduling_agent.cli inspect --db runtime/normal.sqlite
```

正常结果为 `completed`、`review_status=passed`、`save_status=saved`，草稿时段为 18:00。`completed` 仅表示本次草稿处理完成。

## 初始化冲突数据和重新运行

`init` 导入演示已确认排期：demo 渠道 2026-11-05 18:00 至 19:00。重复初始化不会删除草稿或重复导入。需要空数据时使用新的数据库文件，无需删除现有数据库。

```powershell
$runTag = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
.venv\Scripts\python.exe -m scheduling_agent.cli init --db "runtime/conflict-$runTag.sqlite"
.venv\Scripts\python.exe -m scheduling_agent.cli run --mode mock --input examples/inputs/normal.json --db "runtime/conflict-$runTag.sqlite" --output "runtime/conflict-$runTag.json" --trace "runtime/conflict-$runTag.jsonl"
```

相同输入在冲突数据下，Mock 补查窗口，保存 19:00 建议且为 `pending_confirmation`。原始 18:00 硬性要求保留，待确认建议不占用时段。

## 运行缺信息和保存故障

```powershell
$runTag = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
.venv\Scripts\python.exe -m scheduling_agent.cli run --input examples/inputs/missing.json --db "runtime/missing-$runTag.sqlite"
.venv\Scripts\python.exe -m scheduling_agent.cli run --input examples/inputs/normal.json --db "runtime/failure-$runTag.sqlite" --fail-saves 2 --output "runtime/failure-$runTag.json" --trace "runtime/failure-$runTag.jsonl"
```

`--fail-saves 2` 让 SQLite 在两次 INSERT 之后实际报错并回滚。Mock 观察首个失败后重试一次；最终 `failed`、`draft_id=null`，数据库没有草稿。`--fail-saves 1` 可演示一次失败后成功。工具层每个素材最多两次新保存尝试。

CLI 退出码：草稿处理 `completed` 为 0；`needs_input/blocked/failed/incomplete` 或启动错误为 2。这些退出码可用于验收，不应把 needs_input 当程序崩溃。

## 测试和重新生成全部证据

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts/verify.py
.venv\Scripts\python.exe scripts/generate_examples.py
```

后两条默认写入带时间戳的 `runtime/` 新目录，不覆盖交付证据。`generate_examples.py` 实际执行 12 组场景，输出 JSON、JSONL、SQLite 内容导出和 SHA256 清单；重复及 ID 冲突场景有意复用数据库，其余独立。`verify.py` 保存 pytest 原始文本、JUnit 和实测版本/数量。需要指定位置时加 `--out <新的目录>`。

## 真实模型配置和对照

首次配置时复制 `.env.example` 为 `.env`，已有配置应保留并在本地编辑。填写 `MODEL_API_KEY` 和支持 Chat Completions function calling 的 `MODEL_NAME`。`MODEL_BASE_URL` 默认为 `https://api.openai.com/v1`；兼容服务填写其给出的基础地址，可能包含 `/v1` 等版本前缀，不加 `/chat/completions`。`MODEL_TIMEOUT_SECONDS` 默认为 30。远端地址必须使用 HTTPS。不要将密钥写进输入 JSON 或提交 Git。

服务地址必须与 key 的签发方匹配；模型名必须是该服务的实际 ID。DeepSeek 官方地址可填写 `https://api.deepseek.com`；项目对该官方端点默认显式禁用 thinking，以支持强制函数调用。也可设置 `MODEL_THINKING=disabled`；对其他端点，该可选字段留空时不会发送。参考 [DeepSeek 官方工具调用文档](https://api-docs.deepseek.com/guides/tool_calls/)。项目不自动选择模型或将失败切换为 Mock。本次实际通过模型为 deepseek-flash。

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
# 在编辑器中填写 .env，不把真实密钥写进命令历史
$runTag = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
.venv\Scripts\python.exe -m scheduling_agent.cli run --mode real --input examples/inputs/normal.json --db "runtime/real-$runTag.sqlite" --output "runtime/real-$runTag.json" --trace "runtime/real-$runTag.jsonl"
.venv\Scripts\python.exe scripts/real_comparison.py
```

真实对照脚本对同一请求和同一模型，仅改变工具数据库或故障条件，依次运行空闲、18:00 占用且 19:00 可用、保存失败。每轮真实模型选择工具；运行器没有预排动作。结果默认在 `examples/real/<时间>/`，SQLite 独立保留在被 Git 忽略的 `runtime/real-databases/`。每次运行创建新目录，不覆盖失败证据。报告逐项核查观察顺序、观察后的模型动作、确认状态和持久记录；API 错误不算场景通过。附输入、数据库导出和 SHA256 清单，不提交 SQLite 文件。

每次模型决策会收到完整请求、函数定义和此前工具观察。接口采用原生 function calling，一轮一条调用或 `finish`，格式参考 [OpenAI 官方 Function calling 文档](https://developers.openai.com/api/docs/guides/function-calling)。HTTP 协议测试使用 `httpx.MockTransport`，同样属于离线测试，不能代替上述真实验证。

## 输入和行为约定

输入样例见 `examples/inputs/`。所有时间必须带时区并对齐整点，每项素材占用 1 小时。搜索窗口为左闭右开 `[start,end)`，长度 1 小时至 7 天，原要求必须完整落入窗口。冲突按同渠道区间重叠计算，接壤不冲突。比较和请求摘要使用 UTC，输出保留原始要求。

审核、确认、保存、任务状态分别输出。未执行审核时 `review_status=null`；保存失败不会生成虚假草稿 ID。硬性时间改变自动为待确认；flexible 允许窗口内替代。符合要求且不待确认的草稿保留时段，但仍不是发布。待确认草稿不保留时段，未来人工确认必须重新查冲突，本项目没有确认入口。

`request_id` 首次注册后绑定规范化请求 SHA256；相同 ID 相同内容逐项复用草稿，相同 ID 不同内容拒绝。material_ids 的顺序和等价时区写法不影响摘要。默认 24 轮模型决策、24 次工具调用，可由 `--max-steps` 和 `--max-tools` 调整；触限返回 `incomplete`，已有已保存草稿仍如实列出。

## 项目和提交状态

`src/scheduling_agent/` 包含模型适配器、循环、工具、SQLite、Trace 和 CLI；`data/` 全是合成资料和演示规则，未接视频内容审核或真实平台。五份交付文档为 Markdown，便于与代码一起审阅。

题号：第 1 题。GitHub URL：[cxkmxdz/material-scheduling-agent](https://github.com/cxkmxdz/material-scheduling-agent)。候选人已自行填写贡献记录，见提交说明和 AI 使用记录。最终版本以本地 `git rev-parse HEAD` 与远端 main 分支的完整 commit SHA 一致为准。仓库当前公开；如后续转为私有，需确保评审账号可读。本次三组真实模型对照已通过，验证范围仍限于本次模型和请求条件。
