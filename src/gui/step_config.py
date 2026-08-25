# -*- coding: utf-8 -*-
"""步骤 2：配置账龄分档、账龄名称和计算日期。"""
from __future__ import annotations
import customtkinter as ctk
from datetime import date
from tkinter import messagebox

from src.gui.widgets import Card, make_button


def default_bucket_label(lo: int, hi: int) -> str:
    return f"{lo}天以上" if hi == 9999 else f"{lo}-{hi}天"


def sync_default_bucket_label(
    current: str,
    previous_default: str,
    lo: int,
    hi: int,
) -> tuple[str, str]:
    new_default = default_bucket_label(lo, hi)
    return (new_default if current == previous_default else current, new_default)


def validate_bucket_labels(labels: list[str], bucket_count: int) -> None:
    if len(labels) != bucket_count:
        raise ValueError("账龄名称数量必须与账龄档位数量一致")
    normalized = [str(label).strip() for label in labels]
    if any(not label for label in normalized):
        raise ValueError("账龄名称不能为空")
    if len(set(normalized)) != len(normalized):
        raise ValueError("账龄名称不能重复")


def parse_opening_date(value: str, cutoff: date, has_opening: bool) -> date | None:
    if not has_opening:
        return None
    text = value.strip()
    if not text:
        raise ValueError("选择期初余额后必须填写期初余额日期")
    try:
        opening_date = date.fromisoformat(text)
    except ValueError as error:
        raise ValueError("期初余额日期格式错误，请输入 YYYY-MM-DD") from error
    if opening_date >= cutoff:
        raise ValueError("期初余额日期必须早于截止日期")
    return opening_date


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

        # 分档行容器引用
        self._bucket_rows: list[dict] = []

    def refresh(self) -> None:
        """从共享状态刷新 UI 显示"""
        self._rebuild_bucket_rows()
        opening_date = self._state.get("opening_date")
        has_opening = bool(self._state.get("opening_path"))
        if has_opening:
            self._opening_date_entry.configure(state="normal")
            self._opening_date_var.set(opening_date.isoformat() if opening_date else "")
            self._opening_date_tip.configure(
                text="请选择期初余额对应的日期（必须早于截止日期）",
                text_color=("gray50", "gray60"),
            )
        else:
            self._opening_date_var.set("")
            self._state["opening_date"] = None
            self._opening_date_entry.configure(state="disabled")
            self._opening_date_tip.configure(
                text="无期初余额，无需填写",
                text_color=("#27AE60", "#27AE60"),
            )

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
        h3 = ctk.CTkLabel(c, text="账龄名称", font=ctk.CTkFont(size=11), text_color=("gray50", "gray60"))
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
            label = labels[i].strip() if i < len(labels) and str(labels[i]).strip() else default_bucket_label(lo, hi)
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
        auto_label = default_bucket_label(lo, hi)
        alias_var = ctk.StringVar(value=label or auto_label)

        e1 = ctk.CTkEntry(row_frame, textvariable=lo_var, width=80, height=30)
        e1.grid(row=0, column=0, padx=4, sticky="w")
        e2 = ctk.CTkEntry(row_frame, textvariable=hi_var, width=80, height=30)
        e2.grid(row=0, column=1, padx=4, sticky="w")
        e3 = ctk.CTkEntry(row_frame, textvariable=alias_var, width=160, height=30)
        e3.grid(row=0, column=2, padx=4, sticky="ew")

        del_btn = make_button(row_frame, "✕", level="weak", width=30, height=30,
                              command=lambda idx=index: self._delete_bucket(idx))
        del_btn.grid(row=0, column=3, padx=4)

        row = {
            "lo_var": lo_var, "hi_var": hi_var, "alias_var": alias_var,
            "default_label": auto_label, "frame": row_frame,
        }
        self._bucket_rows.append(row)

        def sync_label(*_args) -> None:
            try:
                current = alias_var.get()
                new_label, new_default = sync_default_bucket_label(
                    current, row["default_label"], int(lo_var.get()), int(hi_var.get()),
                )
                row["default_label"] = new_default
                if new_label != current:
                    alias_var.set(new_label)
            except ValueError:
                return

        lo_var.trace_add("write", sync_label)
        hi_var.trace_add("write", sync_label)

    def _add_bucket(self) -> None:
        """新增一个分档"""
        buckets = self._read_buckets_from_ui()
        labels = self._read_labels_from_ui()
        if buckets:
            last_hi = buckets[-1][1]
        else:
            last_hi = 0
        buckets.append((last_hi, last_hi + 365))
        labels.append(default_bucket_label(*buckets[-1]))
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
        self._state["bucket_labels"] = [
            default_bucket_label(lo, hi) for lo, hi in self._state["buckets"]
        ]
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
        self._opening_date_var = ctk.StringVar(value="")
        self._opening_date_entry = ctk.CTkEntry(c, textvariable=self._opening_date_var, width=200, height=32)
        self._opening_date_entry.pack(anchor="w", pady=(0, 4))

        tip = ctk.CTkLabel(c, text='期初日期用于将期初分档账龄偏移到截止日期（期初"1年以内"→截止日"1-2年"）',
                           font=ctk.CTkFont(size=11), text_color=("gray50", "gray60"))
        tip.pack(anchor="w")

        # 提示：如果期初无分档则不影响计算
        self._opening_date_tip = ctk.CTkLabel(
            c, text="", font=ctk.CTkFont(size=10), text_color=("gray50", "gray60"),
        )
        self._opening_date_tip.pack(anchor="w")
        return card

    def validate(self) -> bool:
        """校验参数合法性"""
        errors = []

        # 校验截止日期
        cutoff = None
        try:
            cutoff = date.fromisoformat(self._date_var.get().strip())
            self._state["cutoff_date"] = cutoff
        except ValueError:
            errors.append("截止日期格式错误，请输入 YYYY-MM-DD")

        if cutoff is not None:
            try:
                self._state["opening_date"] = parse_opening_date(
                    self._opening_date_var.get(), cutoff, bool(self._state.get("opening_path")),
                )
            except ValueError as error:
                errors.append(str(error))

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

        # 账龄名称必须与档位逐项对应、非空且唯一
        bucket_labels = self._read_labels_from_ui()
        try:
            validate_bucket_labels(bucket_labels, len(buckets))
            self._state["bucket_labels"] = bucket_labels
        except ValueError as error:
            errors.append(str(error))

        if errors:
            messagebox.showwarning("校验未通过", "\n".join(errors))
            return False
        return True
