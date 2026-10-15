# tabs/tab_d.py
"""D 菜单：历史操作报告查看（失败记录红色高亮）"""
import os
import sys
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from .base_tab import BaseTab


class TabD(BaseTab):
    TAB_NAME = "D 历史报告"
    TAB_KEY = "D"

    def _build_ui(self):
        left = ttk.Frame(self, padding=6)
        left.pack(side="left", fill="y")

        ttk.Label(left, text="报告列表:").pack(anchor="w")
        self.report_listbox = tk.Listbox(left, width=45, height=22)
        self.report_listbox.pack(fill="y", expand=True, pady=4)
        self.report_listbox.bind("<<ListboxSelect>>", self._on_report_select)

        ttk.Button(left, text="刷新", command=self.refresh).pack(
            fill="x", pady=2)
        ttk.Button(left, text="打开日志目录",
                   command=self._open_log_dir).pack(fill="x", pady=2)

        # 图例
        legend = ttk.LabelFrame(left, text="图例", padding=6)
        legend.pack(fill="x", pady=(8, 0))
        for color, text in (
            ("red", "❌ 失败记录"),
            ("#008000", "✅ 成功记录"),
            ("#888888", "⏭️ 跳过记录"),
            ("#004080", "📄 标题/统计"),
        ):
            lbl = ttk.Label(legend, text=text, foreground=color,
                            font=("Consolas", 9))
            lbl.pack(anchor="w")

        right = ttk.Frame(self, padding=(0, 6, 6, 6))
        right.pack(side="left", fill="both", expand=True)
        self.report_text = ScrolledText(right, wrap="word",
                                         font=("Consolas", 10),
                                         background="#fafafa")
        self.report_text.pack(fill="both", expand=True)

        # ★ 文本 tag 配置
        self.report_text.tag_config(
            "error",
            foreground="#8B0000",
            background="#FFE0E0",
            font=("Consolas", 10, "bold"),
        )
        self.report_text.tag_config(
            "success",
            foreground="#006400",
            font=("Consolas", 10),
        )
        self.report_text.tag_config(
            "skip",
            foreground="#808080",
            font=("Consolas", 10),
        )
        self.report_text.tag_config(
            "heading",
            foreground="#004080",
            font=("Consolas", 11, "bold"),
        )
        self.report_text.tag_config(
            "summary",
            foreground="#404040",
            font=("Consolas", 10, "bold"),
        )

    def _execute_one(self, task):
        return "skip", "D 模块无任务执行"

    # ---------- 报告刷新 ----------
    def refresh(self):
        if not self.target_dir:
            return
        log_dir = self.target_dir / "_logs"
        self.report_listbox.delete(0, "end")
        self._report_files = []
        if log_dir.exists():
            files = sorted(log_dir.glob("*_report.md"), reverse=True)
            self._report_files = files
            for f in files:
                self.report_listbox.insert("end", f.name)

    def _on_report_select(self, event):
        sel = self.report_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._report_files):
            return
        path = self._report_files[idx]
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            content = f"读取失败: {e}"
        self._render_with_tags(content)

    def _render_with_tags(self, content):
        """按行解析并以不同颜色渲染"""
        w = self.report_text
        w.delete("1.0", "end")

        for line in content.split("\n"):
            tag = None
            # 判断优先级：失败 > 成功 > 跳过 > 标题 > 摘要
            if "❌" in line or "✖" in line or "失败：" in line or "失败 " in line:
                tag = "error"
            elif line.startswith("#"):
                tag = "heading"
            elif "✅" in line or "✔" in line:
                tag = "success"
            elif "⏭" in line or "跳过：" in line:
                tag = "skip"
            elif line.startswith("|") and "失败" in line:
                tag = "summary"
            elif line.startswith("**"):
                tag = "heading"

            if tag:
                w.insert("end", line + "\n", (tag,))
            else:
                w.insert("end", line + "\n")

        # 滚动到顶部
        w.see("1.0")

    def _open_log_dir(self):
        if not self.target_dir:
            return
        log_dir = self.target_dir / "_logs"
        log_dir.mkdir(exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(log_dir))
            elif sys.platform == "darwin":
                os.system(f'open "{log_dir}"')
            else:
                os.system(f'xdg-open "{log_dir}"')
        except Exception:
            pass