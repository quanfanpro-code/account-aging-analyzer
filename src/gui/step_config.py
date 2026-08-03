# -*- coding: utf-8 -*-
"""步骤 2：配置参数 — 账龄分档 + 截止日期 + 余额方向"""
from __future__ import annotations
import customtkinter as ctk
from datetime import date
from tkinter import messagebox

from src.gui.widgets import Card, make_button


class StepConfig(ctk.CTkFrame):
    """步骤 2：参数配置"""

    def __init__(self, master, state: dict):
        super().__init__(master, fg_color="transparent")
        self._state = state

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 左列：分档卡片
        self._buckets_card = self._build_buckets_card()
        self._buckets_card.grid(row=0, column=0, padx=(0, 6), sticky="nsew")

        # 右列上：日期卡片
        self._date_card = self._build_date_card()
        self._date_card.grid(row=0, column=1, padx=(6, 0), sticky="new")

        # 右列下：方向卡片
        self._direction_card = self._build_direction_card()
        self._direction_card.grid(row=1, column=1, padx=(6, 0), pady=(8, 0), sticky="new")

        # 分档行容器引用
        self._bucket_rows: list[dict] = []

    def refresh(self) -> None:
        """从共享状态刷新 UI 显示"""
        self._rebuild_bucket_rows()

    def _build_buckets_card(self) -> Card:
        card = Card(self, title="账龄分档设置")
        c = card.content
        c.grid_columnconfigure(0, weight=1)
        c.grid_columnconfigure(1, weight=1)
        c.grid_columnconfigure(2, weight=2)
        c.grid_columnconfigure(3, weight=0)

        # 表头
        h1 = ctk.CTkLabel(c, text="下限（天）", font=ctk.CTkFont(size=11), text_color=("gray50", "gray60"))
        h1.grid(row=0, column=0, padx=4, pady=(4, 2), sticky="w")
        h2 = ctk.CTkLabel(c, text="上限（天）", font=ctk.CTkFont(size=11), text_color=("gray50", "gray60"))
        h2.grid(row=0, column=1, padx=4, pady=(4, 2), sticky="w")
        h3 = ctk.CTkLabel(c, text="显示别名（如：3个月内）", font=ctk.CTkFont(size=11), text_color=("gray50", "gray60"))
        h3.grid(row=0, column=2, padx=4, pady=(4, 2), sticky="w")
        h4 = ctk.CTkLabel(c, text="操作", font=ctk.CTkFont(size=11), text_color=("gray50", "gray60"))
        h4.grid(row=0, column=3, padx=4, pady=(4, 2), sticky="w")

        # 分档行容器
        self._bucket_container = ctk.CTkFrame(c, fg_color="transparent")
        self._bucket_container.grid(row=1, column=0, columnspan=4, sticky="ew")
        self._bucket_container.grid_columnconfigure(0, weight=1)
        self._bucket_container.grid_columnconfigure(1, weight=1)
        self._bucket_container.grid_columnconfigure(2, weight=2)
        self._bucket_container.grid_columnconfigure(3, weight=0)

        # 按钮行
        btn_frame = ctk.CTkFrame(c, fg_color="transparent")
        btn_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        make_button(btn_frame, "+ 新增分档", level="secondary", width=100,
                    command=self._add_bucket).pack(side="left", padx=(0, 6))
        make_button(btn_frame, "重置默认", level="weak", width=90,
                    command=self._reset_buckets).pack(side="left")

        card._bucket_container = self._bucket_container
        card._btn_frame = btn_frame
        return card

    def _rebuild_bucket_rows(self) -> None:
        """根据 shared_state 重建分档行"""
        for w in self._bucket_container.winfo_children():
            w.destroy()
        self._bucket_rows.clear()

        buckets = self._state.get("buckets", [(0, 90), (90, 180), (180, 365), (365, 730), (730, 9999)])
        labels = self._state.get("bucket_labels", [])
        for i, (lo, hi) in enumerate(buckets):
            label = labels[i] if i < len(labels) else ""
            self._add_bucket_row(lo, hi, i, label)

    def _add_bucket_row(self, lo: int, hi: int, index: int, label: str = "") -> None:
        """添加一行分档输入"""
        row_frame = ctk.CTkFrame(self._bucket_container, fg_color="transparent")
        row_frame.grid(row=index, column=0, columnspan=4, sticky="ew", pady=1)
        row_frame.grid_columnconfigure(0, weight=1)
        row_frame.grid_columnconfigure(1, weight=1)
        row_frame.grid_columnconfigure(2, weight=2)
        row_frame.grid_columnconfigure(3, weight=0)

        lo_var = ctk.StringVar(value=str(lo))
        hi_var = ctk.StringVar(value=str(hi))
        alias_var = ctk.StringVar(value=label)

        e1 = ctk.CTkEntry(row_frame, textvariable=lo_var, width=80, height=30)
        e1.grid(row=0, column=0, padx=4, sticky="w")
        e2 = ctk.CTkEntry(row_frame, textvariable=hi_var, width=80, height=30)
        e2.grid(row=0, column=1, padx=4, sticky="w")
        e3 = ctk.CTkEntry(row_frame, textvariable=alias_var, width=160, height=30,
                          placeholder_text="留空则显示 0-90天")
        e3.grid(row=0, column=2, padx=4, sticky="ew")

        del_btn = make_button(row_frame, "✕", level="weak", width=30, height=30,
                              command=lambda idx=index: self._delete_bucket(idx))
        del_btn.grid(row=0, column=3, padx=4)

        self._bucket_rows.append({"lo_var": lo_var, "hi_var": hi_var, "alias_var": alias_var, "frame": row_frame})

    def _add_bucket(self) -> None:
        """新增一个分档"""
        buckets = self._read_buckets_from_ui()
        labels = self._read_labels_from_ui()
        if buckets:
            last_hi = buckets[-1][1]
        else:
            last_hi = 0
        buckets.append((last_hi, last_hi + 365))
        labels.append("")  # 新分档默认无别名
        self._state["buckets"] = buckets
        self._state["bucket_labels"] = labels
        self._rebuild_bucket_rows()

    def _delete_bucket(self, index: int) -> None:
        """删除指定分档"""
        buckets = self._read_buckets_from_ui()
        labels = self._read_labels_from_ui()
        if len(buckets) <= 1:
            messagebox.showwarning("无法删除", "至少保留一个分档")
            return
        del buckets[index]
        if index < len(labels):
            del labels[index]
        self._state["buckets"] = buckets
        self._state["bucket_labels"] = labels
        self._rebuild_bucket_rows()

    def _reset_buckets(self) -> None:
        """重置为默认分档"""
        self._state["buckets"] = [(0, 90), (90, 180), (180, 365), (365, 730), (730, 9999)]
        self._state["bucket_labels"] = []
        self._rebuild_bucket_rows()

    def _read_buckets_from_ui(self) -> list[tuple[int, int]]:
        """从 UI 读取当前分档列表；非法行号记录在 self._invalid_bucket_rows（1 起）"""
        result = []
        self._invalid_bucket_rows: list[int] = []
        for idx, row in enumerate(self._bucket_rows, start=1):
            try:
                lo = int(row["lo_var"].get())
                hi = int(row["hi_var"].get())
                result.append((lo, hi))
            except ValueError:
                self._invalid_bucket_rows.append(idx)
        return result

    def _read_labels_from_ui(self) -> list[str]:
        """从 UI 读取分档别名标签（与 _read_buckets_from_ui 保持行对齐）"""
        result = []
        for row in self._bucket_rows:
            try:
                int(row["lo_var"].get())
                int(row["hi_var"].get())
                result.append(row["alias_var"].get().strip())
            except ValueError:
                continue
        return result

    def _build_date_card(self) -> Card:
        card = Card(self, title="计算日期设置")
        c = card.content

        # 截止日期
        lbl1 = ctk.CTkLabel(c, text="截止日期（YYYY-MM-DD）：", font=ctk.CTkFont(size=12))
        lbl1.pack(anchor="w", pady=(4, 4))
        self._date_var = ctk.StringVar(value=date.today().strftime("%Y-%m-%d"))
        entry1 = ctk.CTkEntry(c, textvariable=self._date_var, width=200, height=32)
        entry1.pack(anchor="w", pady=(0, 4))

        # 期初日期（用于期初分档账龄偏移）
        lbl2 = ctk.CTkLabel(c, text="期初余额日期（YYYY-MM-DD）：", font=ctk.CTkFont(size=12))
        lbl2.pack(anchor="w", pady=(8, 4))
        # 安全计算去年同一天（处理闰年 2-29）
        today = date.today()
        try:
            last_year_date = today.replace(year=today.year - 1)
        except ValueError:
            # 2月29日在去年不存在，回退到2月28日
            last_year_date = date(today.year - 1, 2, 28)
        self._opening_date_var = ctk.StringVar(value=last_year_date.strftime("%Y-%m-%d"))
        entry2 = ctk.CTkEntry(c, textvariable=self._opening_date_var, width=200, height=32)
        entry2.pack(anchor="w", pady=(0, 4))

        tip = ctk.CTkLabel(c, text='期初日期用于将期初分档账龄偏移到截止日期（期初"1年以内"→截止日"1-2年"）',
                           font=ctk.CTkFont(size=11), text_color=("gray50", "gray60"))
        tip.pack(anchor="w")

        # 提示：如果期初无分档则不影响计算
        tip2 = ctk.CTkLabel(c, text="（未检测到分档列时，也会用该日期精确计算铁板模式下的期初账龄）",
                           font=ctk.CTkFont(size=10), text_color=("gray50", "gray60"))
        tip2.pack(anchor="w")
        return card

    def _build_direction_card(self) -> Card:
        card = Card(self, title="默认方向")
        c = card.content

        tip = ctk.CTkLabel(c, text="系统会自动判断每个科目的方向，识别不了的才用这里选的默认方向",
                           font=ctk.CTkFont(size=11), text_color=("gray50", "gray60"))
        tip.pack(anchor="w", pady=(4, 4))

        self._dir_var = ctk.StringVar(value="debit")
        r1 = ctk.CTkRadioButton(c, text="借方（应收 / 预付 / 其他应收）",
                                variable=self._dir_var, value="debit",
                                font=ctk.CTkFont(size=13))
        r1.pack(anchor="w", pady=(4, 4))
        r2 = ctk.CTkRadioButton(c, text="贷方（应付 / 预收 / 其他应付）",
                                variable=self._dir_var, value="credit",
                                font=ctk.CTkFont(size=13))
        r2.pack(anchor="w", pady=(0, 4))
        return card

    def validate(self) -> bool:
        """校验参数合法性"""
        errors = []

        # 校验截止日期（用局部变量传递，避免校验失败时引用未定义的 d）
        cutoff = None
        try:
            parts = self._date_var.get().strip().split("-")
            if len(parts) != 3:
                raise ValueError
            cutoff = date(int(parts[0]), int(parts[1]), int(parts[2]))
            self._state["cutoff_date"] = cutoff
        except (ValueError, IndexError):
            errors.append("截止日期格式错误，请输入 YYYY-MM-DD")

        # 校验期初日期（可选；如填写则必须早于截止日期）
        try:
            parts = self._opening_date_var.get().strip().split("-")
            if len(parts) == 3:
                od = date(int(parts[0]), int(parts[1]), int(parts[2]))
                if cutoff is not None and od >= cutoff:
                    errors.append("期初日期必须早于截止日期")
                self._state["opening_date"] = od
            else:
                self._state["opening_date"] = None
        except (ValueError, IndexError):
            if self._opening_date_var.get().strip():
                errors.append("期初余额日期格式错误，请输入 YYYY-MM-DD")
            self._state["opening_date"] = None

        # 校验分档
        buckets = self._read_buckets_from_ui()
        invalid_rows = getattr(self, "_invalid_bucket_rows", [])
        if invalid_rows:
            rows_text = "、".join(str(i) for i in invalid_rows)
            errors.append(f"第 {rows_text} 行分档填的不是数字，已忽略这些行，请修正后再继续")
        if not buckets:
            errors.append("至少需要一个账龄分档")
        else:
            for i, (lo, hi) in enumerate(buckets):
                if lo >= hi:
                    errors.append(f"第 {i+1} 个分档：下限 ({lo}) 必须小于上限 ({hi})")
            # 检查连续性
            for i in range(1, len(buckets)):
                if buckets[i][0] != buckets[i - 1][1]:
                    errors.append(f"第 {i+1} 档下限 ({buckets[i][0]}) 应等于第 {i} 档上限 ({buckets[i-1][1]})")
            self._state["buckets"] = buckets

        # 读取别名标签
        bucket_labels = self._read_labels_from_ui()
        self._state["bucket_labels"] = bucket_labels

        # 方向
        self._state["direction"] = self._dir_var.get()

        if errors:
            messagebox.showwarning("校验未通过", "\n".join(errors))
            return False
        return True
