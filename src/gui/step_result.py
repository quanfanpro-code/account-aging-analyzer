# -*- coding: utf-8 -*-
"""步骤 3：计算输出 — 执行计算 + 日志 + 导出"""
from __future__ import annotations
import pandas as pd
import customtkinter as ctk
import queue
import threading
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

from src.gui.widgets import Card, make_button
from src.core.workflow import AgingWorkflow
from src.gui.confirmation_dialog import ConfirmationDialog
from src.gui.票据确认窗口 import BillConfirmationDialog
from src.core.receivable_bills import BillConfirmationRequired
from src.core.report import ReportGenerator
from src.core.data_loader import DataLoader
from src.core.current_accounts import (
    filter_current_accounts,
    find_category_conflicts,
    format_category_conflicts,
)
from src.gui.step_import import format_filter_summary


class StepResult(ctk.CTkFrame):
    """步骤 3：计算 + 日志 + 导出"""

    def __init__(self, master, state: dict):
        super().__init__(master, fg_color="transparent")
        self._state = state
        self._loader = DataLoader()
        self._results: list = []

        # 后台线程只往队列塞消息，主线程用单一 after 泵统一消费（线程安全）
        self._msg_queue: queue.Queue = queue.Queue()
        self.after(100, self._poll_queue)

        self.grid_columnconfigure(0, weight=0)   # 执行列
        self.grid_columnconfigure(1, weight=1)   # 日志列
        self.grid_rowconfigure(0, weight=1)

        # 左列：执行卡片 + 导出卡片
        left_frame = ctk.CTkFrame(self, fg_color="transparent")
        left_frame.grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        left_frame.grid_rowconfigure(0, weight=0)
        left_frame.grid_rowconfigure(1, weight=0)
        left_frame.grid_rowconfigure(2, weight=1)

        self._build_exec_card(left_frame)
        self._build_export_card(left_frame)

        # 右列：日志卡片
        self._build_log_card()

    def invalidate_results(self) -> None:
        """清除旧计算结果（当用户返回前序步骤修改数据/参数时调用）"""
        self._results = []
        self._state["aging_results"] = []
        self._state.pop('calculation_trace', None)
        self._btn_export.configure(state="disabled")
        self._export_status.configure(
            text="（参数已变更，请重新计算）",
            text_color=("gray50", "gray60"),
        )
        self._status_label.configure(text="就绪", text_color=("gray50", "gray60"))
        self._progress.set(0)
        self._stats_label.configure(text="")

    def _build_exec_card(self, parent: ctk.CTkFrame) -> None:
        card = Card(parent, title="执行计算")
        card.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        c = card.content

        # 主按钮
        self._btn_calc = make_button(c, "▶ 开始计算", level="primary", width=140,
                                     command=self._start_calculation)
        self._btn_calc.pack(pady=(8, 8))

        # 进度条
        self._progress = ctk.CTkProgressBar(c, width=200)
        self._progress.set(0)
        self._progress.pack(pady=(0, 4))

        # 状态标签
        self._status_label = ctk.CTkLabel(c, text="就绪", font=ctk.CTkFont(size=12),
                                          text_color=("gray50", "gray60"))
        self._status_label.pack(pady=(0, 8))

        # 统计
        self._stats_label = ctk.CTkLabel(c, text="", font=ctk.CTkFont(size=12))
        self._stats_label.pack(pady=(0, 4))

    def _build_export_card(self, parent: ctk.CTkFrame) -> None:
        card = Card(parent, title="导出审计底稿")
        card.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        c = card.content

        self._btn_export = make_button(c, "📥 导出 Excel", level="secondary", width=140,
                                       command=self._export_excel)
        self._btn_export.pack(pady=(8, 8))
        self._btn_export.configure(state="disabled")

        self._export_status = ctk.CTkLabel(c, text="（计算完成后可导出）",
                                           font=ctk.CTkFont(size=11),
                                           text_color=("gray50", "gray60"))
        self._export_status.pack(pady=(0, 8))

    def _build_log_card(self) -> None:
        card = Card(self, title="计算日志")
        card.grid(row=0, column=1, padx=(6, 0), sticky="nsew")
        c = card.content
        c.grid_rowconfigure(0, weight=1)
        c.grid_columnconfigure(0, weight=1)

        self._log_box = ctk.CTkTextbox(c, font=ctk.CTkFont(family="Consolas", size=12),
                                       fg_color=("#2C3E50", "#0D1B2A"),
                                       text_color=("#ECF0F1", "#ECF0F1"))
        self._log_box.grid(row=0, column=0, sticky="nsew")
        self._log_box.insert("end", "等待开始计算...\n")
        self._log_box.configure(state="disabled")

    def _log(self, msg: str) -> None:
        """向日志框追加一行（线程安全：只往队列塞，主线程泵统一写）"""
        self._msg_queue.put(("log", msg))

    def _poll_queue(self) -> None:
        """主线程消息泵：消费后台线程塞进来的所有界面更新"""
        try:
            while True:
                kind, payload = self._msg_queue.get_nowait()
                if kind == "log":
                    self._log_box.configure(state="normal")
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    self._log_box.insert("end", f"[{timestamp}] {payload}\n")
                    self._log_box.see("end")
                    self._log_box.configure(state="disabled")
                elif kind == "progress":
                    current, total = payload
                    pct = current / total if total > 0 else 1.0
                    self._progress.set(pct)
                    self._status_label.configure(
                        text=f"计算中... {current}/{total}",
                        text_color=("#E67E22", "#E67E22"),
                    )
                elif kind == "stats":
                    self._stats_label.configure(text=payload)
                elif kind == "confirmation":
                    pending, event, answer = payload
                    self._status_label.configure(text="等待计算前确认")
                    def complete(decisions, answer=answer, event=event):
                        answer['decisions'] = decisions
                        event.set()
                    ConfirmationDialog(self, pending, complete, self._state.get('confirmation_decisions'))
                elif kind == "calc_done":
                    self._on_calc_done(payload)
                elif kind == 'bill_confirmation':
                    pending, event, answer = payload
                    self._status_label.configure(text='等待票据计龄口径确认')
                    def complete_bills(decisions,answer=answer,event=event):
                        answer['decisions']=decisions;event.set()
                    BillConfirmationDialog(self,pending,complete_bills)
                elif kind == "calc_error":
                    messagebox.showerror("计算失败", f"{payload}\n详情见右侧计算日志")
                elif kind == "export_done":
                    self._state["is_exporting"] = False
                    self._log(f"✅ 审计底稿已导出: {payload}")
                    self._export_status.configure(
                        text=f"已导出: {Path(payload).name}", text_color=("#27AE60", "#27AE60"))
                    self._btn_export.configure(state="normal", text="📥 导出 Excel")
                    messagebox.showinfo("导出成功", f"审计底稿已保存至：\n{payload}")
                elif kind == "export_error":
                    self._state["is_exporting"] = False
                    self._log(f"❌ 导出失败: {payload}")
                    self._btn_export.configure(state="normal", text="📥 导出 Excel")
                    messagebox.showerror("导出失败", f"{payload}\n详情见右侧计算日志")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _start_calculation(self) -> None:
        """在新线程中执行计算（避免卡 GUI）"""
        # 禁用按钮
        self._state["is_computing"] = True
        self._btn_calc.configure(state="disabled", text="计算中...")
        self._btn_export.configure(state="disabled")
        self._progress.set(0)
        self._status_label.configure(text="计算中...", text_color=("#E67E22", "#E67E22"))
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

        thread = threading.Thread(target=self._run_calculation, daemon=True)
        thread.start()

    def _run_calculation(self) -> None:
        """实际计算逻辑（后台线程）"""
        try:
            self._log("===== 开始往来账款账龄分析 =====")
            self._log(f"截止日期: {self._state['cutoff_date']}")
            self._log(f"账龄分档: {self._state['buckets']}")
            self._log("处理口径: 计算前确认、反向余额自动重分类、成对对抵后输出唯一最终账龄")
            self._log(f"期初模式: {'分档模式' if self._state.get('opening_aging_columns') else '铁板模式'}")

            # 加载并清洗期初余额（可选：不选时按空表、期初视为 0）
            opening_df = self._state.get("opening_df")
            if opening_df is None:
                self._log("ℹ️ 未选择期初余额，期初余额按 0 计算")
                opening_df = pd.DataFrame(columns=["科目编码", "科目名称", "明细名称", "借方余额", "贷方余额"])
            else:
                opening_df = self._loader.apply_mapping(opening_df, self._state.get("opening_mapping", {}))
                opening_df, open_warnings = self._loader.convert_types(
                    opening_df, amount_columns=["借方余额", "贷方余额"]
                )
                for w in open_warnings:
                    self._log(f"⚠️ {w}")

            # 加载并清洗序时账
            journal_df = self._state.get("journal_df")
            if journal_df is None:
                self._log("❌ 序时账数据未加载，请返回步骤 1")
                self._msg_queue.put(("calc_done", False))
                return

            journal_df = self._loader.apply_mapping(journal_df, self._state.get("journal_mapping", {}))
            journal_df, journal_warnings = self._loader.convert_types(
                journal_df,
                amount_columns=["借方金额", "贷方金额"],
                date_columns=["日期"],
            )
            for w in journal_warnings:
                self._log(f"⚠️ {w}")

            opening_result = filter_current_accounts(
                opening_df,
                data_kind="opening",
                source_label=f"期初余额/{self._state.get('opening_sheet') or '(无期初)'}",
                include_receivable_bills=self._state.get('include_receivable_bills',False),
            )
            journal_result = filter_current_accounts(
                journal_df,
                data_kind="journal",
                source_label=f"序时账/{self._state.get('journal_sheet') or '(未选择)'}",
                include_receivable_bills=self._state.get('include_receivable_bills',False),
            )
            for title, filter_result in (("期初余额", opening_result), ("序时账", journal_result)):
                self._log(f"--- {title}过滤结果 ---")
                for line in format_filter_summary(filter_result).splitlines():
                    self._log(line)
                for warning in filter_result.warnings:
                    self._log(f"⚠️ {warning}")

            conflicts = find_category_conflicts([opening_result, journal_result])
            if conflicts:
                raise ValueError(format_category_conflicts(conflicts))
            if opening_result.retained_rows + journal_result.retained_rows == 0:
                raise ValueError("所选数据中未识别到本次纳入的往来科目")
            opening_df = opening_df.copy()
            journal_df = journal_df.copy()
            opening_df['_来源工作表'] = f"{self._state.get('opening_path') or '(无期初)'} | {self._state.get('opening_sheet') or ''}"
            journal_df['_来源工作表'] = f"{self._state.get('journal_path') or ''} | {self._state.get('journal_sheet') or ''}"
            pending = AgingWorkflow.preflight(opening_df, journal_df)
            input_signature = (
                id(self._state.get('opening_df')), id(self._state.get('journal_df')),
                self._state.get('opening_sheet'), self._state.get('journal_sheet'),
                tuple(sorted(self._state.get('opening_mapping', {}).items())),
                tuple(sorted(self._state.get('journal_mapping', {}).items())),
            )
            if self._state.get('confirmation_input_signature') != input_signature:
                self._state.pop('confirmation_decisions', None)
                self._state.pop('bill_decisions',None)
            decisions = {'temporary': {}, 'names': {}}
            cached = self._state.get('confirmation_decisions', {})
            cache_complete = (
                all(x.code in cached.get('temporary', {}) for x in pending.temporary)
                and all(x.key in cached.get('names', {}) for x in pending.names)
            )
            if cached and cache_complete:
                decisions = cached
                self._log('同一批资料复用已确认的科目归属及名称关系')
            elif pending.temporary or pending.names:
                event = threading.Event()
                answer = {}
                self._msg_queue.put(('confirmation', (pending, event, answer)))
                event.wait()
                decisions = answer.get('decisions')
                if decisions is None:
                    self._log('用户取消计算前确认，本次未执行账龄计算')
                    self._msg_queue.put(('calc_done', False))
                    return
                self._state['confirmation_decisions'] = decisions
                self._state['confirmation_input_signature'] = input_signature

            # 批量计算
            def on_progress(current: int, total: int) -> None:
                self._msg_queue.put(("progress", (current, total)))

            # 是否启用分档模式由自动检测结果决定；期初日期无论是否分档都可用于精确期初账龄。
            opening_aging_columns = self._state.get("opening_aging_columns", {})
            opening_date = self._state.get("opening_date")

            orch = AgingWorkflow(
                cutoff_date=self._state["cutoff_date"],
                buckets=self._state["buckets"],
                on_progress=on_progress,
                opening_date=opening_date,
                opening_aging_columns=opening_aging_columns,
            )

            self._log("开始 FIFO 账龄计算...")
            bill_decisions=list(self._state.get('bill_decisions',[]))
            while True:
                try:
                    results = orch.run(opening_df, journal_df,
                        temporary_assignments=decisions['temporary'], name_decisions=decisions['names'],
                        include_receivable_bills=self._state.get('include_receivable_bills',False),
                        bill_decisions=bill_decisions)
                    break
                except BillConfirmationRequired as error:
                    event=threading.Event();answer={}
                    self._msg_queue.put(('bill_confirmation',(error.candidates,event,answer)))
                    event.wait()
                    if answer.get('decisions') is None:
                        self._log('已取消票据口径确认，本次未完成计算')
                        self._msg_queue.put(('calc_done',False));return
                    bill_decisions.extend(answer['decisions'])
                    self._state['bill_decisions']=bill_decisions
            self._state['confirmation_input_signature']=input_signature
            self._state['calculation_trace'] = {
                'source_results': orch.source_results,
                'confirmation_records': orch.confirmation_records,
                'transfer_records': orch.transfer_records,
                'reclassification_records': orch.reclassification_records,
                'offset_records': orch.offset_records,
                'opening_source': orch.opening_input,
                'journal_source': orch.journal_input,
                'bill_transfer_records': orch.bill_transfer_records,
                'bill_policy_records': orch.bill_policy_records,
            }
            for warning in getattr(orch, "last_warnings", []):
                self._log(f"⚠️ {warning}")
            self._log(f"✅ 计算完成！共 {len(results)} 个账龄明细")

            # 输出方向判断日志
            for log_line in getattr(orch, "last_direction_log", []):
                self._log(f"  {log_line}")

            # 统计
            assets = sum(r.closing_balance for r in results if r.direction == 'debit')
            liabilities = sum(r.closing_balance for r in results if r.direction == 'credit')
            self._log(f"最终资产类余额: {assets:,.2f}；最终负债类余额: {liabilities:,.2f}")

            self._state["aging_results"] = results
            self._results = results

            # 更新统计标签
            stats_text = f"明细数: {len(results)}\n资产: {assets:,.2f}\n负债: {liabilities:,.2f}"
            self._msg_queue.put(("stats", stats_text))

            self._msg_queue.put(("calc_done", True))

        except Exception as e:
            # traceback 完整保留在日志框；弹窗只给一行人话
            self._log(f"❌ 计算异常:\n{traceback.format_exc()}")
            first_line = str(e).strip().splitlines()[0] if str(e).strip() else "未知错误"
            self._msg_queue.put(("calc_error", f"计算出错了：{first_line}"))
            self._msg_queue.put(("calc_done", False))

    def _on_calc_done(self, success: bool) -> None:
        """计算完成后的 GUI 更新（由主线程消息泵调用）"""
        self._state["is_computing"] = False
        self._btn_calc.configure(state="normal", text="▶ 开始计算")
        if success:
            self._progress.set(1.0)
            self._status_label.configure(text="✅ 计算完成", text_color=("#27AE60", "#27AE60"))
            self._btn_export.configure(state="normal")
            self._export_status.configure(text="点击按钮导出审计底稿 Excel")
        else:
            self._status_label.configure(text="❌ 计算失败", text_color=("#E74C3C", "#E74C3C"))
            self._btn_export.configure(state="disabled")

    def _export_excel(self) -> None:
        """导出 Excel 审计底稿"""
        if not self._results and not self._state.get('calculation_trace'):
            messagebox.showwarning("无数据", "请先完成计算再导出")
            return

        path = filedialog.asksaveasfilename(
            title="导出审计底稿",
            defaultextension=".xlsx",
            filetypes=[("Excel 文件", "*.xlsx")],
            initialfile=f"往来账款账龄审计底稿_{self._state['cutoff_date']}.xlsx",
        )
        if not path:
            return

        # 禁用导出按钮防止重复点击
        self._state["is_exporting"] = True
        self._btn_export.configure(state="disabled", text="导出中...")
        self._log(f"正在导出到: {path} ...")

        threading.Thread(target=self._do_export, args=(path,), daemon=True).start()

    def _do_export(self, path: str) -> None:
        """后台线程执行导出（界面更新只往队列塞消息）"""
        try:
            gen = ReportGenerator()
            gen.generate(
                output_path=path,
                aging_results=self._results,
                config={
                    "cutoff_date": self._state["cutoff_date"],
                    "buckets": self._state["buckets"],
                    "bucket_labels": self._state.get("bucket_labels"),
                    "opening_date": self._state.get("opening_date"),
                    "aging_mode": "分档模式" if self._state.get("opening_aging_columns") else "铁板模式",
                    "bucket_boundary_rule": "边界点归前档",
                    "fifo_policy": "先进先出法 (收付款按最老余额优先核销)",
                    "direction_policy": "反向余额自动转入成对科目，按转入方向追溯账龄",
                    "negative_balance_policy": "反向余额自动重分类，并保留重分类记录",
                    **self._state.get('calculation_trace', {}),
                },
            )
            self._msg_queue.put(("export_done", path))
        except Exception as e:
            self._log(f"❌ 导出异常:\n{traceback.format_exc()}")
            first_line = str(e).strip().splitlines()[0] if str(e).strip() else "未知错误"
            self._msg_queue.put(("export_error", f"导出失败了：{first_line}"))
