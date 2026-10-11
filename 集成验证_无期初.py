# -*- coding: utf-8 -*-
"""集成验证：无期初余额，只用序时账 — 端到端测试"""
import pandas as pd
from datetime import date
from pathlib import Path

from src.core.workflow import AgingWorkflow
from src.core.report import ReportGenerator

BASE = Path(__file__).parent

print("=" * 60)
print("  无期初余额场景 — 集成验证")
print("=" * 60)

opening_df = pd.DataFrame(columns=["科目编码", "科目名称", "明细名称", "借方余额", "贷方余额"])
journal_df = pd.DataFrame({
    "日期": [date(2024, 1, 1), date(2024, 10, 1), date(2024, 11, 1), date(2025, 2, 1)],
    "科目编码": ["1122", "1122", "1122", "1122"],
    "科目名称": ["应收账款", "应收账款", "应收账款", "应收账款"],
    "明细名称": ["客户A", "客户A", "客户A", "客户A"],
    "借方金额": [1000.0, 500.0, 0.0, 300.0],
    "贷方金额": [0.0, 0.0, 600.0, 0.0],
    "摘要": ["销售", "销售", "回款", "销售"],
})

cutoff = date(2025, 6, 1)
buckets = [(0, 365), (365, 9999)]

orch = AgingWorkflow(cutoff_date=cutoff, buckets=buckets)
results = orch.run(opening_df, journal_df)

assert len(results) == 1, f"明细数应为 1，实际 {len(results)}"
r = results[0]
assert r.opening_balance == 0.0, "期初余额应为 0"
assert abs(r.closing_balance - 1200.0) < 0.01, f"期末应为 1200，实际 {r.closing_balance}"
assert abs(r.total_check - r.closing_balance) < 0.01, "勾稽不平衡"
print(f"  期末余额: {r.closing_balance:,.0f}（期望 1200）")
print(f"  期末分档: {r.bucket_totals}")

output = BASE / "集成验证_无期初_审计底稿.xlsx"
ReportGenerator().generate(
    output_path=output, aging_results=results,
    config={"cutoff_date": cutoff, "buckets": buckets, "direction": "debit"},
)
print(f"  已导出: {output}")
print("  [SUCCESS] 无期初场景集成验证全部通过！")
