# 暂估连续账龄实施计划

> 使用requirement-workflow内置executing-plans串行实施；复用用户已经批准的需求、方案原则和执行顺序，不重复申请确认。

目标：全部八类往来、全部科目层级的暂估业务连续承接对应批次账龄。
架构：复用现有预检、归集及FIFO；等额内部转科目只从账龄流量扣除，保留原借贷列。
技术：本机Python、pandas、pytest；不新增依赖。
设计：docs/superpowers/specs/2026-10-11-temporary-transfers-design.md。

## 阶段清单
- [x] 需求：已获用户批准，后续补充全部八类和下级暂估。
- [x] 设计：确认先识别、再归属及批次承接，保留原发生额。
- [x] 计划：先程序和Git交付，再一次性计算，再更新合并记录。
- [x] 编码及验证：182项通过。
- [x] 验收审查：见对应review文档。
- [x] 交付动作：已获用户明确授权提交推送，实际Git结果以提交历史和远端核验为准。

## 任务1：全层级识别及连续账龄
文件：src/core/current_accounts.py、preflight.py、workflow.py、orchestrator.py、fifo_engine.py；新增temporary_transfers.py和tests/test_temporary_transfers.py。
- [x] 先写真实失败测试：两批暂估200和100，实际核销60，内部转正式100和80，截止日分档应为老140、新100，原账借贷为480和240。
- [x] 运行指定新测试，19项失败，原账龄被重置及下级暂估未识别。
- [x] 新增识别及匹配函数，逐行标注已匹配转科目借贷；FIFO仅扣这些流量，校验平衡。
- [x] 运行本机Python -X utf8 -m pytest tests/test_temporary_transfers.py -q，再运行 -m pytest -q，全部通过。

## 任务2：结果可追溯及文档交付
文件：src/core/report.py、src/gui/step_result.py、README.md。
- [x] 在上述失败测试断言报告承接金额180，补充实际凭证、科目、金额、业务单号来源。
- [x] GUI将转科目记录传给报告；README说明识别顺序、证据规则、缺失证据和部分差额。
- [x] 全量验证与审查；写docs/reviews/2026-10-11-temporary-transfers-review.md。
- [x] 用户已明确授权提交、推送，执行并验证远端提交。

## 后续一次性任务
在通用程序完成后，使用用户已确认名称及新补充别名重算10份；所有原净额保持不变，名称归集改变列示。读取用户当前名称合并记录后更新到35组。11份Excel逐表、逐数核验并使用原生Excel打开检查；先备份校验再覆盖桌面成品。
