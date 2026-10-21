# 设计：四大审计工具 Excel 输出层 excel-fast-writer 改造

日期：2026-10-21
需求文档：docs/requirements/2026-10-21-excel-fast-writer输出改造-requirement.md
状态：待批准（CHECKPOINT 2）

## 方案比较

### 维度一：写入器代码放哪

| 方案 | 说明 | 评估 |
|---|---|---|
| A. 单文件重写（推荐） | make_excel.py 一个文件内含写入器核心（XML 拼接、样式去重、打包）+ 摩根系排版层，约 600 行 | 与现状一致（四项目根目录各一份 make_excel.py），调用方 import 不变，四项目同步只复制一个文件 |
| B. 两文件分层 | excel_writer.py 通用写入器 + make_excel.py 排版层 | 层次更清晰，但四项目 × 2 文件同步，多一层 import，对单用途项目是过度设计 |
| C. 共享库/pip 包 | 跨仓库共享一份写入器 | 否：账龄 Skill 要独立打包分发、三个桌面工具要独立运行，引入包管理依赖违背现状（否决，不再讨论） |

### 维度二：排版后处理接口

现状：postprocess(wb) 回调在保存前收到 openpyxl Workbook，逐格改格式。

| 方案 | 说明 | 评估 |
|---|---|---|
| A. 计划回调（推荐） | make_excel 签名不变，postprocess 改收表计划列表（写入前的中间结构，含值、列宽、区域样式、页签色、图表字段，提供 apply_overrides 等方法），调用处改写回调体 | 签名兼容；调用处改动集中在 report.py 的 finish_layout、kemu writer.py 的图表回调；业务排版规则（备注高亮的【】检测、行高计算）留在各项目，不塞进通用层 |
| B. per-sheet 字典参数 | make_excel(sheets, path, sheet_options={...}) | 表达不了"按备注内容动态定行高/触发高亮"这类规则，除非把规则塞进通用层，职责混乱 |
| C. 调用处直接构建表计划 | make_excel 只收表计划 | 调用处要从"组织 DataFrame"改为"组装计划"，侵入业务数据组织代码，违背不动业务逻辑的约束 |

### 维度三：kemu 班福图表（需用户选择）

现状：openpyxl LineChart，固定插在"班福分析"表 H2，分类=B 列 2-10 行（首位数 1-9），数据=D:E 列 1-10 行，带标题和轴标题。

| 方案 | 说明 | 评估 |
|---|---|---|
| C1. 写入器内置最小折线图（推荐） | 表计划加"图表"字段，写入器按固定结构拼 chart1.xml + drawing1.xml + rels 并注册进 zip | 一次成型全程无 openpyxl；只支持本项目需要的折线图场景，不做通用图表引擎；一次性工作量约 100-150 行 |
| C2. openpyxl 生成图表部件后合并 | 用 openpyxl 单独生成只含图表的最小文件，抽取 chart/drawing XML 合入 zip | 绕一圈复杂度不低，仍依赖 openpyxl 参与输出 |
| C3. 保留二次打开加图 | 主文件一次成型，再 load_workbook 加图保存 | 图表只有一张，但重开重存整本大文件，正是本次要消灭的模式（否决） |

## 推荐方案（A + A + C1）

### 写入器来源

以 excel-fast-writer 技能的 writer_skeleton.py（633 行，纯标准库，含自检）为基础裁剪合并：保留 StyleBook 样式去重、共享字符串、列样式兜底、列宽/行高/合并/冻结/条件格式/打印设置，增加摩根系排版层（沿用现有列类型推断、列宽估算、深海蓝常量）与本次需要的折线图拼接。compare_skeleton.py（399 行）仅在开发期用于金样对比，不进入四项目仓库。

### 对外接口（与现状对齐）

```python
make_excel(data, output_path, sheet_name='Sheet1', postprocess=None) -> str
# data: DataFrame 或 [(名称, df), ...]，行为同现状（空表写占位行、非法字符清洗、sheet 名 31 字限制）
# postprocess(表计划列表): 写入前回调；表计划提供 标签色/区域覆盖/条件格式/图表 等字段与方法
```

### 数据流（改造后）

调用方组织 DataFrame（不动）→ make_excel 转成表计划（值矩阵 + 列类型 + 列宽 + 五层样式）→ postprocess 改计划（页签色、备注列宽/换行/行高、黄底红字覆盖、图表定义）→ 一次遍历拼全部 sheet XML + styles.xml + sharedStrings.xml + 图表部件 → zip 打包输出。全程无 openpyxl、无二次读写。

### 各项目落地

| 项目 | 改动文件 | 内容 |
|---|---|---|
| account-aging-analyzer（模板） | make_excel.py 重写；src/core/report.py 的 finish_layout 改为计划操作；删除死代码 _patch_summary_formulas | 页签色 0070C0、备注列宽 72 换行行高、【反向余额重分类】【票据连续计龄】黄底红字加粗，全部变为计划字段 |
| account-aging-skill | make_excel.py 与模板完全相同直接复制；src/core/report.py 同步；scripts/计算往来账龄.py 打包入口核对 | 无排版差异 |
| current-account-occupancy-statistics | make_excel.py 在写入器核心一致的前提下保留本版排版差异（表头右对齐、更多关键词等）；excel_io.py 调用处不变（无 postprocess） | 保留变体差异 |
| kemu-counterpart-generator | make_excel.py 保留本版差异（SUM_FONT 黑色、0-1 浮点 pct 细化、_clean_cell）；src/io/writer.py 的图表回调改为传图表字段；移除"裸 to_excel"回退分支（make_excel 必然可用，输出失败直接报错） | 图表走 C1 |

openpyxl 保留为依赖：读取输入仍用它，四项目 requirements.txt 不变。

### 错误处理

非法值（NaN/NaT）沿用 kemu 版 _clean_cell 置空思路在写入器统一处理；sheet 名非法字符清洗与 31 字截断沿用现状；写入失败向上抛异常，由各调用方现有 try/except 报告，不静默降级（与需求"不留旧路径当回退"一致）。

### 测试策略

1. 改造前：四项目各生成金样输出（analyzer/skill 用模拟数据跑 ReportGenerator，kemu/occupancy 用各自测试或模拟数据），存 BackUp 目录；旧版大表计时一次留基线。
2. 写入器自检、compare_skeleton 自检退出码 0。
3. 金样语义对比：值、工作表结构、数字格式必须一致；格式差异逐项审查（用户已放宽为"接近"）。
4. 现有测试套件全过：现有测试用 openpyxl 读输出断言语义（sheet 名、值、对齐、占位行），新输出照样可读可断言；个别断言写入内部细节的测试按语义改写。
5. 新增最小测试：图表部件存在且能被 openpyxl 读取、postprocess 计划回调生效（页签色、备注高亮）。
6. 新版大表计时，与基线对比记录提升。

### 迁移与回滚

顺序：analyzer（模板）→ skill（复制适配）→ occupancy → kemu（图表）。每项目独立验证后再进下一个。
回滚：改前整目录备份至 C:\Users\27651\BackUp\项目名_年月日_时分秒\；git 工作区亦可恢复；金样与对比结果作为质量闸门。

### CONTEXT 与 ADR

- CONTEXT.md 不更新：本次不改业务术语，CONTEXT.md 只收术语不含实现。
- 模板项目 docs/adr/0001：记录"Excel 输出弃用 openpyxl 逐格两遍，改为标准库一次成型 XML 写入"的决策与理由（难逆转、有真实取舍、后人会问为什么不用 openpyxl）。
