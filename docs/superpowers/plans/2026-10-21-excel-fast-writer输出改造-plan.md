# 四大审计工具 Excel 输出层 excel-fast-writer 改造 实施计划

> **For agentic workers:** 用户未授权子代理，按 executing-plans.md 串行执行。步骤用 checkbox 跟踪。

**Goal:** 四个同源审计工具的 make_excel.py 从 openpyxl 逐格两遍写入改为标准库一次成型 XML 写入，输出语义不变、速度大幅提升。

**Architecture:** 以 excel-fast-writer 技能的 writer_skeleton.py 为底合并摩根系排版层成单文件 make_excel.py；postprocess 回调改收表计划列表；kemu 折线图自拼 chart XML；四项目各持同源副本，保留各自排版差异。

**Tech Stack:** Python 3.14 标准库（zipfile、XML 字符串拼接）、pandas（输入 DataFrame）、openpyxl（仅读输入与测试断言）。

**Spec:** docs/superpowers/specs/2026-10-21-excel-fast-writer输出改造-design.md

## Global Constraints

- 解释器固定：`C:\Users\27651\AppData\Local\Programs\Python\Python314\python.exe`（下称 `$PY`）。
- 不改业务计算与数据组织代码；调用处只改排版参数传递。
- 不保留 openpyxl 写入路径与裸 to_excel 回退；openpyxl 仅用于读输入、读输出断言。
- `make_excel(data, output_path, sheet_name='Sheet1', postprocess=None) -> str` 签名不变；postprocess 收表计划列表。
- 每项目改前整目录备份至 `C:\Users\27651\BackUp\项目名_20261021_HHMMSS\`（排除 .git、__pycache__）。
- 金样目录：`C:\Users\27651\BackUp\excel-fast-writer金样_20261021\`。
- 推进闸门：当前项目测试全绿 + 金样对比通过，才进下一项目。
- 顺序：任务0 准备 → 任务1-2 analyzer → 任务3 skill → 任务4 occupancy → 任务5 kemu → 任务6 汇总验证 → 任务7 交付文档。
- 中文新文件 UTF-8 with BOM；提交信息中文。

---

### 任务 0：准备与基线

**Files:** 只读 + 金样/备份目录产出，不改仓库代码。

- [ ] **0.1 备份四项目**（robocopy /E /XD .git __pycache__ .pytest_cache，robocopy 退出码 ≤7 为成功）
- [ ] **0.2 四项目现有测试基线**：各项目目录跑 `$PY -m pytest tests -q`，记录通过/失败数（基线必须全绿；若某项目测试本就失败，记录并区分既有失败）
- [ ] **0.3 生成金样**：
  - analyzer/skill：先看 `集成验证_往来全自动化.py` 的调用方式；若可非交互直接跑，用其输出生成金样；否则用 make_excel 构造代表性 sheets（多 sheet + 空表占位 + 合计行 + 长备注列）生成
  - kemu：构造 sheets（含"班福分析"表）走 `save_output_file`，金样必须含图表
  - occupancy：走 `excel_io.py` 导出函数或 make_excel 构造 sheets
- [ ] **0.4 基线计时**：临时脚本生成 50000 行 × 12 列 DataFrame，旧版 make_excel 计时 3 次取中位，记录
- [ ] **0.5 通读** writer_skeleton.py（633 行）与 compare_skeleton.py（399 行），确认裁剪范围与接口

### 任务 1：analyzer make_excel.py 重写

**Files:**
- Modify: `C:\Users\27651\Documents\Code\account-aging-analyzer\make_excel.py`（整文件重写）
- Test: `tests\test_excel_writer_plan.py`（新建）

**Interfaces:**
- Produces: `make_excel(data, output_path, sheet_name='Sheet1', postprocess=None) -> str`；postprocess(plans) 收表计划列表，表计划含 `标签色` 属性与 apply_theme/apply_columns/apply_rows/apply_overrides/apply_conditions 方法、`图表` 字段（任务 5 使用）

- [ ] **1.1 RED**：新建 `tests/test_excel_writer_plan.py`：

```python
# -*- coding: utf-8 -*-
"""postprocess 计划回调测试：回调收到表计划，改动落到输出文件。"""
import pandas as pd
from openpyxl import load_workbook
from make_excel import make_excel


