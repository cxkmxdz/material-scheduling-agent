# 素材审核与发布排期 Agent 需求说明

本项目依据父目录 Word《小影笔试 Agent 完整实施计划》实现第 1 题。用户为内容团队，目标是形成有审核证据、无已知时段冲突、保留确认权限的排期草稿。成功保存不代表发布。其余题目、网页、多 Agent、部署和生产 Runtime 均不在范围内。

## 输入和资料

CLI 读取 JSON，必填 request_id、material_ids、channel、requested_at、time_requirement、search_window。request_id 为 1 至 100 位字母数字下划线或连字符；素材 ID 不重复，单请求 1 至 20 项；时间必须带时区并对齐整点。窗口从 start 包含至 end 不包含，长 1 小时至 7 天。每项占用 1 小时，原始时段必须完整处于窗口。

本地合成资料包含完整素材 M01/M04、缺 asset_url 和 rights_owner 的 M02、阻断风险 M03/M05、警示风险 M06。工具只审核元数据，不下载或理解视频。DEMO-R001 至 DEMO-R003 为演示规则，不代表小影或任何实际业务标准。

## 输出与完成定义

每项输出 material_id、review_status、risk_reasons、missing_fields、original_requirement、proposed_at、confirmation_status、pending_confirmations、save_status、draft_id、task_status、unfinished_reason、tool_errors。请求级输出包含运行 ID、模式、模型、步数、工具调用数、停止原因、Trace 路径及逐项状态。

| 维度 | 值 | 成功或限制含义 |
| --- | --- | --- |
| 审核 | passed / needs_information / blocked / null | null 表示尚未取得审核证据 |
| 确认 | not_required / pending_confirmation | hard 时间发生改变必须待确认 |
| 保存 | not_attempted / saved / failed | saved 必须对应 SQLite 的实际记录 |
| 任务 | completed / needs_input / blocked / failed / incomplete | completed 仅为草稿处理完成 |

多素材按项独立保存，允许部分完成；聚合优先级为 failed、incomplete、needs_input、blocked、completed。请求级模型/数据库错误为 failed，预算耗尽为 incomplete，不能用局部成功遮蔽未完成项。

## 验收要求

| 编号 | 场景 | 必须满足的判据 |
| --- | --- | --- |
| A01 | 正常 | 读取、审核、查询、保存；数据库存在输出对应草稿 |
| A02 | 缺信息 | 列出缺失字段，请求补充，不保存或补造信息 |
| A03 | 规则阻断 | 展示规则 ID 和原因，不保存可执行排期 |
| A04 | 原时段冲突 | 补查替代；18:00 hard 改 19:00 时保留原要求并待确认 |
| A05 | 无空闲时段 | 窗口内无法排期，不突破边界 |
| A06 | 重复提交 | 同 ID 同内容返回同一草稿，无新增记录 |
| A07 | ID 冲突 | 同 ID 不同摘要明确冲突，原数据不变 |
| A08 | 保存失败 | 故障真实发生，事务回滚，输出失败且无虚假 ID |
| A09 | 预算耗尽 | 步数或工具上限返回 incomplete，保留观察 |
| A10 | 多素材 | 所有子项分别报告，唯一键覆盖每项，部分失败可见 |
| A11 | 动态真实决策 | 同一请求仅改工具数据，真实模型观察后动作变化；再测真实保存失败 |
| A12 | 可追溯性 | 至少三组实际输入输出及 Trace；标注 mock/real，密钥脱敏 |
| A13 | 工具边界 | 拒绝伪造审核、缺失证据、擅自确认、发布、窗口外保存 |
| A14 | 可复现交付 | 固定依赖、README、五份文档、测试和示例；不提交密钥或数据库 |

A11 尚需模型配置，不能以脚本模拟或假 HTTP 返回证明通过。最终提交还需题号、可访问的 GitHub URL 和 commit SHA；本次授权不包括向远端推送。
