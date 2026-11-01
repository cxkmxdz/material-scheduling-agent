# 素材审核与发布排期 Agent AI 使用记录

本交付由 Codex 在用户授权下实际读取计划、编写代码、安装依赖、执行命令和测试、生成示例与文档。此处说明 AI 辅助范围，不能据此推断候选人亲自编写、调试或具备未展示的经历。

## 本次 AI 完成的工作

AI 完整提取并阅读本地 Word《小影笔试 Agent 完整实施计划》的正文及表格顺序，检查当前目录和适用 AGENTS.md，将实现放入新的 scheduling-agent 子目录，保留原文件。AI 编写 Python 包中的 schemas、repository、tools、model、agent、trace、cli，生成合成资料、自动测试、示例及验证脚本，编写 README 与五份 Markdown 文档。

AI 实际通过 uv 安装依赖并生成 uv.lock，调用 pytest 验证业务不变量及接口协议，执行 generate_examples.py 留存实际本地工具输出和 Trace。AI 根据测试失败修复了 INSERT 列数问题，并补充参数校验和脱敏边界。测试结论来自留存的命令输出，不是 AI 口头估计。

模型适配接口参考了 [OpenAI 官方 Function calling 文档](https://developers.openai.com/api/docs/guides/function-calling)，采用可配置的 Chat Completions 兼容端点。业务方案由所给 Word 的范围与验收要求约束。没有调用多 Agent，也没有发布到远端。

## 三种模式的区别

1. Codex 辅助开发：指本次生成、修改及验证代码的过程，不等于项目运行时已连接模型。
2. 项目 Mock：MockModel 为离线脚本，用于验证工具和运行器。示例均标为 mock。
3. 项目真实模型：RealModel 可发起实际 API 函数调用，但本次缺少凭据，尚未运行真实模型验收。接口测试里的 MockTransport 仍是离线模拟。

## 候选人待核实补充

候选人可确认的输入是选题、提供的计划和本次任务约束；除此以外，AI 无法核实其个人贡献、总投入时间、过去项目经历或面试准备情况，不代填这些内容。候选人应在提交前逐项审阅代码，实际运行和解释关键流程，然后按事实补充自己阅读、修改、测试和决策的部分。

建议由候选人填写：实际人工修改的文件或提交、人工验证的方法与结果、能够独立解释的边界与取舍、真实投入时间。未发生的工作保持未完成，不将 AI 生成内容改写为个人亲历。当前文档不是候选人的个人自述。
