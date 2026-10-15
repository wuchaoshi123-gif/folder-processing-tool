#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件夹名称批量化处理工具 v1.0
主入口：仅负责窗口 + Tab 容器

性能优化:
  - confirm_dir 使用 os.scandir 异步统计子文件夹数量,避免数万文件夹时卡顿
"""
import os
import sys
import threading
import multiprocessing
multiprocessing.freeze_support()   # ★ Windows 打包场景需要

from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from config_manager import load_config, update_config
from tabs import TabA, TabB, TabC, TabD, TabE, TabF, TabG

class FolderBatchGUI:
    def __init__(self, root):
        self.root = root
        self.target_dir = None

        cfg = load_config()
        saved_key = (cfg.get("DEEPSEEK_API_KEY", "").strip()
                     or os.environ.get("DEEPSEEK_API_KEY", "").strip())
        if saved_key and not cfg.get("DEEPSEEK_API_KEY", "").strip():
            update_config(DEEPSEEK_API_KEY=saved_key)

        self.dir_var = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪 - 请先选择目标目录")

        last_dir = cfg.get("LAST_TARGET_DIR", "")
        if last_dir and Path(last_dir).is_dir():
            self.dir_var.set(last_dir)
            self.target_dir = Path(last_dir)
            # 启动时也异步统计一次
            threading.Thread(
                target=self._count_subdirs_async,
                args=(self.target_dir,), daemon=True
            ).start()

        self._build_ui()

        if saved_key:
            shown = saved_key[:6] + "..." + saved_key[-4:] if len(saved_key) > 12 else "***"
            self.status_var.set(f"✅ 已自动加载 API Key: {shown}")

    # ==========================================================
    def _build_ui(self):
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)

        top = ttk.Frame(self.root, padding=8)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="目标目录:").pack(side="left")
        ttk.Entry(top, textvariable=self.dir_var).pack(
            side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="浏览...", command=self.choose_dir).pack(side="left")
        ttk.Button(top, text="确认目录", command=self.confirm_dir).pack(
            side="left", padx=4)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=8, pady=6)

        self.tab_a = TabA(self.notebook, self)
        self.tab_b = TabB(self.notebook, self)
        self.tab_c = TabC(self.notebook, self)
        self.tab_d = TabD(self.notebook, self)
        self.tab_e = TabE(self.notebook, self)
        self.tab_f = TabF(self.notebook, self)
        self.tab_g = TabG(self.notebook, self)

        self.notebook.add(self.tab_a, text=f"  {TabA.TAB_NAME}  ")
        self.notebook.add(self.tab_b, text=f"  {TabB.TAB_NAME}  ")
        self.notebook.add(self.tab_c, text=f"  {TabC.TAB_NAME}  ")
        self.notebook.add(self.tab_d, text=f"  {TabD.TAB_NAME}  ")
        self.notebook.add(self.tab_e, text=f"  {TabE.TAB_NAME}  ")
        self.notebook.add(self.tab_f, text=f"  {TabF.TAB_NAME}  ")
        self.notebook.add(self.tab_g, text=f"  {TabG.TAB_NAME}  ")


        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        ttk.Label(self.root, textvariable=self.status_var,
                  relief="sunken", anchor="w", padding=(6, 3)).grid(
            row=2, column=0, sticky="ew")

    def _on_tab_changed(self, event):
        current = self.notebook.nametowidget(self.notebook.select())
        if current is self.tab_d:
            self.tab_d.refresh()

    # ==========================================================
    #              ★ 目录选择（性能优化核心）
    # ==========================================================
    def choose_dir(self):
        path = filedialog.askdirectory(title="选择目标目录")
        if path:
            self.dir_var.set(path)
            self.confirm_dir()

    def confirm_dir(self):
        path = self.dir_var.get().strip().strip('"').strip("'")
        if not path:
            messagebox.showwarning("提示", "请先选择或输入目录路径")
            return False
        p = Path(path)
        if not p.is_dir():
            messagebox.showerror("错误", f"路径不存在或不是目录:\n{path}")
            return False

        self.target_dir = p
        # ★ 立即反馈，不等待统计
        self.status_var.set(f"✅ 目录已确认: {p}  (正在后台统计子文件夹数量...)")
        update_config(LAST_TARGET_DIR=str(p))

        # ★ 后台异步统计，UI 完全不卡
        threading.Thread(
            target=self._count_subdirs_async,
            args=(p,),
            daemon=True,
        ).start()
        return True

    def _count_subdirs_async(self, p):
        """后台线程统计子文件夹数量（os.scandir 加速）"""
        try:
            n = 0
            with os.scandir(p) as it:
                for entry in it:
                    try:
                        # follow_symlinks=False 避免对每个符号链接再 stat
                        if entry.is_dir(follow_symlinks=False):
                            n += 1
                    except OSError:
                        continue
            self.root.after(0, lambda: self._update_dir_status(p, n))
        except Exception:
            self.root.after(0, lambda: self._update_dir_status(p, None))

    def _update_dir_status(self, p, n):
        """回到主线程更新状态栏；若目录已切换则忽略过期结果"""
        if self.target_dir != p:
            return
        if n is None:
            self.status_var.set(f"✅ 目录已确认: {p}")
        else:
            self.status_var.set(f"✅ 目录已确认: {p}  (子文件夹 {n} 个)")

    def ensure_dir(self):
        if self.target_dir and self.target_dir.is_dir():
            return True
        return self.confirm_dir()

    def refresh_reports(self):
        if hasattr(self, "tab_d"):
            self.tab_d.refresh()


# ==================================================================
def main():
    root = tk.Tk()
    root.title("文件夹名称批量化处理工具 v1.0")
    root.geometry("1380x820")
    root.minsize(1100, 650)

    try:
        style = ttk.Style()
        style.theme_use("vista" if sys.platform.startswith("win") else "clam")
    except Exception:
        pass

    FolderBatchGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()