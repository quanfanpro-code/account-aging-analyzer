# 暂估FIFO承接纠正实施计划

> 复用用户已批准的需求和执行顺序，串行执行requirement-workflow；不重复询问。

目标：用主流程的FIFO精度处理暂估迁移，取消单据一一对应依赖。
技术：现有Python、pandas、pytest；设计见同目录specs中的temporary-transfers-design。

## 六阶段
- [x] 需求纠正：用户明确取消单据匹配。
- [x] 方案纠正：同一FIFO余额层、内部流量顺序承接。
- [x] 实施计划：先程序，后通知用户补充名称，再重算，最后改名称记录。
- [x] 编码：重写temporary_transfers.py，移除workflow、orchestrator、fifo_engine中的业务单号采集和传递。
- [x] 验收：26项承接测试、全套182项通过；README与领域文档同步纠正。
- [x] 交付动作：用户已授权纠正提交与推送，结果以Git实际记录为准。

## 验证过程
新增无单号无凭证号的行为测试先运行：21项失败、5项通过，证明原匹配方案不能满足FIFO承接。最小实现后26项通过。全套182项通过。断言老140、新100，原借贷410/170，内部金额110按40、20、50顺序承接。检查无单据或税额依赖、原净额不变、截止日后不参与。
代码范围：src/core/temporary_transfers.py、workflow.py、orchestrator.py、fifo_engine.py；tests/test_temporary_transfers.py；README及对应需求、设计、审查文档。

## 后续任务前置条件
程序纠正完成后，先通知用户；等待其补充剩余纯字母单位的全称与归属。此时不启动10份重算、不覆盖Excel，也不修改名称合并记录。资料补齐后按已经确认的本次特殊口径重算并更新记录，既有5项简称决定继续有效。
