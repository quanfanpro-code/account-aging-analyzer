# -*- coding: utf-8 -*-
"""导入页纯状态和筛选摘要测试。"""
from datetime import date

import pandas as pd

import src.gui.step_import as step_import
from src.core.current_accounts import filter_current_accounts


def _function(name: str):
    function = getattr(step_import, name, None)
    assert callable(function), f"{name} 接口尚未实现"
    return function


def test_清除期初会清空所有关联状态():
    clear_source_state = _function("clear_source_state")
    state = {
        "opening_path": "a.xlsx", "opening_sheet_names": ["A", "B"],
        "opening_sheet": "B", "opening_df": object(),
        "opening_mapping": {"科目编码": "科目"},
        "opening_filter_summary": "旧摘要",
        "opening_aging_columns": {(0, 90): "0-90天"},
        "opening_has_aging": True, "opening_date": date(2025, 1, 1),
    }
    clear_source_state(state, "opening")
    assert state["opening_path"] is None
    assert state["opening_sheet_names"] == []
    assert state["opening_sheet"] is None
    assert state["opening_df"] is None
    assert state["opening_mapping"] == {}
    assert state["opening_filter_summary"] == ""
    assert state["opening_aging_columns"] == {}
    assert state["opening_has_aging"] is False
    assert state["opening_date"] is None


def test_切换工作表只清空旧载荷并保留文件信息():
    reset_source_payload = _function("reset_source_payload")
    opening_date = date(2025, 1, 1)
    state = {
        "opening_path": "a.xlsx", "opening_sheet_names": ["A", "B"],
        "opening_sheet": "A", "opening_df": object(),
        "opening_mapping": {"科目编码": "科目"},
        "opening_filter_summary": "旧摘要",
        "opening_aging_columns": {(0, 90): "0-90天"},
        "opening_has_aging": True, "opening_date": opening_date,
    }
    reset_source_payload(state, "opening")
    assert state["opening_path"] == "a.xlsx"
    assert state["opening_sheet_names"] == ["A", "B"]
    assert state["opening_date"] == opening_date
    assert state["opening_sheet"] is None
    assert state["opening_df"] is None
    assert state["opening_mapping"] == {}
    assert state["opening_filter_summary"] == ""
    assert state["opening_aging_columns"] == {}
    assert state["opening_has_aging"] is False


def test_旧读取请求不能覆盖新选择():
    next_request = _function("next_source_request")
    is_current = _function("is_current_source_request")
    state = {"journal_request_id": 0}
    first = next_request(state, "journal")
    second = next_request(state, "journal")
    assert first == 1
    assert second == 2
    assert is_current(state, "journal", first) is False
    assert is_current(state, "journal", second) is True


def test_筛选摘要包含勾稽数量_八类分项和警告():
    format_summary = _function("format_filter_summary")
    df = pd.DataFrame({
        "科目编码": ["1122", "2204", "6602", "1122"],
        "科目名称": ["应收账款", "合同负债", "管理费用", "应付账款"],
        "明细名称": [None, "客户B", "部门", "供应商C"],
        "借方金额": [100.0, 0.0, 50.0, 0.0],
        "贷方金额": [0.0, 80.0, 0.0, 20.0],
    })
    result = filter_current_accounts(df, data_kind="journal", source_label="序时账/明细")
    text = format_summary(result)
    assert "原始 4 行" in text
    assert "保留 3 行" in text
    assert "忽略 1 行" in text
    assert "非八类往来 1 行" in text
    assert "应收账款 1 行" in text
    assert "预付账款 0 行" in text
    assert "名称与编码冲突 1 行" in text
    assert "未填明细 1 行" in text
