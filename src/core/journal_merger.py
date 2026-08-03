# -*- coding: utf-8 -*-
"""序时账多文件合并"""
from __future__ import annotations
import logging
import pandas as pd
from src.core.column_mapper import ColumnMapper, REQUIRED_FIELDS
from src.core.data_loader import DataLoader

logger = logging.getLogger(__name__)


def merge_journal_files(dfs: list[pd.DataFrame], warnings_out: list[str] | None = None) -> pd.DataFrame:
    """合并多个序时账 DataFrame，每个自动匹配列名后拼接

    不做自动去重（需求口径）；完全重复的记录数通过 warnings_out 与 logging 提示。
    """
    loader = DataLoader()
    required = REQUIRED_FIELDS["journal"]
    normalized = []

    for i, df in enumerate(dfs):
        mapper = ColumnMapper()
        mapper.auto_map(list(df.columns), field_type="journal")
        # 校验必要字段
        mapping = mapper.get_mapping()
        missing = [f for f in required if not mapping.get(f)]
        if missing:
            raise ValueError(f"第 {i+1} 个文件缺少必要字段: {', '.join(missing)}")
        # 应用映射统一列名
        normalized_df = loader.apply_mapping(df, mapping)
        normalized.append(normalized_df)

    merged = pd.concat(normalized, ignore_index=True)

    # 按 (日期+科目+明细+借方+贷方) 统计完全重复行数，提示可能重复导入
    dup_cols = [c for c in ["日期", "科目编码", "明细名称", "借方金额", "贷方金额"] if c in merged.columns]
    if dup_cols:
        dup_count = int(merged.duplicated(subset=dup_cols).sum())
        if dup_count > 0:
            msg = (f"合并后发现 {dup_count} 行与前面完全重复的记录（日期+科目+明细+借方+贷方均相同），"
                   "可能是同一凭证被重复导入，请核对；本工具不做自动去重")
            logger.warning(msg)
            if warnings_out is not None:
                warnings_out.append(msg)

    return merged
