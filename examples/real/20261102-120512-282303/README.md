# 首次真实接口尝试

2026-11-02 实际向配置的 API 发送了三组请求。配置模型名为 deepseek，但服务地址仍为 api.openai.com/v1。三组均返回 MODEL_AUTH_ERROR，各自工具调用数为 0，数据库草稿数为 0。

本次证明了真实接口的鉴权失败被明确报告，不能验证模型的业务决策。free、occupied、save_failure 均未达到验收要求；尤其 save_failure 未执行保存工具，不能算已验证保存失败处理。

comparison.json、各输出、Trace 及数据库导出为当次运行实际产物，按原样保留。原适配器将 HTTP 401 和 403 合并为同一错误码，因此不为本次补造具体状态码。后续版本新增 HTTP 状态和成功响应 ID、模型名、token 数记录，但不采集原始思维链。
