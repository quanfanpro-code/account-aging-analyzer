# -*- coding: utf-8 -*-
"""借贷混合计算测试"""
from datetime import date
import pytest
import pandas as pd
from src.core.orchestrator import AgingOrchestrator


def test_借贷混合一次算完():
    """借方科目和贷方科目在同一次计算中分别用对应口径"""
    opening_df = pd.DataFrame({
        "科目编码": ["1122", "2202"],
        "科目名称": ["应收账款", "应付账款"],
        "明细名称": ["客户A", "供应商X"],
        "借方余额": [1000.0, 0.0],
        "贷方余额": [0.0, 800.0],
    })
    journal_df = pd.DataFrame({
        "日期": [date(2024, 6, 1), date(2024, 6, 1)],
        "科目编码": ["1122", "2202"],
        "明细名称": ["客户A", "供应商X"],
        "借方金额": [500.0, 200.0],
        "贷方金额": [0.0, 300.0],
        "摘要": ["销售", "采购"],
    })
    orch = AgingOrchestrator(
        cutoff_date=date(2025, 6, 1),
        buckets=[(0, 365)],
        direction="debit",  # 默认方向
    )
    results = orch.run(opening_df, journal_df)
    assert len(results) == 2
    # 1122 走借方口径
    r0 = next(r for r in results if r.subject_code == "1122")
    assert r0.direction == "debit"
    assert r0.closing_balance == pytest.approx(1500.0)  # 1000+500
    # 2202 走贷方口径
    r1 = next(r for r in results if r.subject_code == "2202")
    assert r1.direction == "credit"
    assert r1.closing_balance == pytest.approx(900.0)  # 800+300-200


def test_反挂科目余额方向自动识别():
    """预收挂在应收编码下，余额方向能纠正为贷方"""
    opening_df = pd.DataFrame({
        "科目编码": ["1122"],
        "科目名称": ["应收账款"],
        "明细名称": ["客户A"],
        "借方余额": [100.0],
        "贷方余额": [500.0],
    })
    journal_df = pd.DataFrame({
        "日期": [date(2024, 6, 1)],
        "科目编码": ["1122"],
        "明细名称": ["客户A"],
        "借方金额": [0.0],
        "贷方金额": [200.0],
        "摘要": ["预收"],
    })
    orch = AgingOrchestrator(
        cutoff_date=date(2025, 6, 1),
        buckets=[(0, 365)],
        direction="debit",
    )
    results = orch.run(opening_df, journal_df)
    assert len(results) == 1
    # 余额方向：贷方500 > 借方100 -> 贷方口径
    assert results[0].direction == "credit"
    # 贷方口径：期初(贷-借=400) + 贷200 - 借0 = 600
    assert results[0].closing_balance == pytest.approx(600.0)
