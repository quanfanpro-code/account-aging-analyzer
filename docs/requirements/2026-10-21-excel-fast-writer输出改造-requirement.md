# 需求：四大审计工具 Excel 输出层 excel-fast-writer 改造

日期：2026-10-21
状态：待确认（CHECKPOINT 1）

## 背景与问题

四个同源审计工具（往来占用统计、序时账对方科目、账龄分析工具、账龄分析 Skill）的 Excel 结果文件都由各自的 make_excel.py 生成，实现方式相同：openpyxl 先逐格写一遍值，再逐格刷一遍字体、填充、边框、数字格式，最后整本保存。大表（数万行）导出时是逐格对象操作加两次整表序列化，速度慢。

各项目在 make_excel 之上还有排版后处理（postprocess 回调，保存前逐格处理）：账龄两项目设置结果表页签颜色、备注列宽、备注换行行高和【反向余额重分类】【票据连续计龄】黄底红字；序时账对方科目在此加入班福折线图；往来占用统计无后处理。

excel-fast-writer 技能提供"值与排版在同一次 XML 拼接里写入"的写入器骨架（标准库实现，含样式去重、共享字符串、列样式兜底、条件格式、批注、打印设置）和金样语义对比器。

## 用户与使用场景

财务、审计人员用这四个工具导出大型审计底稿，导出等待时间主要耗在写 Excel 上；用户要求改造后"重点是快"，输出效果接近原样即可，不强求一比一还原。

## 功能范围

1. 将模板项目的 make_excel.py 重写为 excel-fast-writer 一次成型写入，不再使用 openpyxl 逐格写值和逐格刷样式；对外行为保持：接收 DataFrame 或 [(名称, df), ...]，输出完整排版 xlsx，返回输出路径。
2. 排版后处理随接口调整：页签颜色、备注高亮等由 postprocess 回调改为表计划参数/区域样式，在写入前一并生效；各项目调用处（report.py、writer.py、excel_io.py）只改排版参数传递，不改数据组织。
3. 模板先行：先改造 account-aging-analyzer（本仓库）并验证，其余三个项目复用同一写入器适配各自的调用处与版本差异（occupancy 版有关键词与对齐变体，kemu 版有图表）。
4. 交付：四项目 README 同步更新（含顶部日期式更新说明），分别提交并推送 GitHub（用户已授权）。

## 明确不做的内容

- 不改业务计算、匹配、账龄逻辑（build_frames、pipeline 等数据组织代码不动）。
- 不改读取输入的代码（各项目 reader、excel_io 的读取部分）。
- 不追求与旧输出一比一：值与结构必须一致，格式细节（样式去重顺序、边距默认值等）允许差异。
- 不保留旧 openpyxl 写入路径作为回退开关（excel-fast-writer 明确禁止两套路径并存）。
- _patch_summary_formulas 无任何调用，属死代码，不搬运。
- 不为几百行的小表做单独优化，统一走新写入器。

## 约束与风险

- 接口兼容：上层调用文件改动仅限排版参数传递与回调替换。
- kemu 班福图表：excel-fast-writer 写入器不含图表部件，实现方式（自拼 chart XML / 其他）在方案阶段取舍。
- occupancy 与 kemu 的 make_excel 是带差异的变体，复用时保留各自差异，不强行合并成一份跨仓库代码。
- C:\Users\27651\.agents\skills\account-aging 是独立安装副本（非目录联结），D 盘正本改造后需同步或提醒用户。
- 改前备份：C:\Users\27651\BackUp\项目名_年月日_时分秒\。
- 金样：改造前先用当前代码在各项目生成旧输出留作金样，改后逐项对比。

## 验收标准

1. 四项目现有测试全部通过。
2. 金样对比：值、工作表结构、数字格式一致；关键标识（表头深蓝底白字 Arial 11、合计行浅蓝底加粗、上下框线、页签颜色、备注黄底红字、冻结首行、列宽估算）接近；差异清单逐项确认或排除。
3. excel-fast-writer 交付检查通过：写入器自检、对比器自检退出码为 0。
4. 大表导出改造前后各计时一次，记录提升幅度。
5. README 日期式更新说明已更新；四项目分别提交并推送成功。

## 调研摘要与来源

- excel-fast-writer 技能：C:\Users\27651\.agents\skills\excel-fast-writer（writer_skeleton.py、compare_skeleton.py、SKILL.md）。
- 四项目 make_excel.py 现状核实（2026-10-21）：行数 311/275/265/265；analyzer 与 skill 版完全相同；调用链 report.py→make_excel（账龄两项目）、src/io/writer.py→make_excel（kemu，含 LineChart）、excel_io.py→make_excel（occupancy）。
- 本地四项目与 GitHub 最新提交一致（gh 核实，2026-10-21）。

## 待确认项

1. 模板项目定为 account-aging-analyzer（先改并验证，其余复用），是否认可。
2. kemu 班福图表实现方式（阶段 2 给出方案后选择）。
3. .agents 技能安装副本的同步方式（交付阶段处理）。
