# -*- coding: utf-8 -*-
"""步骤 1：导入数据 — 双文件选择 + 双列映射 + 预览"""
from __future__ import annotations
import customtkinter as ctk
import pandas as pd
import queue
import threading
from tkinter import filedialog, messagebox

from src.gui.widgets import Card, make_button
from src.core.column_mapper import ColumnMapper, REQUIRED_ANY_FIELDS, REQUIRED_FIELDS
from src.core.current_accounts import CurrentAccountFilterResult, filter_current_accounts
from src.core.data_loader import DataLoader


def reset_source_payload(state: dict, prefix: str) -> None:
    """切换工作表时清空由旧工作表产生的状态。"""
    state[f"{prefix}_sheet"] = None
    state[f"{prefix}_df"] = None
    state[f"{prefix}_mapping"] = {}
    state[f"{prefix}_filter_summary"] = ""
    if prefix == "opening":
        state["opening_aging_columns"] = {}
        state["opening_has_aging"] = False


def next_source_request(state: dict, prefix: str) -> int:
    """生成递增请求号，用于丢弃晚到的旧读取结果。"""
    key = f"{prefix}_request_id"
    state[key] = int(state.get(key, 0)) + 1
    return state[key]


def is_current_source_request(state: dict, prefix: str, request_id: int) -> bool:
    return state.get(f"{prefix}_request_id") == request_id


def clear_source_state(state: dict, prefix: str) -> None:
    """彻底清除一个文件卡片及其派生状态。"""
    next_source_request(state, prefix)
    reset_source_payload(state, prefix)
    state[f"{prefix}_path"] = None
    state[f"{prefix}_sheet_names"] = []
    if prefix == "opening":
        state["opening_date"] = None


def format_filter_summary(result: CurrentAccountFilterResult) -> str:
    """把过滤统计整理成导入页可直接显示的简短中文摘要。"""
    lines = [
        f"原始 {result.original_rows} 行｜保留 {result.retained_rows} 行｜忽略 {result.ignored_rows} 行",
    ]
    if result.ignored_counts:
        lines.append("忽略原因：" + "；".join(
            f"{reason} {count} 行" for reason, count in result.ignored_counts.items()
        ))
    lines.append("往来分项：" + "；".join(
        f"{category} {count} 行" for category, count in result.category_counts.items()
    ))
    lines.append("识别方式：" + "；".join(
        f"{basis} {count} 行" for basis, count in result.recognition_counts.items()
    ))
    amounts = "，".join(f"{name} {value:.2f}" for name, value in result.blank_detail_amounts.items())
    lines.append(f"未填明细 {result.blank_detail_rows} 行（{amounts}）")
    lines.append(f"名称与编码冲突 {result.warning_count} 行")
    return "\n".join(lines)


