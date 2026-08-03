# -*- coding: utf-8 -*-
import pytest
from src.core.column_mapper import ColumnMapper


# ============ 智能匹配：长词优先 ============
def test_智能匹配_借方余额优先于借方():
    """列名含'借方余额'应被识别为借方余额，不是借方金额"""
    columns = ["借方余额", "借方金额"]
    mapper = ColumnMapper()
    result = mapper.auto_map(columns, field_type="balance")
    assert result["借方余额"] == "借方余额"


def test_智能匹配_不会把贷方误识别为借方():
    """列名含'贷方'不应被识别为借方字段"""
    columns = ["贷方金额", "贷方余额"]
    mapper = ColumnMapper()
    result = mapper.auto_map(columns, field_type="balance")
    assert result["借方余额"] is None
    assert result["贷方余额"] == "贷方余额"


# ============ 序时账匹配 ============
def test_智能匹配_日期列():
    columns = ["记账日期", "摘要", "借方金额"]
    mapper = ColumnMapper()
    result = mapper.auto_map(columns, field_type="journal")
    assert result["日期"] == "记账日期"


def test_智能匹配_无匹配返回None():
    columns = ["A", "B", "C"]
    mapper = ColumnMapper()
    result = mapper.auto_map(columns, field_type="journal")
    assert result["日期"] is None


# ============ 手动覆盖 ============
def test_手动覆盖映射():
    mapper = ColumnMapper()
    mapper.auto_map(["记账日期", "摘要"], field_type="journal")
    mapper.set_mapping("日期", "摘要")
    assert mapper.get_mapping()["日期"] == "摘要"


# ============ 余额表字段 ============
def test_余额表匹配_客户字段():
    columns = ["科目编码", "科目名称", "客户名称", "借方余额", "贷方余额"]
    mapper = ColumnMapper()
    result = mapper.auto_map(columns, field_type="balance")
    assert result["科目编码"] == "科目编码"
    assert result["明细名称"] == "客户名称"


# ============ 必填校验 ============
def test_校验必填字段_缺失抛错():
    """必填字段未映射时应抛 ValueError"""
    mapper = ColumnMapper()
    mapper.auto_map(["A", "B"], field_type="journal")
    with pytest.raises(ValueError, match="必填"):
        mapper.validate_required(["日期", "借方金额"])


# ============ 同列冲突排除 ============
def test_智能匹配_同一列不被多字段重复占用():
    """当 Excel 只有一列'科目'时，不应同时映射到科目编码和科目名称"""
    columns = ["科目", "日期", "摘要"]
    mapper = ColumnMapper()
    result = mapper.auto_map(columns, field_type="journal")
    # "科目"应被优先匹配到"科目编码"（字段遍历顺序先于"科目名称"）
    assert result["科目编码"] == "科目"
    # "科目名称"不应也匹配到"科目"，应为 None
    assert result["科目名称"] is None


# ============ 期初账龄分档列检测 ============
def test_检测期初分档列_标准格式():
    """应识别 '0-90天'、'90-180天' 等标准格式列"""
    columns = ["科目编码", "科目名称", "明细名称",
               "0-90天", "90-180天", "180-365天", "365-730天", "730天以上"]
    mapper = ColumnMapper()
    result = mapper.detect_aging_columns(columns)
    assert len(result) == 5
    assert result[0] == ((0, 90), "0-90天")
    assert result[1] == ((90, 180), "90-180天")
    assert result[4] == ((730, 9999), "730天以上")


def test_检测期初分档列_中文年格式():
    """应识别 '1年以内'、'1-2年'、'2-3年'、'3年以上' 格式"""
    columns = ["科目编码", "1年以内", "1-2年", "2-3年", "3年以上"]
    mapper = ColumnMapper()
    result = mapper.detect_aging_columns(columns)
    assert len(result) == 4
    assert result[0] == ((0, 365), "1年以内")
    assert result[1] == ((365, 730), "1-2年")
    assert result[3] == ((1095, 9999), "3年以上")


def test_检测期初分档列_无分档列返回空():
    """没有分档列时返回空列表"""
    columns = ["科目编码", "科目名称", "借方余额", "贷方余额"]
    mapper = ColumnMapper()
    result = mapper.detect_aging_columns(columns)
    assert result == []


def test_智能匹配_借方余额不匹配期末列():
    """列名含"期末"的列不应被匹配为期初余额表的借方/贷方余额"""
    columns = ["期末借方余额", "借方余额", "期末贷方余额", "贷方余额"]
    mapper = ColumnMapper()
    result = mapper.auto_map(columns, field_type="balance")
    assert result["借方余额"] == "借方余额"
    assert result["贷方余额"] == "贷方余额"


def test_智能匹配_科目编码不抢科目名称列():
    """兜底关键词"科目"不应命中"科目名称"列"""
    columns = ["科目名称", "记账日期", "客户名称", "借方金额", "贷方金额"]
    mapper = ColumnMapper()
    result = mapper.auto_map(columns, field_type="journal")
    assert result["科目编码"] is None
    assert result["科目名称"] == "科目名称"
