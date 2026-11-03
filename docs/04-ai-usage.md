# 素材审核与发布排期 Agent AI 使用记录

本交付由 Codex 在用户授权下实际读取计划、编写代码、安装依赖、执行命令和测试、生成示例与文档。此处说明 AI 辅助范围，不能据此推断候选人亲自编写、调试或具备未展示的经历。

## 本次 AI 完成的工作

AI 完整提取并阅读本地 Word《小影笔试 Agent 完整实施计划》的正文及表格顺序，检查当前目录和适用 AGENTS.md，将实现放入新的 scheduling-agent 子目录，保留原文件。AI 编写 Python 包中的 schemas、repository、tools、model、agent、trace、cli，生成合成资料、自动测试、示例及验证脚本，编写 README 与五份 Markdown 文档。

AI 实际通过 uv 安装依赖并生成 uv.lock，调用 pytest 验证业务不变量及接口协议，执行 generate_examples.py 留存实际本地工具输出和 Trace。AI 根据测试失败修复了 INSERT 列数问题，并补充参数校验和脱敏边界。测试结论来自留存的命令输出，不是 AI 口头估计。

模型适配接口参考了 [OpenAI 官方 Function calling 文档](https://developers.openai.com/api/docs/guides/function-calling)，采用可配置的 Chat Completions 兼容端点。业务方案由所给 Word 的范围与验收要求约束。没有调用多 Agent。后续 GitHub 提交按候选人明确授权执行，不涉及业务平台发布。

## 三种模式的区别

1. Codex 辅助开发：指本次生成、修改及验证代码的过程，不等于项目运行时已连接模型。
2. 项目 Mock：MockModel 为离线脚本，用于验证工具和运行器。examples/mock 中的离线示例标为 mock，examples/real 中的实际接口记录标为 real，彼此不替代。
3. 项目真实模型：初次交付缺少凭据；2026-11-02 用户在本地填写配置，先出现鉴权失败，修正地址后出现 thinking 与 required 工具选择不兼容的 HTTP 400。AI 修正评估判据、补充 DeepSeek 兼容配置和响应元数据记录，再实际运行 deepseek-flash 完成三条件对照。旧失败证据及最终真实成功 Trace 全部保留。接口测试里的 MockTransport 仍是离线模拟。

## 候选人自行填写的贡献记录

本项目使用 Codex 辅助完成方案细化、代码实现、测试和文档整理。我主要负责阅读题目、确定选题和项目范围，并核对交付内容是否覆盖题目要求。在验证阶段，我查看了测试结果和运行记录，重点关注时段冲突后的调整、待确认状态、重复提交及保存失败的处理。通过本次项目，我进一步理解了模型决策循环与固定流程的区别，以及业务工具校验和运行记录对验证 Agent 行为的作用。项目代码主要由 AI 辅助生成，我目前对部分实现细节的理解仍需加强，后续会继续阅读代码并尝试修改验证。
