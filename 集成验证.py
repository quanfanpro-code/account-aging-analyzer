# -*- coding: utf-8 -*-
"""集成验证脚本：端到端测试"""
import pandas as pd
from datetime import date
from pathlib import Path

from src.core.column_mapper import ColumnMapper
from src.core.data_loader import DataLoader
from src.core.orchestrator import AgingOrchestrator
from src.core.report import ReportGenerator

BASE = Path(__file__).parent

print("=" * 60)
print("  往来账款账龄分析 — 集成验证")
print("=" * 60)

# 1. 加载数据
print("\n[1/5] 加载 Excel 数据...")
opening_df = pd.read_excel(BASE / "模拟数据_期初余额.xlsx")
journal_df = pd.read_excel(BASE / "模拟数据_序时账.xlsx")
print(f"  期初余额: {len(opening_df)} 行, {list(opening_df.columns)}")
print(f"  序时账:   {len(journal_df)} 行, {list(journal_df.columns)}")

# 2. 列映射
print("\n[2/5] 自动列映射...")
opening_mapper = ColumnMapper()
opening_mapping = opening_mapper.auto_map(list(opening_df.columns), field_type="balance")
print(f"  期初映射: {opening_mapping}")
journal_mapper = ColumnMapper()
journal_mapping = journal_mapper.auto_map(list(journal_df.columns), field_type="journal")
print(f"  序时账映射: {journal_mapping}")

# 验证必填
opening_mapper.validate_required(["科目编码", "明细名称", "借方余额", "贷方余额"])
journal_mapper.validate_required(["日期", "科目编码", "明细名称", "借方金额", "贷方金额"])
print("  必填字段校验: 通过")

# 3. 清洗转换
print("\n[3/5] 数据清洗与类型转换...")
loader = DataLoader()
opening_df = loader.apply_mapping(opening_df, opening_mapping)
opening_df = loader.clean(opening_df, key_column="科目编码")
opening_df, _ = loader.convert_types(opening_df, amount_columns=["借方余额", "贷方余额"])
print(f"  期初清洗后: {len(opening_df)} 行")

journal_df = loader.apply_mapping(journal_df, journal_mapping)
journal_df = loader.clean(journal_df, key_column="科目编码")
journal_df, _ = loader.convert_types(
    journal_df,
    amount_columns=["借方金额", "贷方金额"],
    date_columns=["日期"],
)
print(f"  序时账清洗后: {len(journal_df)} 行")

# 4. FIFO 计算
print("\n[4/5] FIFO 账龄计算...")
cutoff = date(2025, 6, 1)
buckets = [(0, 90), (90, 180), (180, 365), (365, 730), (730, 9999)]

progress = []
def on_progress(current, total):
    progress.append((current, total))

# 借方方向（应收）
orch_debit = AgingOrchestrator(
    cutoff_date=cutoff, buckets=buckets, direction="debit",
    on_progress=on_progress,
)
# 只取借方的科目
opening_debit = opening_df[opening_df["借方余额"] > 0].copy()
results_debit = orch_debit.run(opening_debit, journal_df)
print(f"  借方方向: {len(results_debit)} 个明细")

for r in results_debit:
    print(f"    {r.detail_name}: 期初{r.opening_balance:,.0f} "
          f"→ 期末{r.closing_balance:,.0f} "
          f"分档={[f'{v:,.0f}' for v in r.bucket_totals]} "
          f"total_check={r.total_check:,.0f}")

# 贷方方向（应付）
orch_credit = AgingOrchestrator(
    cutoff_date=cutoff, buckets=buckets, direction="credit",
)
opening_credit = opening_df[opening_df["贷方余额"] > 0].copy()
results_credit = orch_credit.run(opening_credit, journal_df)
print(f"  贷方方向: {len(results_credit)} 个明细")

for r in results_credit:
    print(f"    {r.detail_name}: 期初{r.opening_balance:,.0f} "
          f"→ 期末{r.closing_balance:,.0f} "
          f"分档={[f'{v:,.0f}' for v in r.bucket_totals]} "
          f"total_check={r.total_check:,.0f}")

all_results = results_debit + results_credit

# 5. 导出报告
print("\n[5/5] 导出审计底稿...")
output_path = BASE / "集成验证_审计底稿.xlsx"
gen = ReportGenerator()
gen.generate(
    output_path=output_path,
    aging_results=all_results,
    config={"cutoff_date": cutoff, "buckets": buckets, "direction": "debit/credit"},
)
print(f"  已导出: {output_path}")

# 验证
print("\n" + "=" * 60)
print("  验证结果")
print("=" * 60)

# 验证期末余额（分方向核对：应收看借方口径，应付看贷方口径；
# 反方向下的同一明细余额口径不同，不参与校验）
print("\n--- 期末余额验证 ---")
expected_debit = {
    "客户A公司": 150000.0,
    "客户B集团": 170000.0,
    "客户C科技": 65000.0,
}
expected_credit = {
    "供应商X": 130000.0,
    "供应商Y": 160000.0,
}
all_pass = True
for direction_results, expected in ((results_debit, expected_debit), (results_credit, expected_credit)):
    for r in direction_results:
        exp = expected.get(r.detail_name)
        if exp is not None:
            ok = abs(r.closing_balance - exp) < 0.01
            status = "PASS" if ok else "FAIL"
            if not ok:
                all_pass = False
            print(f"  {status}: {r.detail_name} 期末={r.closing_balance:,.2f} (期望={exp:,.2f})")

# 验证平衡
print("\n--- 平衡校验 ---")
for r in all_results:
    ok = abs(r.total_check - r.closing_balance) < 0.01
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_pass = False
    print(f"  {status}: {r.detail_name} total_check={r.total_check:,.2f} vs closing={r.closing_balance:,.2f}")

# 验证 Excel Sheet
print("\n--- Excel 验证 ---")
import openpyxl
wb = openpyxl.load_workbook(output_path)
for name in ["借方账龄汇总表", "贷方账龄汇总表", "逐笔追溯明细", "期初余额验证", "期末余额验证", "参数说明"]:
    ok = name in wb.sheetnames
    status = "PASS" if ok else "FAIL"
    if not ok:
        all_pass = False
    print(f"  {status}: Sheet '{name}'")

print("\n" + "=" * 60)
if all_pass:
    print("  [SUCCESS] 全部集成验证通过！")
else:
    print("  [FAILED] 部分验证未通过，请检查")
print("=" * 60)
