# 第二次真实接口尝试

实际服务已改为 api.deepseek.com，模型为 deepseek-flash。三组均返回 HTTP 400，工具调用数为 0，数据库为空，均未通过业务验收。

一次单独诊断仅检查错误体是否涉及 thinking 和 tool_choice，不记录错误原文或密钥，两个标记均为 true。结合 DeepSeek 官方接口说明，当前模型默认 thinking 与 required 工具选择不兼容。之后适配器对该官方端点显式禁用 thinking，并先通过回归测试，再执行新的完整对照。

本目录原始输出、Trace、对照和摘要均保留，不将它们当作保存工具失败的验收证据。