def test_postprocess_收到表计划并可设页签色(tmp_path):
    plans = []
    def 记录(pl):
        plans.extend(pl)
        pl[0].标签色 = '0070C0'
    out = make_excel(pd.DataFrame({"金额": [1.0]}), str(tmp_path / "o.xlsx"),
                     postprocess=记录)
    assert len(plans) == 1            # 回调确实收到了表计划
    wb = load_workbook(out)
    assert wb["Sheet1"].sheet_properties.tabColor.rgb.endswith("0070C0")


def test_postprocess_区域覆盖落到单元格样式(tmp_path):
    def 高亮(pl):
        pl[0].apply_overrides({"B2": {"底色": "FFF2CC", "字色": "9C0006", "加粗": True}})
    out = make_excel(pd.DataFrame({"备注": ["【反向余额重分类】测试"]}), str(tmp_path / "o.xlsx"),
                     postprocess=高亮)
    wb = load_workbook(out)
    cell = wb["Sheet1"]["B2"]
    assert cell.fill.fgColor.rgb.endswith("FFF2CC")
    assert cell.font.bold is True
```

跑 `$PY -m pytest tests/test_excel_writer_plan.py -v`，预期 FAIL（旧版 postprocess 收 Workbook，无 `标签色`/`apply_overrides` 属性）。

- [ ] **1.2 GREEN**：重写 make_excel.py：
  - 写入器核心（自 writer_skeleton.py 裁剪）：`StyleBook`（字体/填充/边框/数字格式/xf 去重）、`_SharedStrings`、`col_letter`、`_num`（%.16g）、`new_sheet`、`apply_theme/apply_columns/apply_rows/apply_overrides/apply_conditions`、`_sheet_xml`（子元素顺序 sheetPr→dimension→sheetViews→sheetFormatPr→cols→sheetData→autoFilter→mergeCells→conditionalFormatting→dataValidations→printOptions→pageMargins→pageSetup）、`write_workbook`（[Content_Types]/rels/workbook/styles/sharedStrings 拼接 + zipfile compresslevel=1；styles.xml 预置字体 0 号位、填充 none/gray125、xf 0 号位；calcPr fullCalcOnLoad）
  - 表计划增加 `标签色` 属性 → sheetPr tabColor
  - 摩根系排版层（沿用现有逻辑不改行为）：`_infer_column_type`、`_char_width`、`_estimate_column_width`、常量（THICK/DASHED/上下框线、HDR 1F4E79 白字 Arial11 加粗居中、数据蓝字/黑字、SUM D6E4F0、FMT、ROW_HEIGHT=18、A 列宽 2、列宽 10~50）→ 映射为 apply_columns（数字格式+对齐按列）+ apply_rows（第 1 行表头、末行合计）+ apply_overrides（合计行覆盖）
  - NaN/NaT 置空；sheet 名 `re.sub(r'[\\/*?:\[\]]','_')[:31]`；空表写"（无数据）"占位行；无 postprocess 时直接写
- [ ] **1.3 VERIFY**：`$PY -m pytest tests -q` 全绿（现有 test_make_excel.py 3 个测试原样通过）
- [ ] **1.4 金样对比**：`$PY compare_skeleton.py 金样 analyzer新输出`（值、sheet 结构、数字格式必须一致；格式差异逐项核对，页签色/备注高亮此时应一致或仅因 postprocess 未适配而缺失——缺失项在任务 2 恢复）
- [ ] **1.5 计时**：同 0.4 脚本跑新版，记录对比

### 任务 2：analyzer report.py 适配

**Files:**
- Modify: `src\core\report.py`（finish_layout 与删除 `_patch_summary_formulas`）
- Test: 既有 `tests/test_report.py`、`tests/test_重分类备注.py` 为行为网

- [ ] **2.1 RED**：在 test_report.py 补一个断言页签色与备注高亮落到输出文件的测试（若无）：

```python
def test_结果表页签色与备注高亮(tmp_path, ...):
    # 用既有 fixture 生成输出后：
    wb = load_workbook(out)
    assert wb["账龄计算结果"].sheet_properties.tabColor.rgb.endswith("0070C0")
    ws = wb["期末余额构成及账龄依据"]
    # 备注列存在且含【反向余额重分类】的行有黄底
