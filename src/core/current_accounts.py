# -*- coding: utf-8 -*-
"""八类往来科目的统一识别、过滤、统计和冲突检查。"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re

import pandas as pd


CATEGORY_COLUMN = "_往来类别"
DIRECTION_COLUMN = "_正常方向"
SOURCE_COLUMN = "_来源工作表"
ORIGINAL_NAME_COLUMN = "_原科目名称"

ACCOUNT_RULES = (
    ("应收账款", "1122", "debit"),
    ("预付账款", "1123", "debit"),
    ("其他应收款", "1221", "debit"),
    ("合同资产", "1486", "debit"),
    ("应付账款", "2202", "credit"),
    ("预收账款", "2203", "credit"),
    ("其他应付款", "2241", "credit"),
    ("合同负债", "2204", "credit"),
)
CATEGORIES = tuple(rule[0] for rule in ACCOUNT_RULES)
EXCLUDED_TERMS = ("坏账准备", "减值准备")
BLANK_DETAIL = "（未填明细）"


@dataclass(frozen=True)
class CurrentAccountMatch:
    status: str
    category: str | None
    direction: str | None
    basis: str
    display_name: str
    ignored_reason: str = ""
    warning: str = ""


@dataclass
class CurrentAccountFilterResult:
    dataframe: pd.DataFrame
    source_label: str
    original_rows: int
    retained_rows: int
    ignored_rows: int
    ignored_counts: dict[str, int]
    category_counts: dict[str, int]
    recognition_counts: dict[str, int]
    blank_detail_rows: int
    blank_detail_amounts: dict[str, float]
    warning_count: int
    warnings: list[str]


@dataclass(frozen=True)
class CategoryConflict:
    subject_code: str
    categories: tuple[str, ...]
    evidence: tuple[tuple[str, str, str], ...]


def _is_blank(value: object) -> bool:
    return value is None or bool(pd.isna(value)) or not str(value).strip()


def _text(value: object) -> str:
    return "" if _is_blank(value) else str(value).strip()


def _subject_code(value: object) -> str:
    return re.sub(r"^(\d+)\.0+$", r"\1", _text(value))


def _amount(value: object) -> float:
    number = pd.to_numeric(value, errors="coerce")
    return 0.0 if pd.isna(number) else float(number)


def classify_current_account(subject_code: object, subject_name: object) -> CurrentAccountMatch:
    """按名称优先、编码辅助的顺序识别一行科目。"""
    code = _subject_code(subject_code)
    name = _text(subject_name)

    if any(term in name for term in EXCLUDED_TERMS):
        return CurrentAccountMatch("ignored", None, None, "none", name, "坏账或减值准备")

    name_rule = next((rule for rule in ACCOUNT_RULES if rule[0] in name), None)
    code_rule = next((rule for rule in ACCOUNT_RULES if code.startswith(rule[1])), None)
    if name_rule:
        category, _prefix, direction = name_rule
        warning = ""
        if code_rule and code_rule[0] != category:
            warning = f"科目名称识别为{category}，编码 {code} 通常对应{code_rule[0]}，已按名称分类"
        return CurrentAccountMatch("retained", category, direction, "name", name, warning=warning)
    if code_rule:
        category, _prefix, direction = code_rule
        return CurrentAccountMatch(
            "retained", category, direction, "code", name or category,
        )
    reason = "识别关键字段均为空" if not code and not name else "非八类往来"
    return CurrentAccountMatch("ignored", None, None, "none", name, reason)


def filter_current_accounts(
    df: pd.DataFrame,
    *,
    data_kind: str,
    source_label: str,
) -> CurrentAccountFilterResult:
    """过滤整表并返回可复核统计；不修改传入的原始数据。"""
    if data_kind not in {"opening", "journal"}:
        raise ValueError("data_kind 只能是 opening 或 journal")

    amount_columns = (
        ("借方余额", "贷方余额") if data_kind == "opening" else ("借方金额", "贷方金额")
    )
    ignored = Counter()
    categories = Counter()
    recognition = Counter()
    blank_detail_rows = 0
    blank_amounts = {column: 0.0 for column in amount_columns}
    warnings: list[str] = []
    retained: list[dict] = []

    for row_number, (_, row) in enumerate(df.iterrows(), start=2):
        original_name = _text(row.get("科目名称"))
        match = classify_current_account(row.get("科目编码"), original_name)
        if match.status == "ignored":
            ignored[match.ignored_reason] += 1
            continue

        item = row.to_dict()
        item["科目编码"] = _subject_code(row.get("科目编码"))
        item["科目名称"] = match.display_name
        item[ORIGINAL_NAME_COLUMN] = original_name
        detail_is_blank = _is_blank(row.get("明细名称"))
        item["明细名称"] = BLANK_DETAIL if detail_is_blank else _text(row.get("明细名称"))
        item[CATEGORY_COLUMN] = match.category
        item[DIRECTION_COLUMN] = match.direction
        item[SOURCE_COLUMN] = source_label
        retained.append(item)
        categories[match.category] += 1
        recognition["按名称识别" if match.basis == "name" else "按编码辅助识别"] += 1
        if detail_is_blank:
            blank_detail_rows += 1
            for column in amount_columns:
                blank_amounts[column] += _amount(row.get(column))
        if match.warning:
            warnings.append(f"{source_label} 第 {row_number} 行：{match.warning}")

    added_columns = [
        "科目编码", "科目名称", "明细名称",
        ORIGINAL_NAME_COLUMN, CATEGORY_COLUMN, DIRECTION_COLUMN, SOURCE_COLUMN,
    ]
    output_columns = list(df.columns) + [column for column in added_columns if column not in df.columns]
    output = pd.DataFrame(retained, columns=output_columns)
    retained_rows = len(retained)
    original_rows = len(df)
    ignored_rows = original_rows - retained_rows
    return CurrentAccountFilterResult(
        dataframe=output,
        source_label=source_label,
        original_rows=original_rows,
        retained_rows=retained_rows,
        ignored_rows=ignored_rows,
        ignored_counts=dict(ignored),
        category_counts={category: categories[category] for category in CATEGORIES},
        recognition_counts={
            "按名称识别": recognition["按名称识别"],
            "按编码辅助识别": recognition["按编码辅助识别"],
        },
        blank_detail_rows=blank_detail_rows,
        blank_detail_amounts=blank_amounts,
        warning_count=len(warnings),
        warnings=warnings,
    )


def find_category_conflicts(
    results: list[CurrentAccountFilterResult],
) -> list[CategoryConflict]:
    """找出同一非空科目编码对应多个标准类别的情况。"""
    grouped: dict[str, list[tuple[str, str, str]]] = {}
    for result in results:
        for _, row in result.dataframe.iterrows():
            code = _subject_code(row.get("科目编码"))
            if not code:
                continue
            evidence = (
                _text(row.get(CATEGORY_COLUMN)),
                _text(row.get(ORIGINAL_NAME_COLUMN)),
                _text(row.get(SOURCE_COLUMN)) or result.source_label,
            )
            if evidence not in grouped.setdefault(code, []):
                grouped[code].append(evidence)

    conflicts = []
    for code, evidence in grouped.items():
        categories = tuple(sorted({item[0] for item in evidence}))
        if len(categories) > 1:
            conflicts.append(CategoryConflict(code, categories, tuple(evidence)))
    return sorted(conflicts, key=lambda conflict: conflict.subject_code)


def format_category_conflicts(conflicts: list[CategoryConflict]) -> str:
    """把阻断性分类冲突整理成可定位的中文提示。"""
    lines = ["同一科目编码被识别为多个往来类别，请核对列映射、工作表或源数据："]
    for conflict in conflicts:
        lines.append(f"科目编码 {conflict.subject_code}：{', '.join(conflict.categories)}")
        for category, original_name, source in conflict.evidence:
            lines.append(f"  - {source}｜{original_name or '(科目名称为空)'}｜{category}")
    return "\n".join(lines)