class StepImport(ctk.CTkFrame):
    """步骤 1：期初余额 + 序时账双文件导入"""

    def __init__(self, master, state: dict):
        super().__init__(master, fg_color="transparent")
        self._state = state
        self._loader = DataLoader()

        # 后台读取线程只往队列塞消息，主线程用 after 泵统一消费（与步骤 3 同一模式，线程安全）
        self._msg_queue: queue.Queue = queue.Queue()
        self.after(100, self._poll_queue)

        # 两个列映射器
        self._opening_mapper = ColumnMapper()
        self._journal_mapper = ColumnMapper()

        # 初始化共享状态：是否启用分档模式由“是否检测到分档列”自动决定。
        self._state.setdefault("opening_has_aging", False)
        self._state.setdefault("opening_aging_columns", {})
        for prefix in ("opening", "journal"):
            self._state.setdefault(f"{prefix}_sheet_names", [])
            self._state.setdefault(f"{prefix}_sheet", None)
            self._state.setdefault(f"{prefix}_request_id", 0)
            self._state.setdefault(f"{prefix}_filter_summary", "")

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

        if is_opening:
            clear_btn = make_button(row_frame, "清除期初", level="weak", width=80)
            clear_btn.grid(row=0, column=2, padx=(6, 0), sticky="e")

        # 工作表选择行
        sheet_frame = ctk.CTkFrame(c, fg_color="transparent")
        sheet_frame.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        sheet_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(sheet_frame, text="工作表：", width=62, anchor="w").grid(row=0, column=0, sticky="w")
        sheet_var = ctk.StringVar(value="尚未读取工作表")
        sheet_combo = ctk.CTkComboBox(
            sheet_frame, variable=sheet_var, values=["尚未读取工作表"], state="disabled",
        )
        sheet_combo.grid(row=0, column=1, sticky="ew")

        # 预览区
        preview_row = 2
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
            # 提示：期初余额可选，不选则按 0 计算
            tip = ctk.CTkLabel(
                aging_detect_frame, text="（不选则期初余额视为 0）",
                font=ctk.CTkFont(size=11),
                text_color=("gray50", "gray60"),
            )
            tip.pack(padx=8, pady=(0, 4), anchor="w")

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

        summary_label = ctk.CTkLabel(
            c, text="", font=ctk.CTkFont(size=11), anchor="w",
            justify="left", wraplength=430, text_color=("gray35", "gray70"),
        )
        summary_label.grid(row=map_row + 2, column=0, sticky="ew", pady=(8, 2))

        # 存储引用
        field_type = "balance" if "期初" in label else "journal"
        card._path_var = path_var
        card._preview_frame = preview_frame
        card._preview_label = preview_label
        card._map_frame = map_frame
        card._field_type = field_type
        card._prefix = "opening" if is_opening else "journal"
        card._sheet_var = sheet_var
        card._sheet_combo = sheet_combo
        card._summary_label = summary_label
        card._map_widgets = {}
        if is_opening:
            card._aging_detect_frame = aging_detect_frame
            card._aging_detect_label = aging_detect_label

        # 按钮事件
        btn.configure(command=lambda: self._on_select_file(card))
        sheet_combo.configure(command=lambda value: self._on_select_sheet(card, value))
        if is_opening:
            clear_btn.configure(command=lambda: self._clear_opening(card))

        return card

    def _on_select_file(self, card: Card) -> None:
        """一次选择一个 Excel 文件并读取工作表列表。"""
        # Card 必有 _title_label 属性（可能为 None），直接用，勿走 winfo_children 间接取
        title = card._title_label.cget("text") if card._title_label else "文件"
        path = filedialog.askopenfilename(
            title=f"选择{title}",
            filetypes=[("Excel 文件", "*.xlsx"), ("所有文件", "*.*")],
        )
        if not path:
            return

        clear_source_state(self._state, card._prefix)
        self._reset_card_display(card)
        card._path_var.set(path)
        self._state[f"{card._prefix}_path"] = path
        request_id = next_source_request(self._state, card._prefix)

        # 读取放后台线程，避免大文件卡住界面；读完后回主线程更新
        self._set_preview_message(card, "正在读取文件，请稍候...", "#E67E22")
        threading.Thread(
            target=self._load_sheet_names_worker,
            args=(card, path, request_id), daemon=True,
        ).start()

    def _load_sheet_names_worker(self, card: Card, path: str, request_id: int) -> None:
        """后台读取工作表名称，不碰界面控件。"""
        try:
            sheet_names = self._loader.list_sheet_names(path)
        except Exception as e:
            self._msg_queue.put(("load_failed", (card, request_id, str(e))))
            return
        self._msg_queue.put(("sheet_names", (card, request_id, sheet_names)))

    def _on_sheet_names_success(self, card: Card, request_id: int, sheet_names: list[str]) -> None:
        if not is_current_source_request(self._state, card._prefix, request_id):
            return
        self._state[f"{card._prefix}_sheet_names"] = sheet_names
        if not sheet_names:
            self._on_load_failed(card, request_id, "工作簿中没有可读取的工作表")
            return
        card._sheet_combo.configure(values=sheet_names, state="readonly")  # 只选不输，避免手输不存在的工作表名
        initial = self._loader.initial_sheet(sheet_names)
        if initial is None:
            card._sheet_var.set("请选择工作表")
            self._set_preview_message(card, "文件包含多个工作表，请手动选择", "#E67E22")
            return
        card._sheet_var.set(initial)
        self._select_sheet(card, initial)

    def _on_select_sheet(self, card: Card, sheet_name: str) -> None:
        if sheet_name in {"", "请选择工作表", "尚未读取工作表"}:
            return
        self._select_sheet(card, sheet_name)

    def _select_sheet(self, card: Card, sheet_name: str) -> None:
        path = self._state.get(f"{card._prefix}_path")
        if not path:
            return
        reset_source_payload(self._state, card._prefix)
        self._state[f"{card._prefix}_sheet"] = sheet_name
        card._sheet_var.set(sheet_name)
        self._reset_payload_display(card)
        request_id = next_source_request(self._state, card._prefix)
        self._set_preview_message(card, "正在读取工作表，请稍候...", "#E67E22")
        threading.Thread(
            target=self._load_sheet_worker,
            args=(card, path, sheet_name, request_id), daemon=True,
        ).start()

    def _load_sheet_worker(self, card: Card, path: str, sheet_name: str, request_id: int) -> None:
        try:
            df = self._loader.load_sheet(path, sheet_name)
        except Exception as e:
            self._msg_queue.put(("load_failed", (card, request_id, str(e))))
            return
        self._msg_queue.put(("load_success", (card, request_id, df)))

    def _poll_queue(self) -> None:
        """主线程消息泵：消费后台读取线程塞进来的界面更新"""
        try:
            while True:
                kind, payload = self._msg_queue.get_nowait()
                card, request_id, data = payload
                if kind == "sheet_names":
                    self._on_sheet_names_success(card, request_id, data)
                elif kind == "load_success":
                    self._on_load_success(card, request_id, data)
                elif kind == "load_failed":
                    self._on_load_failed(card, request_id, data)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _on_load_failed(self, card: Card, request_id: int, err: str) -> None:
        """读取失败（主线程）"""
        if not is_current_source_request(self._state, card._prefix, request_id):
            return
        reset_source_payload(self._state, card._prefix)
        self._set_preview_message(card, "（读取失败）", "#E74C3C")
        messagebox.showerror("读取失败", f"无法读取 Excel 文件：{err}")

    def _on_load_success(self, card: Card, request_id: int, df: pd.DataFrame) -> None:
        """读取成功后的界面更新（主线程）"""
        if not is_current_source_request(self._state, card._prefix, request_id):
            return
        mapper = self._opening_mapper if card._field_type == "balance" else self._journal_mapper

        # 保存到共享状态
        if card._field_type == "balance":
            self._state["opening_df"] = df
            # 检测期初账龄分档列
            self._detect_and_show_aging(card)
        else:
            self._state["journal_df"] = df

        # 更新预览（含多 sheet / 重复记录等提示）
        self._show_preview(card, df)

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
        self._recalculate_filter_summary(card, mapper)

    def _set_preview_message(self, card: Card, text: str, color) -> None:
        for widget in card._preview_frame.winfo_children():
            widget.destroy()
        label = ctk.CTkLabel(
            card._preview_frame, text=text, font=ctk.CTkFont(size=12),
            text_color=(color, color) if isinstance(color, str) and color.startswith("#") else color,
        )
        label.pack(padx=8, pady=8, anchor="w")
        card._preview_label = label

    def _reset_payload_display(self, card: Card) -> None:
        self._set_preview_message(card, "（尚未读取工作表）", ("gray50", "gray60"))
        for widget in card._map_frame.winfo_children():
            widget.destroy()
        card._map_widgets = {}
        card._summary_label.configure(text="")
        if hasattr(card, "_aging_detect_label"):
            card._aging_detect_label.configure(text="")

    def _reset_card_display(self, card: Card) -> None:
        self._reset_payload_display(card)
        card._sheet_combo.configure(values=["尚未读取工作表"], state="disabled")
        card._sheet_var.set("尚未读取工作表")

    def _clear_opening(self, card: Card) -> None:
        clear_source_state(self._state, "opening")
        self._opening_mapper = ColumnMapper()
        card._path_var.set("")
        self._reset_card_display(card)

    def _recalculate_filter_summary(self, card: Card, mapper: ColumnMapper) -> None:
        prefix = card._prefix
        df = self._state.get(f"{prefix}_df")
        mapping = mapper.get_mapping()
        if df is None:
            return
        if not mapping.get("科目编码") and not mapping.get("科目名称"):
            text = "请先完成科目编码或科目名称映射"
            self._state[f"{prefix}_filter_summary"] = text
            card._summary_label.configure(text=text, text_color=("#E67E22", "#E67E22"))
            return

        mapped = self._loader.apply_mapping(df, mapping)
        if prefix == "opening":
            amount_columns = ["借方余额", "贷方余额"]
            data_kind = "opening"
            source_name = "期初余额"
        else:
            amount_columns = ["借方金额", "贷方金额"]
            data_kind = "journal"
            source_name = "序时账"
        date_columns = ["日期"] if prefix == "journal" else []
        mapped, type_warnings = self._loader.convert_types(
            mapped, amount_columns=amount_columns, date_columns=date_columns,
        )
        result = filter_current_accounts(
            mapped,
            data_kind=data_kind,
            source_label=f"{source_name}/{self._state.get(f'{prefix}_sheet') or ''}",
            include_receivable_bills=True,
        )
        text = format_filter_summary(result)
        if result.category_counts.get('应收票据',0):
            text += '\n已识别应收票据；是否纳入计算，在第二步勾选。'
        if type_warnings:
            text += "\n数据提示：" + "；".join(type_warnings)
        self._state[f"{prefix}_filter_summary"] = text
        card._summary_label.configure(text=text, text_color=("gray35", "gray70"))

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
            combo = ctk.CTkComboBox(mf, values=columns_with_none, variable=var, width=180,
                                    state="readonly")  # 只读：手输不存在的列名会架空必填校验
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
        self._recalculate_filter_summary(card, mapper)

    def validate(self) -> bool:
        """校验：序时账必选；期初余额可选（不选则期初视为 0），选了才校验期初映射"""
        errors = []
        # 期初余额文件改为可选：不选则期初余额按 0 计算
        if not self._state.get("journal_path"):
            errors.append("请选择序时账文件")

        if self._state.get("opening_path") and not self._state.get("opening_sheet"):
            errors.append("请选择期初余额工作表")
        if self._state.get("journal_path") and not self._state.get("journal_sheet"):
            errors.append("请选择序时账工作表")

        if not errors:
            if self._state.get("opening_path"):
                try:
                    self._opening_mapper.validate_required(
                        REQUIRED_FIELDS["balance"], REQUIRED_ANY_FIELDS["balance"],
                    )
                except ValueError as e:
                    errors.append(f"期初余额：{e}")
            try:
                self._journal_mapper.validate_required(
                    REQUIRED_FIELDS["journal"], REQUIRED_ANY_FIELDS["journal"],
                )
            except ValueError as e:
                errors.append(f"序时账：{e}")

        if errors:
            messagebox.showwarning("校验未通过", "\n".join(errors))
            return False
        return True