```

先跑确认失败（当前 postprocess 尚未适配）。
- [ ] **2.2 GREEN**：`generate()` 的 finish_layout 改为接收 plans：按名称取表计划 → 设 `标签色='0070C0'`；对"账龄计算结果""期末余额构成及账龄依据"复刻 `_highlight_remarks` 行为：找"备注"列 → 列宽 72 → 逐行按内容宽度 `15*ceil(宽/70)` 设行高（apply_rows 区域覆盖）→ 含【反向余额重分类】/【票据连续计龄】的格子黄底 FFF2CC、红字 9C0006、加粗；删除 `_patch_summary_formulas` 死代码与 load_workbook import
- [ ] **2.3 VERIFY**：全套件绿 + 金样对比（备注高亮、页签色语义与金样一致）

### 任务 3：account-aging-skill 同步

**Files:**
- Modify: `D:\BaiduSyncdisk\workbuddy skills\account-aging\make_excel.py`、`src\core\report.py`
- 核对: `scripts\计算往来账龄.py` 引用

- [ ] **3.1** diff 确认 skill 与 analyzer 的 make_excel.py、src/core/report.py 改造前完全一致（不一致处先清单化）
- [ ] **3.2** 复制新版 make_excel.py 与 report.py；备份先行（同任务 0 规则，skill 目录单独备份）
- [ ] **3.3** grep `scripts/计算往来账龄.py` 与 tests 中 make_excel/postprocess 引用，适配差异
- [ ] **3.4 VERIFY**：`$PY -m pytest tests -q` 全绿 + skill 金样对比

### 任务 4：current-account-occupancy-statistics 适配

**Files:**
- Modify: `C:\Users\27651\Documents\Code\current-account-occupancy-statistics\make_excel.py`
- 核对: `excel_io.py` 调用处（无 postprocess，预期零改动）

- [ ] **4.1** 从旧 occupancy make_excel.py 提取差异清单：表头右对齐、HDR 色与常量、SUM_KEYWORDS（含 汇总/subtotal）、关键词英文扩展、pct 判定规则、_clean_cell 有无
- [ ] **4.2 RED**：确认现有测试基线绿（tests/ 目录），必要时补"右对齐表头"断言测试
- [ ] **4.3 GREEN**：新写入器核心（与模板版一致）+ occupancy 排版差异层
- [ ] **4.4 VERIFY**：测试全绿 + occupancy 金样对比

### 任务 5：kemu-counterpart-generator 适配（图表）

**Files:**
- Modify: `C:\Users\27651\Documents\Code\kemu-counterpart-generator\make_excel.py`、`src\io\writer.py`
- Test: `tests\` 新增图表测试

**Interfaces:**
- Consumes: 表计划 `图表` 字段：`{"类型":"折线", "表":"班福分析", "位置":"H2", "标题":..., "X轴标题":..., "Y轴标题":..., "分类引用":("'班福分析'!B2:B10"), "系列":[("'班福分析'!D1:D10"),("'班福分析'!E1:E10")]}`（系列首行为标题）
- Produces: chart1.xml + drawing1.xml + 对应 rels 注册进 zip，openpyxl 可读回

- [ ] **5.1 RED**：新增 `tests/test_图表.py`：

```python
# -*- coding: utf-8 -*-
"""表计划图表字段应产出可读取的折线图。"""
import pandas as pd
from openpyxl import load_workbook
from make_excel import make_excel


