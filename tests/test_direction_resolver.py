# -*- coding: utf-8 -*-
"""DirectionResolver 方向判断器测试"""
from src.core.direction_resolver import DirectionResolver


def test_余额借方大于贷方判为借方():
    r = DirectionResolver()
    direction, basis = r.resolve("1122", "应收账款", 1000.0, 200.0, "debit")
    assert direction == "debit"
    assert basis == "balance"


def test_余额贷方大于借方判为贷方():
    r = DirectionResolver()
    direction, basis = r.resolve("2202", "应付账款", 100.0, 800.0, "debit")
    assert direction == "credit"
    assert basis == "balance"


def test_余额相等降级到编码首位():
    r = DirectionResolver()
    direction, basis = r.resolve("1122", "应收账款", 0.0, 0.0, "debit")
    assert direction == "debit"
    assert basis == "code"


def test_编码2开头判为贷方():
    r = DirectionResolver()
    direction, basis = r.resolve("2202", "应付账款", 0.0, 0.0, "debit")
    assert direction == "credit"
    assert basis == "code"


def test_编码非12降级到名称关键词():
    r = DirectionResolver()
    direction, basis = r.resolve("9999", "应收账款", 0.0, 0.0, "debit")
    assert direction == "debit"
    assert basis == "name"


def test_名称含应付判为贷方():
    r = DirectionResolver()
    direction, basis = r.resolve("9999", "应付账款", 0.0, 0.0, "debit")
    assert direction == "credit"
    assert basis == "name"


def test_名称含其他应收长词优先():
    r = DirectionResolver()
    direction, basis = r.resolve("9999", "其他应收款", 0.0, 0.0, "credit")
    assert direction == "debit"
    assert basis == "name"


def test_三维度都失败用默认方向():
    r = DirectionResolver()
    direction, basis = r.resolve("9999", "清算资金", 0.0, 0.0, "debit")
    assert direction == "debit"
    assert basis == "default"


def test_反挂科目余额方向自动识别():
    """预收挂在应收编码下，余额方向能纠正"""
    r = DirectionResolver()
    direction, basis = r.resolve("1122", "应收账款", 100.0, 500.0, "debit")
    assert direction == "credit"
    assert basis == "balance"
