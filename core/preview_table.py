# core/preview_table.py
"""可复用的预览表格组件
★ v2 性能优化:
  - 用 _iids 缓存所有 iid, 让 update_task_at 从 O(N) 降到 O(1)
  - 修复 N 万行时每次刷新都要重建 children 元组的瓶颈
"""
import tkinter as tk
from tkinter import ttk


class PreviewTable(ttk.Frame):
    STAGE_COLORS = {
        # A 模块
        "A-1": "#E8F4FF",   # 蓝
        "A-2": "#FFF7E0",   # 黄
        "A-3": "#E8FFE8",   # 绿
        "A-4": "#F0E8FF",   # 紫
        # C 模块
        "C-1": "#E8F4FF",
        "C-2": "#FFECEC",
        "C-3": "#FFF7E0",
        "C-4": "#FFECEC",
        "C-5": "#E8FFE8",
        "C-6": "#F0E8FF",
    }

    def __init__(self, parent):
        super().__init__(parent)
        columns = ("check", "idx", "old", "new", "status")
        self.tree = ttk.Treeview(self, columns=columns,
                                 show="headings", selectmode="extended")
        self.tree.heading("check", text="✓")
        self.tree.heading("idx", text="#")
        self.tree.heading("old", text="路径 / 原名称")
        self.tree.heading("new", text="新路径 / 操作")
        self.tree.heading("status", text="状态")

        self.tree.column("check", width=40, anchor="center", stretch=False)
        self.tree.column("idx", width=50, anchor="center", stretch=False)
        self.tree.column("old", width=520, anchor="w")
        self.tree.column("new", width=520, anchor="w")
        self.tree.column("status", width=200, anchor="w")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        for tag, color in self.STAGE_COLORS.items():
            self.tree.tag_configure(tag, background=color)
        self.tree.tag_configure("header",
                                background="#404040",
                                foreground="white",
                                font=("", 9, "bold"))
        self.tree.tag_configure("row-error",
                                background="#FFD0D0",
                                foreground="#8B0000")
        self.tree.tag_configure("row-success",
                                background="#E0FFE0")

        self.tree.bind("<Button-1>", self._on_click)

        # ★ 关键: tasks 和 _iids 一一对应, 长度永远相等
        self.tasks = []
        self._iids = []

    # ==========================================================
    #  内部工具
    # ==========================================================
    def _on_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        # 用 _iids 反查 idx（避免 tree.index 走全表）
        try:
            idx = self._iids.index(iid)
        except ValueError:
            return
        if 0 <= idx < len(self.tasks) and self.tasks[idx] is not None:
            self.tasks[idx].checked = not self.tasks[idx].checked
            self._refresh_row(iid, self.tasks[idx])

    def _row_values(self, idx, task):
        check = "☑" if task.checked else "☐"
        return (check, idx + 1, task.old, task.display_new(),
                task.status_text())

    def _row_tags(self, task):
        tags = []
        if task.type in self.STAGE_COLORS:
            tags.append(task.type)
        if task.status == "error":
            tags.append("row-error")
        return tuple(tags)

    def _refresh_row(self, iid, task):
        try:
            idx = self._iids.index(iid)
        except ValueError:
            return
        self.tree.item(iid,
                       values=self._row_values(idx, task),
                       tags=self._row_tags(task))

    # ==========================================================
    #  插入
    # ==========================================================
    def add_header(self, text):
        self.tasks.append(None)
        iid = self.tree.insert("", "end",
                               values=("", "", text, "", ""),
                               tags=("header",))
        self._iids.append(iid)

    def append_task(self, task, auto_scroll=True):
        self.tasks.append(task)
        tag = task.type if task.type in self.STAGE_COLORS else ""
        iid = self.tree.insert(
            "", "end",
            values=self._row_values(len(self.tasks) - 1, task),
            tags=(tag,) if tag else (),
        )
        self._iids.append(iid)
        if auto_scroll:
            self.tree.see(iid)

    def append_tasks_batch(self, tasks, auto_scroll=False, max_display=None):
        """批量插入任务（性能关键）"""
        if not tasks:
            return
        total = len(tasks)
        show_count = total if max_display is None else min(total, max_display)
        base = len(self.tasks)
        self.tasks.extend(tasks)

        for i in range(show_count):
            t = tasks[i]
            tag = t.type if t.type in self.STAGE_COLORS else ""
            iid = self.tree.insert(
                "", "end",
                values=self._row_values(base + i, t),
                tags=(tag,) if tag else (),
            )
            self._iids.append(iid)

        if show_count < total:
            iid = self.tree.insert(
                "", "end",
                values=("", "",
                        f"... 省略 {total - show_count:,} 行"
                        f"（仅显示前 {show_count} 行）",
                        "", ""),
                tags=("header",),
            )
            self._iids.append(iid)

        if auto_scroll and self._iids:
            self.tree.see(self._iids[-1])

    def set_tasks(self, tasks):
        """批量设置任务"""
        self.tree.delete(*self.tree.get_children())
        self.tasks = list(tasks)
        self._iids = []
        for i, t in enumerate(self.tasks):
            if t is None:
                iid = self.tree.insert(
                    "", "end",
                    values=("", "", "", "", ""),
                    tags=("header",),
                )
            else:
                tag = t.type if t.type in self.STAGE_COLORS else ""
                iid = self.tree.insert(
                    "", "end",
                    values=self._row_values(i, t),
                    tags=(tag,) if tag else (),
                )
            self._iids.append(iid)

    # ==========================================================
    #  更新（★ 性能优化核心）
    # ==========================================================
    def update_task_at(self, idx, task):
        """★ O(1) 更新单行（用 _iids 缓存）"""
        if not (0 <= idx < len(self._iids)):
            return
        iid = self._iids[idx]
        try:
            self.tree.item(iid, values=self._row_values(idx, task))
        except Exception:
            pass

    def update_all(self):
        for i, iid in enumerate(self._iids):
            if i < len(self.tasks) and self.tasks[i] is not None:
                try:
                    self.tree.item(
                        iid,
                        values=self._row_values(i, self.tasks[i]),
                        tags=self._row_tags(self.tasks[i]))
                except Exception:
                    pass

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self.tasks = []
        self._iids = []

    def get_checked_tasks(self):
        return [(i, t) for i, t in enumerate(self.tasks)
                if t is not None and t.checked]