def test_图表字段生成折线图(tmp_path):
    stats = pd.DataFrame({"首位数": list(range(1, 10)), "实际比率": [0.1] * 9,
                          "班福期望": [0.1] * 9, "对数差": [0.0] * 9})
    def 加图(pl):
        for tp in pl:
            if tp.名称 == "班福分析":
                tp.图表 = [{"类型": "折线", "位置": "H2", "标题": "班福定律分析 - 首位数分布",
                            "X轴标题": "首位数", "Y轴标题": "比率",
                            "分类引用": "'班福分析'!B2:B10",
                            "系列": ["'班福分析'!D1:D10", "'班福分析'!E1:E10"]}]
    out = make_excel([("班福分析", stats)], str(tmp_path / "o.xlsx"), postprocess=加图)
    wb = load_workbook(out)
    charts = wb["班福分析"]._charts
    assert len(charts) == 1 and charts[0].tagname == "lineChart"
```

跑确认 FAIL（旧版走 openpyxl LineChart 也能过此断言——需先验证：若旧版通过则该测试不构成 RED，改为断言输出 zip 内存在 `xl/charts/chart1.xml` 且 workbook 无临时部件，以区分实现路径）。
- [ ] **5.2 GREEN**：写入器按 ECMA-376 拼折线图部件：`xl/charts/chart1.xml`（lineChart + ser：tx 引用系列首行、cat 引用分类、val 引用系列）、`xl/drawings/drawing1.xml`（twoCellAnchor H2 起、约 15 行 × 8 列大小）、`xl/drawings/_rels/drawing1.xml.rels`、sheet rels 挂 drawing、[Content_Types] 注册 chart/drawing 部件；多图表命名递增
- [ ] **5.3** writer.py：`_add_benford_chart` 回调改为往"班福分析"表计划写 `图表` 字段（引用列号 col_base 参数保留）；删除 `MAKE_EXCEL_AVAILABLE` 为假时的裸 to_excel 回退分支与 openpyxl.chart import
- [ ] **5.4 VERIFY**：kemu 全套件绿 + kemu 金样对比（图表可读、数值一致）

### 任务 6：汇总验证（阶段 5 输入）

- [ ] 6.1 四项目最终全套测试各跑一次，记录数字
- [ ] 6.2 四金样最终对比，差异清单逐项标注"一致/已排除/可接受"
- [ ] 6.3 性能对比表：基线 vs 新版（50000×12，三次取中位）

### 任务 7：交付文档（阶段 5/6 执行）

- [ ] 7.1 四项目 README 顶部日期式更新说明（2026 年 10 月 21 日段落：输出层改为一次成型写入、速度对比数字、业务与输出内容不变）
- [ ] 7.2 analyzer `docs/adr/0001-excel输出一次成型写入.md`
- [ ] 7.3 `docs/reviews/2026-10-21-excel-fast-writer输出改造-review.md`
- [ ] 7.4 列出四项目变更清单与验证证据 → 用户 CHECKPOINT 4 确认 → 各项目 `git add -A && git commit`（中文信息）→ `git push`（用户已授权）

## Self-Review

- 规格覆盖：设计文档三个维度（单文件重写/计划回调/自拼图表）对应任务 1/1+2/5；skill 复制任务 3；occupancy 变体任务 4；交付任务 7。无缺口。
- 占位符：无 TBD/TODO；测试代码均给出实际内容；金样生成方式在 0.3 给出主备两条路径。
- 类型一致性：表计划属性名统一为 `标签色`、`名称`、`图表`、方法 `apply_overrides/apply_columns/apply_rows/apply_conditions/apply_theme`（与 writer_skeleton 中文参数风格一致，任务 1 定名后 2/5 沿用）。
