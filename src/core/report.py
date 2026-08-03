# -*- coding: utf-8 -*-
"""审计底稿生成 — 调用 make_excel(theme='deep-navy') 摩根系标准格式"""
from __future__ import annotations
import logging
import sys
from pathlib import Path
from typing import Union

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from src.core.models import AgingResult

try:
    from make_excel import make_excel
    MAKE_EXCEL_AVAILABLE = True
except ImportError:
    # 从非项目根目录运行时，按本文件位置推算项目根再试一次（src/core/report.py → 上两级）
    _root = str(Path(__file__).resolve().parents[2])
    if _root not in sys.path:
        sys.path.insert(0, _root)
    try:
        from make_excel import make_excel
        MAKE_EXCEL_AVAILABLE = True
    except ImportError:
        MAKE_EXCEL_AVAILABLE = False
        logging.getLogger(__name__).warning(
            "未找到 make_excel 模块，审计底稿将回退为无样式的裸 to_excel 输出"
        )

PathLike = Union[str, Path]


class ReportGenerator:
    """生成 6-Sheet 审计底稿 Excel（deep-navy 摩根系标准）"""

    def generate(
        self,
        output_path: PathLike,
        aging_results: list[AgingResult],
        config: dict,
    ) -> None:
        # 按方向分两组
        debit_results = [r for r in aging_results if r.direction == "debit"]
        credit_results = [r for r in aging_results if r.direction == "credit"]

        # ── 构建 6 个 Sheet 的 DataFrame ──
        sheets = [
            ('借方账龄汇总表', self._build_summary(debit_results, config)),
            ('贷方账龄汇总表', self._build_summary(credit_results, config)),
            ('逐笔追溯明细', self._build_entries(aging_results, config)),
            ('期初余额验证', self._build_opening_check(aging_results)),
            ('期末余额验证', self._build_closing_check(aging_results)),
            ('参数说明', self._build_config(config)),
        ]

        if MAKE_EXCEL_AVAILABLE:
            make_excel(sheets, output_path, theme='deep-navy')
            # 补写两个账龄汇总表的合计行 SUM 公式
            self._patch_summary_formulas(output_path, debit_results, config, '借方账龄汇总表')
            self._patch_summary_formulas(output_path, credit_results, config, '贷方账龄汇总表')
        else:
            # 回退：无 make_excel 时用裸 to_excel
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                for name, sheet_df in sheets:
                    sheet_df.to_excel(writer, sheet_name=name, index=False)

    # ─── 账龄汇总表 ───────────────────────────────────────────
    def _build_summary(self, results: list[AgingResult], config: dict) -> pd.DataFrame:
        labels = self._get_bucket_labels(config)
        has_neg = any(abs(r.negative_balance) > 0.005 for r in results)

        headers = ["科目编码", "科目名称", "明细名称"]
        for label in labels:
            headers.append(label)
        if has_neg:
            headers.append("负余额")
        headers.append("合计")

        rows = []
        for r in results:
            row = [r.subject_code, r.subject_name, r.detail_name]
            for amt in r.bucket_totals:
                row.append(amt)
            if has_neg:
                row.append(r.negative_balance)
            row.append(r.total_check)
            rows.append(row)

        # 合计行：先写真实合计值（回退模式下这就是最终值）；
        # make_excel 模式下 _patch_summary_formulas 会再替换为 SUM 公式
        if results:
            sum_row = ["合计", "", ""]
            for i in range(len(results[0].bucket_totals)):
                sum_row.append(sum(r.bucket_totals[i] for r in results))
            if has_neg:
                sum_row.append(sum(r.negative_balance for r in results))
            sum_row.append(sum(r.total_check for r in results))
            rows.append(sum_row)
        else:
            # 无数据时加占位行，确保 sheet 被创建
            placeholder = ["(无数据)", "", ""]
            for label in labels:
                placeholder.append(0.0)
            if has_neg:
                placeholder.append(0.0)
            placeholder.append(0.0)
            rows.append(placeholder)

        return pd.DataFrame(rows, columns=headers)

    def _patch_summary_formulas(self, output_path: PathLike,
                                results: list[AgingResult], config: dict,
                                sheet_name: str) -> None:
        """在 make_excel 生成后，用 SUM 公式替换合计行的占位值"""
        if not results:
            return
        wb = load_workbook(output_path)
        ws = wb[sheet_name]

        has_neg = any(abs(r.negative_balance) > 0.005 for r in results)
        labels = self._get_bucket_labels(config)
        sum_row = len(results) + 2  # make_excel 从第 1 行写表头，数据从第 2 行开始

        # 数字列从第 5 列（科目编码=B, 科目名称=C, 明细名称=D 之后）
        # make_excel 从 B 列(col=2) 开始写，所以：
        # B=科目编码, C=科目名称, D=明细名称, E=分档1, F=分档2, ..., 最后=合计
        first_num_col = 5  # E 列（B=科目编码, C=科目名称, D=明细名称 之后）
        last_num_col = 5 + len(labels) + (1 if has_neg else 0)  # 含合计列

        for col in range(first_num_col, last_num_col + 1):
            col_letter = get_column_letter(col)
            cell = ws.cell(row=sum_row, column=col)
            cell.value = f"=SUM({col_letter}2:{col_letter}{sum_row - 1})"
            # 项目约定：蓝字=手动输入，黑字=公式；写公式后显式置黑
            cell.font = Font(name=cell.font.name, size=cell.font.size,
                             bold=cell.font.bold, color="000000")

        wb.save(output_path)

    # ─── 逐笔追溯明细 ───────────────────────────────────────────
    def _build_entries(self, results: list[AgingResult], config: dict) -> pd.DataFrame:
        headers = ["科目编码", "科目名称", "明细名称", "来源", "来源日期", "金额", "账龄天数", "分档下标"]
        rows = []
        for result in results:
            for entry in result.entries:
                rows.append([
                    result.subject_code, result.subject_name, result.detail_name,
                    entry.source, entry.source_date, entry.amount,
                    entry.days, entry.bucket_index,
                ])
        return pd.DataFrame(rows, columns=headers)

    # ─── 期初余额验证 ───────────────────────────────────────────
    def _build_opening_check(self, results: list[AgingResult]) -> pd.DataFrame:
        has_buckets = any(r.opening_bucket_totals for r in results)

        if has_buckets:
            bucket_count = max(len(r.opening_bucket_totals) for r in results)
            headers = ["科目", "明细", "期初余额"]
            for i in range(bucket_count):
                headers.append(f"期初分档{i+1}")
            headers.append("期初分档合计")
        else:
            headers = ["科目", "明细", "期初余额"]
            bucket_count = 0

        rows = []
        for r in results:
            row = [r.subject_name, r.detail_name, r.opening_balance]
            for i in range(bucket_count):
                row.append(r.opening_bucket_totals[i] if i < len(r.opening_bucket_totals) else 0)
            if has_buckets:
                row.append(sum(r.opening_bucket_totals))
            rows.append(row)

        return pd.DataFrame(rows, columns=headers)

    # ─── 期末余额验证 ───────────────────────────────────────────
    def _build_closing_check(self, results: list[AgingResult]) -> pd.DataFrame:
        # "分档合计+负余额"是独立勾稽列：与"验证期末"公式不同源，避免循环论证
        headers = ["科目", "明细", "方向", "期初余额", "借方合计", "贷方合计",
                   "验证期末", "引擎期末", "差异", "分档合计+负余额", "勾稽差异"]
        rows = []
        for r in results:
            if r.direction == "debit":
                calc = r.opening_balance + r.total_debit - r.total_credit
            else:
                calc = r.opening_balance + r.total_credit - r.total_debit
            rows.append([
                r.subject_name, r.detail_name,
                "借方" if r.direction == "debit" else "贷方",
                r.opening_balance, r.total_debit, r.total_credit,
                calc, r.closing_balance, r.closing_balance - calc,
                r.total_check, r.closing_balance - r.total_check,
            ])
        return pd.DataFrame(rows, columns=headers)

    # ─── 参数说明 ───────────────────────────────────────────
    def _build_config(self, config: dict) -> pd.DataFrame:
        labels = self._get_bucket_labels(config)
        rows = [
            ("计算截止日期", str(config.get("cutoff_date", ""))),
            ("账龄分档", ", ".join(labels)),
            ("默认方向", config.get("direction", "")),
            ("计算口径", config.get("fifo_policy", "先进先出法 (收付款按最老余额优先核销)")),
            ("期初余额日期", str(config.get("opening_date", ""))),
            ("期初模式", config.get("aging_mode", "铁板模式")),
            ("分档边界规则", config.get("bucket_boundary_rule", "边界点归前档")),
            ("负余额展示", config.get("negative_balance_policy", "负余额单列展示，不并入正常账龄分档")),
        ]
        return pd.DataFrame(rows, columns=["参数", "值"])

    @staticmethod
    def _get_bucket_labels(config: dict) -> list[str]:
        """获取分档显示标签：优先用 bucket_labels，回退到 '{lo}-{hi}天'"""
        custom_labels: list[str] | None = config.get("bucket_labels")
        buckets: list[tuple[int, int]] = config.get("buckets", [])
        if custom_labels and len(custom_labels) == len(buckets):
            return list(custom_labels)
        return [f"{lo}-{hi}天" for lo, hi in buckets]
