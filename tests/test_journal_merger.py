# -*- coding: utf-8 -*-
"""多文件合并测试"""
import pandas as pd
from datetime import date
import pytest
from src.core.journal_merger import merge_journal_files


def test_多文件合并_列名一致():
    dfs = [
        pd.DataFrame({"日期": [date(2024,1,1)], "科目编码": ["1122"],
                      "明细名称": ["客户A"], "借方金额": [100.0],
                      "贷方金额": [0.0], "摘要": ["销售"]}),
        pd.DataFrame({"日期": [date(2025,1,1)], "科目编码": ["1122"],
                      "明细名称": ["客户A"], "借方金额": [200.0],
                      "贷方金额": [0.0], "摘要": ["销售"]}),
    ]
    merged = merge_journal_files(dfs)
    assert len(merged) == 2
    assert "日期" in merged.columns
    assert "科目编码" in merged.columns
    assert "明细名称" in merged.columns
    assert "借方金额" in merged.columns
    assert "贷方金额" in merged.columns


def test_多文件合并_列名不一致但能匹配():
    """一个文件用'借方金额'，另一个用'借方发生额'"""
    dfs = [
        pd.DataFrame({"日期": [date(2024,1,1)], "科目编码": ["1122"],
                      "明细名称": ["客户A"], "借方金额": [100.0],
                      "贷方金额": [0.0], "摘要": ["销售"]}),
        pd.DataFrame({"记账日期": [date(2025,1,1)], "科目编码": ["1122"],
                      "客户名称": ["客户A"], "借方发生额": [200.0],
                      "贷方发生额": [0.0], "摘要": ["销售"]}),
    ]
    merged = merge_journal_files(dfs)
    assert len(merged) == 2
    assert "日期" in merged.columns
    assert "明细名称" in merged.columns
    assert "借方金额" in merged.columns


def test_多文件合并_必要字段缺失报错():
    dfs = [
        pd.DataFrame({"日期": [date(2024,1,1)], "科目编码": ["1122"],
                      "明细名称": ["客户A"], "借方金额": [100.0],
                      "贷方金额": [0.0], "摘要": ["销售"]}),
        pd.DataFrame({"日期": [date(2025,1,1)], "科目编码": ["1122"],
                      "明细名称": ["客户A"], "借方金额": [200.0],
                      "摘要": ["销售"]}),  # 缺贷方金额
    ]
    with pytest.raises(ValueError) as exc:
        merge_journal_files(dfs)
    assert "贷方金额" in str(exc.value)


def test_多文件合并_完全重复记录写警告():
    """多文件重复导入同一凭证：不去重，但要提示可能重复的记录数"""
    df1 = pd.DataFrame({"日期": [date(2024,1,1)], "科目编码": ["1122"],
                        "明细名称": ["客户A"], "借方金额": [100.0],
                        "贷方金额": [0.0], "摘要": ["销售"]})
    df2 = df1.copy()  # 同一凭证出现在第二个文件
    warnings = []
    merged = merge_journal_files([df1, df2], warnings_out=warnings)
    assert len(merged) == 2  # 不做自动去重
    assert len(warnings) == 1
    assert "重复" in warnings[0] and "1" in warnings[0]
