# -*- coding: utf-8 -*-
"""GUI 应用主窗口 — 三步向导式"""
from __future__ import annotations
import customtkinter as ctk
from pathlib import Path
from typing import Optional
from tkinter import messagebox

from src.gui.widgets import StepIndicator, Card, make_button
from src.gui.step_import import StepImport
from src.gui.step_config import StepConfig
from src.gui.step_result import StepResult


class MainWindow(ctk.CTk):
    """三步向导主窗口：导入数据 → 配置参数 → 计算输出"""

    def __init__(self):
        super().__init__()
        self.title("往来账款账龄分析工具")
        self.geometry("1100x780")
        self.minsize(900, 650)

        # 外观
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # 共享状态
        self._shared_state: dict = {
            "opening_path": None,       # 期初余额文件路径
            "journal_path": None,       # 序时账文件路径
            "opening_sheet_names": [],  # 期初余额工作表列表
            "journal_sheet_names": [],  # 序时账工作表列表
            "opening_sheet": None,      # 用户选定的期初余额工作表
            "journal_sheet": None,      # 用户选定的序时账工作表
            "opening_request_id": 0,    # 防止旧读取结果覆盖新选择
            "journal_request_id": 0,
            "opening_filter_summary": "",
            "journal_filter_summary": "",
            "opening_mapping": {},      # 期初余额列映射
            "journal_mapping": {},      # 序时账列映射
            "opening_df": None,         # 期初余额 DataFrame
            "journal_df": None,         # 序时账 DataFrame
            "buckets": [(0, 90), (90, 180), (180, 365), (365, 730), (730, 9999)],
            "cutoff_date": None,
            "aging_results": [],
            "is_computing": False,
            "is_exporting": False,
        }
        self._current_step = 0

        # 计算/导出进行中关窗时拦截确认
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---- 主 grid 布局 ----
        self.grid_rowconfigure(0, weight=0)   # 页眉
        self.grid_rowconfigure(1, weight=0)   # 步骤指示条
        self.grid_rowconfigure(2, weight=1)   # 内容区
        self.grid_rowconfigure(3, weight=0)   # 导航按钮
        self.grid_columnconfigure(0, weight=1)

        # 页眉卡片
        self._build_header()

        # 步骤指示条
        self._step_indicator = StepIndicator(self)
        self._step_indicator.grid(row=1, column=0, padx=20, pady=(0, 8), sticky="ew")

        # 步骤内容容器
        self._content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._content_frame.grid(row=2, column=0, padx=20, pady=(0, 8), sticky="nsew")
        self._content_frame.grid_rowconfigure(0, weight=1)
        self._content_frame.grid_columnconfigure(0, weight=1)

        # 三个步骤页面
        self._step1 = StepImport(self._content_frame, self._shared_state)
        self._step2 = StepConfig(self._content_frame, self._shared_state)
        self._step3 = StepResult(self._content_frame, self._shared_state)

        # 全部放在 grid (0,0)，用 raise 切换
        self._step1.grid(row=0, column=0, sticky="nsew")
        self._step2.grid(row=0, column=0, sticky="nsew")
        self._step3.grid(row=0, column=0, sticky="nsew")

        # 底部导航
        self._build_nav()

        # 显示步骤 1
        self._show_step(0)

    def _build_header(self) -> None:
        """页眉卡片：标题 + 副标题 + 主题切换"""
        header = ctk.CTkFrame(self, corner_radius=0, fg_color=("#2C3E50", "#0F3460"))
        header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)

        title = ctk.CTkLabel(
            header, text="往来账款账龄分析工具",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#FFFFFF",
        )
        title.pack(side="left", padx=24, pady=(14, 0))

        subtitle = ctk.CTkLabel(
            header, text="FIFO 先进先出法 · 审计底稿自动生成",
            font=ctk.CTkFont(size=13),
            text_color="#BDC3C7",
        )
        subtitle.pack(side="left", padx=(8, 24), pady=(16, 0))

        # 主题切换
        theme_btn = ctk.CTkSegmentedButton(
            header,
            values=["☀ 亮色", "🌙 暗色"],
            command=self._on_theme_change,
            fg_color=("#BDC3C7", "#2C3E50"),
            selected_color=("#3498DB", "#3498DB"),
            text_color=("#2C3E50", "#ECF0F1"),
        )
        theme_btn.set("☀ 亮色")
        theme_btn.pack(side="right", padx=24, pady=(14, 0))

    def _on_theme_change(self, value: str) -> None:
        """切换亮色/暗色主题"""
        if "暗" in value:
            ctk.set_appearance_mode("dark")
        else:
            ctk.set_appearance_mode("light")

    def _build_nav(self) -> None:
        """底部导航：[上一步] 弱按钮  ...  [下一步] 次按钮"""
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.grid(row=3, column=0, padx=20, pady=(0, 12), sticky="ew")
        nav_frame.grid_columnconfigure(0, weight=1)
        nav_frame.grid_columnconfigure(1, weight=0)
        nav_frame.grid_columnconfigure(2, weight=0)

        self._btn_prev = make_button(nav_frame, "← 上一步", level="weak", command=self._on_prev)
        self._btn_prev.grid(row=0, column=0, sticky="w")

        self._btn_next = make_button(nav_frame, "下一步 →", level="secondary", command=self._on_next)
        self._btn_next.grid(row=0, column=2, sticky="e")

    def _show_step(self, index: int) -> None:
        """显示第 index 步"""
        self._current_step = index
        self._step_indicator.set_step(index)

        if index == 0:
            self._step1.tkraise()
            self._btn_prev.configure(state="disabled", text="← 上一步")
            self._btn_next.configure(text="下一步 →", state="normal")
            # 从步骤 3 返回步骤 1 时，清除旧计算结果
            if hasattr(self, '_step3'):
                self._step3.invalidate_results()
        elif index == 1:
            self._step2.tkraise()
            self._step2.refresh()  # 从 shared_state 刷新显示
            self._btn_prev.configure(state="normal", text="← 上一步")
            self._btn_next.configure(text="下一步 →", state="normal")
            # 从步骤 3 返回步骤 2 时，清除旧计算结果
            if hasattr(self, '_step3'):
                self._step3.invalidate_results()
        elif index == 2:
            self._step3.tkraise()
            self._btn_prev.configure(state="normal", text="← 上一步")
            self._btn_next.configure(text="下一步 →", state="disabled")

    def _on_prev(self) -> None:
        if self._shared_state.get("is_computing"):
            messagebox.showwarning("计算进行中", "请等待当前计算完成后再切换步骤")
            return
        if self._current_step > 0:
            self._show_step(self._current_step - 1)

    def _on_close(self) -> None:
        """关窗保护：计算/导出进行中先确认，避免后台线程写一半文件"""
        if self._shared_state.get("is_computing") or self._shared_state.get("is_exporting"):
            if not messagebox.askyesno(
                "任务进行中",
                "计算或导出还在进行中，现在关闭可能导致结果不完整。\n确定要退出吗？",
            ):
                return
        self.destroy()

    def _on_next(self) -> None:
        if self._shared_state.get("is_computing"):
            messagebox.showwarning("计算进行中", "请等待当前计算完成后再切换步骤")
            return
        if self._current_step < 2:
            # 校验当前步骤
            if self._current_step == 0:
                if not self._step1.validate():
                    return
            elif self._current_step == 1:
                if not self._step2.validate():
                    return
            self._show_step(self._current_step + 1)


def run_app() -> int:
    """启动 GUI 应用"""
    app = MainWindow()
    app.mainloop()
    return 0
