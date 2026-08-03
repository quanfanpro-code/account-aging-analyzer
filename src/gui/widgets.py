# -*- coding: utf-8 -*-
"""GUI 复用控件：步骤指示条、卡片容器"""
from __future__ import annotations
import customtkinter as ctk
from typing import Optional, Callable


class StepIndicator(ctk.CTkFrame):
    """三步向导指示条：①导入数据 → ②配置参数 → ③计算输出"""

    STEPS = ["① 导入数据", "② 配置参数", "③ 计算输出"]

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._labels: list[ctk.CTkLabel] = []
        self._current = 0

        for i, text in enumerate(self.STEPS):
            lbl = ctk.CTkLabel(
                self, text=text,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#BDC3C7",
                padx=20,
            )
            lbl.pack(side="left", padx=(0 if i == 0 else 10, 10))
            self._labels.append(lbl)
            if i < len(self.STEPS) - 1:
                arrow = ctk.CTkLabel(
                    self, text="→",
                    font=ctk.CTkFont(size=14),
                    text_color="#BDC3C7",
                )
                arrow.pack(side="left")

        self.set_step(0)

    def set_step(self, index: int, step_color: str = "#3498DB",
                 done_color: str = "#27AE60", inactive_color: str = "#BDC3C7") -> None:
        """设置当前步骤，之前的为完成态，之后的为非活跃态"""
        self._current = index
        for i, lbl in enumerate(self._labels):
            if i < index:
                lbl.configure(text_color=done_color)
            elif i == index:
                lbl.configure(text_color=step_color)
            else:
                lbl.configure(text_color=inactive_color)


class Card(ctk.CTkFrame):
    """卡片容器 — 统一圆角、边距、背景"""

    def __init__(self, master, title: str = "", **kwargs):
        super().__init__(
            master,
            corner_radius=12,
            border_width=1,
            border_color="#E0E0E0",
            fg_color=("gray95", "gray17"),
            **kwargs,
        )
        self._title_label: Optional[ctk.CTkLabel] = None
        if title:
            self._title_label = ctk.CTkLabel(
                self, text=title,
                font=ctk.CTkFont(size=15, weight="bold"),
                anchor="w",
            )
            self._title_label.pack(fill="x", padx=16, pady=(12, 8))
        self._content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._content_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    @property
    def content(self) -> ctk.CTkFrame:
        return self._content_frame


def make_button(
    master,
    text: str,
    level: str = "secondary",
    command: Optional[Callable] = None,
    **kwargs,
) -> ctk.CTkButton:
    """按三级体系创建按钮

    level: "primary" | "secondary" | "weak"
    """
    if level == "primary":
        defaults = dict(
            fg_color="#3498DB", hover_color="#2980B9",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=42, corner_radius=8,
        )
    elif level == "secondary":
        defaults = dict(
            fg_color="#27AE60", hover_color="#219A52",
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=13),
            height=34, corner_radius=8,
        )
    else:  # weak
        defaults = dict(
            fg_color="transparent", hover_color=("gray85", "gray25"),
            text_color=("gray40", "gray70"),
            border_width=1, border_color=("gray60", "gray40"),
            font=ctk.CTkFont(size=13),
            height=34, corner_radius=8,
        )
    defaults.update(kwargs)
    btn = ctk.CTkButton(master, text=text, command=command, **defaults)
    return btn
