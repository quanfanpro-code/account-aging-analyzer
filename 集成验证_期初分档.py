# -*- coding: utf-8 -*-
"""集成验证：期初分档模式 — 端到端测试"""
import pandas as pd
from datetime import date
from pathlib import Path

from src.core.column_mapper import ColumnMapper
from src.core.data_loader import DataLoader
from src.core.orchestrator import AgingOrchestrator
from src.core.report import ReportGenerator

BASE = Path(__file__).parent

print("=" * 60)
print("  期初分档模式 — 集成验证")
print("=" * 60)

# ====== 1. 构造含期初分档的模拟数据 ======
print("\n[1/5] 构造期初分档数据...")

# 期初余额 — 含分档列
opening_data = {
    "科目编码": ["1122", "1122"],
    "科目名称": ["应收账款", "应收账款"],
    "客户名称": ["客户A", "客户B"],
    "借方余额": [100000.0, 200000.0],
    "贷方余额": [0.0, 0.0],
    "0-90天": [20000.0, 50000.0],
    "90-180天": [30000.0, 50000.0],
    "180-365天": [50000.0, 100000.0],
}
opening_df = pd.DataFrame(opening_data)

# 序时账 — 本期发生
journal_data = {
    "记账日期": [
        date(2024, 7, 1), date(2024, 10, 1), date(2025, 1, 15), date(2025, 3, 20),
        date(2024, 8, 1), date(2024, 12, 1), date(2025, 2, 10),
    ],
    "科目编码": [
        "1122", "1122", "1122", "1122",
        "1122", "1122", "1122",
    ],
    "客户名称": [
        "客户A", "客户A", "客户A", "客户A",
        "客户B", "客户B", "客户B",
    ],
    "借方金额": [
        40000.0, 0.0, 30000.0, 0.0,
        0.0, 20000.0, 40000.0,
    ],
    "贷方金额": [
        0.0, 20000.0, 0.0, 15000.0,
        10000.0, 0.0, 0.0,
    ],
    "摘要": [
        "销售", "回款", "销售", "回款",
        "回款", "销售", "销售",
    ],
}
journal_df = pd.DataFrame(journal_data)

# 存储
opening_path = BASE / "集成验证_期初分档_期初.xlsx"
journal_path = BASE / "集成验证_期初分档_序时账.xlsx"
opening_df.to_excel(opening_path, index=False)
journal_df.to_excel(journal_path, index=False)

print(f"  期初生成: {opening_path}")
print(f"  序时账生成: {journal_path}")

# ====== 2. 列映射 + 检测期初分档列 ======
print("\n[2/5] 列映射 + 期初分档检测...")

opening_mapper = ColumnMapper()
opening_mapping = opening_mapper.auto_map(list(opening_df.columns), field_type="balance")
print(f"  期初映射: {opening_mapping}")

# 检测分档列
aging_cols = opening_mapper.detect_aging_columns(list(opening_df.columns))
print(f"  检测到期初分档列: {aging_cols}")

journal_mapper = ColumnMapper()
journal_mapping = journal_mapper.auto_map(list(journal_df.columns), field_type="journal")

# ====== 3. 数据清洗 ======
print("\n[3/5] 数据清洗...")
loader = DataLoader()
opening_df = loader.apply_mapping(opening_df, opening_mapping)
opening_df = loader.clean(opening_df, "科目编码")
opening_df, _ = loader.convert_types(opening_df, amount_columns=["借方余额", "贷方余额"])

journal_df = loader.apply_mapping(journal_df, journal_mapping)
journal_df = loader.clean(journal_df, "科目编码")
journal_df, _ = loader.convert_types(journal_df, amount_columns=["借方金额", "贷方金额"], date_columns=["日期"])

# ====== 4. 计算 ======
print("\n[4/5] FIFO 计算（含期初分档）...")
cutoff = date(2025, 6, 1)
opening_date = date(2024, 1, 1)
buckets = [(0, 90), (90, 180), (180, 365), (365, 730)]

orch = AgingOrchestrator(
    cutoff_date=cutoff, buckets=buckets, direction="debit",
    opening_date=opening_date,
    opening_aging_columns={k: v for k, v in aging_cols},
)
results = orch.run(opening_df, journal_df)

print(f"  结果: {len(results)} 个明细")
for r in results:
    shift = (cutoff - opening_date).days
    print(f"\n  {r.detail_name}:")
    print(f"    期初总额: {r.opening_balance:,.0f}")
    print(f"    期初分档(偏移前): {r.opening_bucket_totals}")
    print(f"    本期借/贷: {r.total_debit:,.0f} / {r.total_credit:,.0f}")
    print(f"    期末余额: {r.closing_balance:,.0f}")
    print(f"    期末分档: {[f'{v:,.0f}' for v in r.bucket_totals]}")
    print(f"    total_check: {r.total_check:,.0f} {'OK' if abs(r.total_check - r.closing_balance) < 0.01 else 'FAIL'}")

# ====== 5. 导出 ======
print("\n[5/5] 导出...")
output = BASE / "集成验证_期初分档_审计底稿.xlsx"
ReportGenerator().generate(
    output_path=output, aging_results=results,
    config={"cutoff_date": cutoff, "buckets": buckets, "direction": "debit"},
)
print(f"  已导出: {output}")

# ====== 验证 ======
print("\n" + "=" * 60)
print("  验证")
print("=" * 60)

# 客户A: 期初100000(分档:20000/30000/50000) + 借(40000+30000) - 贷(20000+15000) = 135000
# 客户B: 期初200000(分档:50000/50000/100000) + 借(20000+40000) - 贷10000 = 250000
expected = {"客户A": 135000.0, "客户B": 250000.0}
all_pass = True
for r in results:
    exp = expected.get(r.detail_name.split("客户")[-1] if "客户" in r.detail_name else r.detail_name, None)
    # 用明细名匹配
    for k, v in expected.items():
        if k in r.detail_name:
            ok = abs(r.closing_balance - v) < 0.01
            status = "PASS" if ok else "FAIL"
            if not ok: all_pass = False
            print(f"  {status}: {r.detail_name} 期末={r.closing_balance:,.0f} (期望={v:,.0f})")
            break

# 平衡校验
print("\n  平衡校验:")
for r in results:
    ok = abs(r.total_check - r.closing_balance) < 0.01
    status = "PASS" if ok else "FAIL"
    if not ok: all_pass = False
    print(f"  {status}: {r.detail_name} total_check={r.total_check:,.0f}")

# 期初分档验证
print("\n  期初分档结构:")
for r in results:
    has_opening = len(r.opening_bucket_totals) > 0
    status = "PASS" if has_opening else "FAIL"
    if not has_opening: all_pass = False
    print(f"  {status}: {r.detail_name} opening_buckets={r.opening_bucket_totals}")
    print(f"        opening_date={r.opening_date}")

print("\n" + "=" * 60)
if all_pass:
    print("  [SUCCESS] 期初分档模式集成验证全部通过！")
else:
    print("  [FAILED] 请检查")
print("=" * 60)
