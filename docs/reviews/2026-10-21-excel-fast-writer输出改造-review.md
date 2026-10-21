# 验收审查：excel-fast-writer 输出层改造（四项目）

日期：2026-10-21
对照文档：docs/requirements/2026-10-21-excel-fast-writer输出改造-requirement.md、docs/superpowers/specs/2026-10-21-excel-fast-writer输出改造-design.md、docs/superpowers/plans/2026-10-21-excel-fast-writer输出改造-plan.md

## 审查范围与逐项对照

| 需求项 | 结果 |
|---|---|
| make_excel.py 单文件重写为一次成型写入（不再逐格写值+刷样式） | 四项目完成；输出路径全程无 openpyxl（test_report/test_writer_layout 断言 Workbook.save 零调用） |
| postprocess 改表计划回调，签名不变 | analyzer/skill/kemu 完成；页签色、备注高亮随一次写入生效 |
| kemu 班福图表自拼 XML（方案 C1） | 完成；openpyxl 可读回 lineChart，图表部件 chart1.xml/drawing1.xml 注册进 zip |
| 不改业务逻辑 | report.py 仅改 finish_layout 与删除死代码 _patch_summary_formulas；writer.py 仅改图表回调与删除裸 to_excel 回退；账龄两项目 report.py 差异段（暂估识别依据）保留 |
| 不保留旧写入路径 | kemu/occupancy 调用处的 make_excel 不可用回退分支删除；输出失败直接抛错 |
| 各项目排版差异保留 | occupancy 表头右对齐、扩展关键词、空表跳过+全空建空表；kemu 合计行显式黑字、空表跳过；均逐项迁移 |

## 审查中发现并已修复的问题

1. 单行数据表的末行边框规则与数据区规则键名相同被整体覆盖（上框丢失）→ 改为 setdefault+update 合并。
2. 页边距默认值与 openpyxl 写出的不一致（openpyxl 实际默认 top/bottom=1、header/footer=0.5）→ 对齐，避免新旧文件边距差。
3. 表头格继承了数字列的数字格式（文本格无视觉效果但字面不同）→ 表头区域覆盖 数字格式=General。
4. 浮点列类型判定漏掉 occupancy/kemu 变体的"非百分比浮点仍按金额"分支 → 金样对比暴露后补回。
5. 空字符串被存成空文本格（旧版 openpyxl 落成空格）→ 与旧行为对齐；occupancy 全空兜底表恢复为真空白 sheet。
6. 冻结 xSplit=0 的字面差异 → 单向冻结不再写 xSplit 属性。

## ponytail-review（过度工程）

写入器核心自 633 行骨架裁剪：未搬迁批注、数据验证、隐藏行、缩放等本项目不用的能力；表计划仅保留项目用到的字段。残余可再裁项：公式格支持（2 行，skeleton 原行为）、合并/条件格式/打印参数（表计划 API 的最小通用层，postprocess 已在用）。结论：Lean already, ship.

## 验证证据（2026-10-21 新鲜运行）

| 项目 | 测试 | 金样对比 | 大表计时（50000行×12列×2表） |
|---|---|---|---|
| account-aging-analyzer | 233 passed（基线 231+新增 2） | 无差异 | 26.52s → 4.18s（约 6.3 倍） |
| account-aging-skill | 295 passed | 无差异 | 同一写入器核心 |
| current-account-occupancy-statistics | 21 passed | 3 处（旧行逐行写行高 vs 新版默认行高，视觉一致，接受） | 同一写入器核心 |
| kemu-counterpart-generator | 167 passed（基线 166+新增图表 1） | 无差异 | 26.5s 级 → 3.82s |

自检：写入器随测试套件验证；对比器（金样目录副本）经 inline-string 兼容补丁后自检通过；kemu 图表经 openpyxl 读回断言。kemu 全套偶发 GUI/文件占用失败经旧代码对照复现（与本次改动无关，单跑恒过）。

## 残余风险与后续事项

1. occupancy 金样 3 处行高表达差异：所有行高 18 由 sheetFormatPr 默认值承担，旧行逐行写 ht=18；Excel 显示一致，未逐格对齐。
2. compare_skeleton 副本打了两个兼容补丁（openpyxl inline string 读取、无填充归一），技能原件未动；后续对比需继续用金样目录副本。
3. C:\Users\27651\.agents\skills\account-aging 技能安装副本未同步本次改造（非目录联结，独立一份）。
4. 桌面 exe 与独立 CLI（kemu）为旧版打包，需重新打包后才包含本次输出层改造。
