# -*- coding: utf-8 -*-
"""配置页账龄名称与期初日期纯规则测试。"""
from datetime import date

import pytest

import src.gui.step_config as step_config


def _rule(name: str):
    function = getattr(step_config, name, None)
    assert callable(function), f"{name} 接口尚未实现"
    return function


def test_默认账龄名称随上下限更新():
    default_label = _rule("default_bucket_label")
    sync_label = _rule("sync_default_bucket_label")
    assert default_label(0, 90) == "0-90天"
    assert default_label(730, 9999) == "730天以上"
    assert sync_label("0-90天", "0-90天", 0, 120) == ("0-120天", "0-120天")


def test_手动账龄名称在上下限变化后保留():
    sync_label = _rule("sync_default_bucket_label")
    assert sync_label("3个月内", "0-90天", 0, 120) == ("3个月内", "0-120天")


def test_账龄名称为空_重复或数量不符会拒绝():
    validate_labels = _rule("validate_bucket_labels")
    with pytest.raises(ValueError, match="不能为空"):
        validate_labels(["0-90天", ""], 2)
    with pytest.raises(ValueError, match="不能重复"):
        validate_labels(["1年以内", "1年以内"], 2)
    with pytest.raises(ValueError, match="数量"):
        validate_labels(["1年以内"], 2)


def test_无期初日期为空_有期初日期必填且早于截止日():
    parse_opening_date = _rule("parse_opening_date")
    cutoff = date(2026, 12, 31)
    assert parse_opening_date("", cutoff, False) is None
    with pytest.raises(ValueError, match="必须填写"):
        parse_opening_date("", cutoff, True)
    with pytest.raises(ValueError, match="早于"):
        parse_opening_date("2026-12-31", cutoff, True)
    assert parse_opening_date("2025-12-31", cutoff, True) == date(2025, 12, 31)
