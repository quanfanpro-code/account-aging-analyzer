# -*- coding: utf-8 -*-
"""方向判断器 - 三维度综合判断科目借贷方向"""
from __future__ import annotations


class DirectionResolver:
    """按优先级判断科目方向：余额 > 编码首位 > 名称关键词 > 默认"""

    # 长词在前，确保"其他应收"优先于"应收"匹配
    DEBIT_KEYWORDS = [
        "其他应收", "应收账款", "应收", "预付账款", "预付",
        "待摊费用", "长期待摊", "待摊",
    ]
    CREDIT_KEYWORDS = [
        "其他应付", "应付账款", "应付", "预收账款", "预收",
        "预提费用", "预提",
    ]

    def resolve(
        self,
        subject_code: str,
        subject_name: str,
        opening_debit_total: float,
        opening_credit_total: float,
        default_direction: str,
    ) -> tuple[str, str]:
        """返回 (direction, basis)，basis 为判断依据"""

        # 第一优先：期初余额方向
        if opening_debit_total > opening_credit_total:
            return "debit", "balance"
        if opening_credit_total > opening_debit_total:
            return "credit", "balance"

        # 第二优先：科目编码首位
        code = str(subject_code).strip()
        if code:
            first = code[0]
            if first == "1":
                return "debit", "code"
            if first == "2":
                return "credit", "code"

        # 第三优先：科目名称关键词（长词优先）
        name = str(subject_name or "")
        for keyword in self.DEBIT_KEYWORDS:
            if keyword in name:
                return "debit", "name"
        for keyword in self.CREDIT_KEYWORDS:
            if keyword in name:
                return "credit", "name"

        # 兜底：默认方向
        return default_direction, "default"
