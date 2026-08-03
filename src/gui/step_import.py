# -*- coding: utf-8 -*-
"""步骤 1：导入数据 — 双文件选择 + 双列映射 + 预览"""
from __future__ import annotations
import customtkinter as ctk
import pandas as pd
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

from src.gui.widgets import Card, make_button
from src.core.column_mapper import ColumnMapper, REQUIRED_FIELDS
from src.core.data_loader import DataLoader


class StepImport(ctk.CTkFrame):
    """步骤 1：期初余额 + 序时账双文件导入"""

    def __init__(self, master, state: dict):
        super().__init__(master, fg_color="transparent")
        self._state = state
        self._loader = DataLoader()

        # 两个列映射器
        self._opening_mapper = ColumnMapper()
        self._journal_mapper = ColumnMapper()

        # 初始化共享状态：是否启用分档模式由“是否检测到分档列”自动决定。
        self._state.setdefault("opening_has_aging", False)
        self._state.setdefault("opening_aging_columns", {})

        # 上部分：期初余额卡片（左）+ 序时账卡片（右）
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._opening_card = self._build_file_card("期初余额", col=0, is_opening=True)
        self._journal_card = self._build_file_card("序时账", col=1, is_opening=False)

    def _build_file_card(self, label: str, col: int, is_opening: bool = False) -> Card:
        """构建一个文件导入卡片"""
        card = Card(self, title=label)
        card.grid(row=0, column=col, padx=(0 if col == 0 else 6, 6 if col == 0 else 0), sticky="nsew")
        c = card.content
        c.grid_columnconfigure(0, weight=1)

        # 文件选择行
        row_frame = ctk.CTkFrame(c, fg_color="transparent")
        row_frame.grid(row=0, column=0, sticky="ew", pady=(4, 4))
        row_frame.grid_columnconfigure(0, weight=1)

        path_var = ctk.StringVar()
        entry = ctk.CTkEntry(row_frame, textvariable=path_var, height=32)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        btn = make_button(row_frame, "选择文件", level="secondary", width=90)
        btn.grid(row=0, column=1, sticky="e")

        # 预览区
        preview_row = 1
        preview_frame = ctk.CTkScrollableFrame(c, height=160, fg_color=("gray90", "gray15"))
        preview_frame.grid(row=preview_row, column=0, sticky="ew", pady=(4, 4))

        preview_label = ctk.CTkLabel(
            preview_frame, text="（尚未选择文件）",
            font=ctk.CTkFont(size=12),
            text_color=("gray50", "gray60"),
        )
        preview_label.pack(padx=8, pady=8, anchor="w")

        # 期初账龄分档检测结果显示区
        aging_detect_frame = None
        if is_opening:
            aging_detect_frame = ctk.CTkFrame(c, fg_color=("gray95", "gray20"))
            aging_detect_frame.grid(row=preview_row + 1, column=0, sticky="ew", pady=(0, 4))
            aging_detect_label = ctk.CTkLabel(
                aging_detect_frame, text="",
                font=ctk.CTkFont(size=11),
                text_color=("gray50", "gray60"),
            )
            aging_detect_label.pack(padx=8, pady=4, anchor="w")

        # 列映射区
        map_row = preview_row + (2 if is_opening else 1)
        map_label = ctk.CTkLabel(
            c, text="列映射（自动匹配 → 可手动调整）：",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        )
        map_label.grid(row=map_row, column=0, sticky="ew", pady=(8, 2))

        map_frame = ctk.CTkFrame(c, fg_color="transparent")
        map_frame.grid(row=map_row + 1, column=0, sticky="ew")

        # 存储引用
        field_type = "balance" if "期初" in label else "journal"
        card._path_var = path_var
        card._preview_frame = preview_frame
        card._preview_label = preview_label
        card._map_frame = map_frame
        card._field_type = field_type
        card._map_widgets = {}
        if is_opening:
            card._aging_detect_frame = aging_detect_frame
            card._aging_detect_label = aging_detect_label

        # 按钮事件
        btn.configure(command=lambda: self._on_select_file(card))

        return card

    def _on_select_file(self, card: Card) -> None:
        """打开文件选择对话框，加载 Excel 并预览"""
        # Card 必有 _title_label 属性（可能为 None），直接用，勿走 winfo_children 间接取
        title = card._title_label.cget("text") if card._title_label else "文件"
        if card._field_type == "journal":
            paths = filedialog.askopenfilenames(
                title=f"选择{title}（可多选）",
                filetypes=[("Excel 文件", "*.xlsx"), ("所有文件", "*.*")],
            )
            if not paths:
                return
            path = " ; ".join(paths)
        else:
            path = filedialog.askopenfilename(
                title=f"选择{title}",
                filetypes=[("Excel 文件", "*.xlsx"), ("所有文件", "*.*")],
            )
            if not path:
                return
            paths = [path]

        card._path_var.set(path)

        # 通过 field_type 区分期初/序时账
        if card._field_type == "balance":
            self._state["opening_path"] = path
        else:
            self._state["journal_path"] = path

        # 读取放后台线程，避免大文件卡住界面；读完后回主线程更新
        card._preview_label.configure(
            text="正在读取文件，请稍候...",
            text_color=("#E67E22", "#E67E22"),
        )
        threading.Thread(target=self._load_file_worker, args=(card, list(paths)), daemon=True).start()

    @staticmethod
    def _read_first_sheet(path: str, notes: list[str]) -> pd.DataFrame:
        """读取 Excel 第一个工作表；多 sheet 时记录提示"""
        xf = pd.ExcelFile(path)
        if len(xf.sheet_names) > 1:
            notes.append(
                f"文件 {Path(path).name} 有 {len(xf.sheet_names)} 个工作表，"
                f"只读取了第一个工作表「{xf.sheet_names[0]}」"
            )
        return pd.read_excel(xf, sheet_name=0)

    def _load_file_worker(self, card: Card, paths: list[str]) -> None:
        """后台线程读取 Excel，不碰界面控件"""
        notes: list[str] = []
        try:
            if card._field_type == "journal" and len(paths) > 1:
                from src.core.journal_merger import merge_journal_files
                dfs = [self._read_first_sheet(p, notes) for p in paths]
                df = merge_journal_files(dfs, warnings_out=notes)
            else:
                df = self._read_first_sheet(paths[0], notes)
        except Exception as e:
            self.after(0, lambda err=str(e): self._on_load_failed(card, err))
            return
        self.after(0, lambda: self._on_load_success(card, df, notes))

    def _on_load_failed(self, card: Card, err: str) -> None:
        """读取失败（主线程）"""
        card._preview_label.configure(
            text="（读取失败）", text_color=("#E74C3C", "#E74C3C"))
        messagebox.showerror("读取失败", f"无法读取 Excel 文件：{err}")

    def _on_load_success(self, card: Card, df: pd.DataFrame, notes: list[str]) -> None:
        """读取成功后的界面更新（主线程）"""
        mapper = self._opening_mapper if card._field_type == "balance" else self._journal_mapper

        # 保存到共享状态
        if card._field_type == "balance":
            self._state["opening_df"] = df
            # 检测期初账龄分档列
            self._detect_and_show_aging(card)
        else:
            self._state["journal_df"] = df

        # 更新预览（含多 sheet / 重复记录等提示）
        self._show_preview(card, df, notes)

        # 自动匹配列映射
        columns = list(df.columns)
        mapper.auto_map(columns, field_type=card._field_type)

        # 更新映射 UI
        self._build_map_ui(card, mapper)

        # 保存映射到共享状态
        if card._field_type == "balance":
            self._state["opening_mapping"] = mapper.get_mapping()
        else:
            self._state["journal_mapping"] = mapper.get_mapping()

    def _show_preview(self, card: Card, df: pd.DataFrame, notes: list[str] | None = None) -> None:
        """在预览区显示前 10 行（notes 为读取时的提示，如多 sheet 只读第一个）"""
        pf = card._preview_frame
        # 清除旧内容
        for w in pf.winfo_children():
            w.destroy()

        for note in notes or []:
            ctk.CTkLabel(pf, text=f"⚠️ {note}", font=ctk.CTkFont(size=11),
                         text_color=("#E67E22", "#E67E22"),
                         anchor="w", wraplength=380, justify="left").pack(padx=8, pady=(4, 0), anchor="w")

        preview_rows = min(10, len(df))
        cols = list(df.columns)

        if preview_rows == 0:
            ctk.CTkLabel(pf, text="（空文件）", font=ctk.CTkFont(size=12),
                         text_color=("gray50", "gray60")).pack(padx=8, pady=8, anchor="w")
            return

        # 简易表格：用 Label 拼
        header_text = "  |  ".join(cols)
        ctk.CTkLabel(pf, text=header_text, font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").pack(padx=8, pady=(4, 2), anchor="w")

        for i in range(preview_rows):
            row_vals = [str(df.iloc[i][c])[:20] for c in cols]
            row_text = "  |  ".join(row_vals)
            ctk.CTkLabel(pf, text=row_text, font=ctk.CTkFont(size=11),
                         anchor="w").pack(padx=8, pady=1, anchor="w")

        if len(df) > preview_rows:
            ctk.CTkLabel(pf, text=f"... 共 {len(df)} 行，仅显示前 {preview_rows} 行",
                         font=ctk.CTkFont(size=10),
                         text_color=("gray50", "gray60")).pack(padx=8, pady=2, anchor="w")

    def _build_map_ui(self, card: Card, mapper: ColumnMapper) -> None:
        """根据映射器构建列映射下拉 UI"""
        mf = card._map_frame
        for w in mf.winfo_children():
            w.destroy()

        mapping = mapper.get_mapping()
        df = self._state.get("opening_df") if card._field_type == "balance" else self._state.get("journal_df")
        columns = list(df.columns) if df is not None else []
        columns_with_none = ["(未映射)"] + columns

        card._map_widgets = {}
        row_idx = 0
        for field_name, mapped_col in mapping.items():
            lbl = ctk.CTkLabel(mf, text=field_name, font=ctk.CTkFont(size=12), width=80, anchor="w")
            lbl.grid(row=row_idx, column=0, padx=(0, 8), pady=2, sticky="w")

            var = ctk.StringVar(value=mapped_col if mapped_col else "(未映射)")
            combo = ctk.CTkComboBox(mf, values=columns_with_none, variable=var, width=180)
            combo.grid(row=row_idx, column=1, padx=(0, 4), pady=2, sticky="w")

            # 保存引用以便后续获取值
            card._map_widgets[field_name] = var

            def make_callback(fn=field_name, m=mapper, c=card):
                return lambda choice, fn=fn, m=mapper, c=c: self._on_map_change(fn, choice, m, c)

            combo.configure(command=make_callback())
            row_idx += 1

    def _detect_and_show_aging(self, card: Card) -> None:
        """检测期初账龄分档列并显示"""
        if not hasattr(card, '_aging_detect_label'):
            return
        df = self._state.get("opening_df")
        if df is None:
            return

        columns = list(df.columns)
        mapper = ColumnMapper()
        aging_cols = mapper.detect_aging_columns(columns)

        if aging_cols:
            label = card._aging_detect_label
            col_names = [f"{lo}-{hi}天 → {name}" for (lo, hi), name in aging_cols]
            label.configure(
                text=f"已检测到账龄分档列，将自动使用分档模式：{', '.join(col_names)}",
                text_color=("#27AE60", "#27AE60"),
            )
            # 保存到共享状态
            self._state["opening_aging_columns"] = {k: v for k, v in aging_cols}
            self._state["opening_has_aging"] = True
        else:
            card._aging_detect_label.configure(
                text="未检测到账龄分档列，将自动使用铁板模式",
                text_color=("#E74C3C", "#E74C3C"),
            )
            self._state["opening_aging_columns"] = {}
            self._state["opening_has_aging"] = False

    def _on_map_change(self, field_name: str, choice: str, mapper: ColumnMapper, card: Card) -> None:
        """映射下拉变更时更新 mapper 和共享状态"""
        if choice == "(未映射)":
            mapper.set_mapping(field_name, None)
        else:
            mapper.set_mapping(field_name, choice)

        if card._field_type == "balance":
            self._state["opening_mapping"] = mapper.get_mapping()
        else:
            self._state["journal_mapping"] = mapper.get_mapping()

    def validate(self) -> bool:
        """校验：两个文件都已选择、必填字段已映射"""
        errors = []
        if not self._state.get("opening_path"):
            errors.append("请选择期初余额文件")
        if not self._state.get("journal_path"):
            errors.append("请选择序时账文件")

        if not errors:
            try:
                self._opening_mapper.validate_required(REQUIRED_FIELDS["balance"])
            except ValueError as e:
                errors.append(f"期初余额：{e}")
            try:
                self._journal_mapper.validate_required(REQUIRED_FIELDS["journal"])
            except ValueError as e:
                errors.append(f"序时账：{e}")

        if errors:
            messagebox.showwarning("校验未通过", "\n".join(errors))
            return False
        return True
