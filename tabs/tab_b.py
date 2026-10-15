# tabs/tab_b.py
"""B 菜单：文件夹名称批量翻译（多线程 API 并发 + 多线程执行重命名）"""
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from core.task import Task
from core.preview_table import PreviewTable
from core.utils import list_target_folders, rename_item
from .base_tab import BaseTab


class TabB(BaseTab):
    TAB_NAME = "B 批量翻译"
    TAB_KEY = "B"

    def _build_ui(self):
        from config_manager import load_config
        cfg = load_config()

        self.api_key_var = tk.StringVar(value=cfg.get("DEEPSEEK_API_KEY", ""))
        self.model_var = tk.StringVar(value=cfg.get("MODEL", "deepseek-chat"))
        self.max_len_var = tk.StringVar(value=str(cfg.get("MAX_TOTAL_LENGTH", 90)))
        self.min_len_var = tk.StringVar(value=str(cfg.get("MIN_TRANSLATED_LENGTH", 15)))
        self.retry_var = tk.StringVar(value=str(cfg.get("RETRY_TIMES", 3)))
        self.delay_var = tk.StringVar(value=str(cfg.get("DELAY", 0.05)))
        self.price_in_var = tk.StringVar(value=str(cfg.get("INPUT_TOKEN_PRICE", 0.00014)))
        self.price_out_var = tk.StringVar(value=str(cfg.get("OUTPUT_TOKEN_PRICE", 0.00028)))
        self.workers_var = tk.StringVar(value="8")
        self.stats_var = tk.StringVar(value="尚未发起翻译请求")
        self.show_key_var = tk.BooleanVar(value=False)

        # ---------- 参数区 ----------
        param_box = ttk.LabelFrame(self, text=" 翻译参数设置 ", padding=8)
        param_box.pack(fill="x", padx=6, pady=(6, 4))

        ttk.Label(param_box, text="API Key:").grid(
            row=0, column=0, sticky="w", pady=3)
        self.key_entry = ttk.Entry(
            param_box, textvariable=self.api_key_var, width=52, show="•")
        self.key_entry.grid(row=0, column=1, columnspan=3, padx=4, sticky="ew")
        ttk.Checkbutton(param_box, text="显示", variable=self.show_key_var,
                        command=self._toggle_key).grid(
            row=0, column=4, sticky="w", padx=4)

        ttk.Label(param_box, text="模型:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Combobox(param_box, textvariable=self.model_var, width=22,
                     values=["deepseek-chat", "deepseek-reasoner"]).grid(
            row=1, column=1, padx=4, sticky="w")

        ttk.Label(param_box, text="并发数:").grid(
            row=1, column=2, sticky="w", padx=(15, 0))
        ttk.Spinbox(param_box, from_=1, to=16, increment=1,
                    textvariable=self.workers_var, width=8).grid(
            row=1, column=3, padx=4, sticky="w")

        ttk.Label(param_box, text="名称最大长度:").grid(
            row=2, column=0, sticky="w", pady=3)
        ttk.Spinbox(param_box, from_=20, to=200, increment=5,
                    textvariable=self.max_len_var, width=10).grid(
            row=2, column=1, padx=4, sticky="w")

        ttk.Label(param_box, text="译文最短长度:").grid(
            row=2, column=2, sticky="w", padx=(15, 0))
        ttk.Spinbox(param_box, from_=1, to=100, increment=1,
                    textvariable=self.min_len_var, width=10).grid(
            row=2, column=3, padx=4, sticky="w")

        ttk.Label(param_box, text="重译次数:").grid(
            row=2, column=4, sticky="w", padx=(15, 0))
        ttk.Spinbox(param_box, from_=0, to=10, increment=1,
                    textvariable=self.retry_var, width=8).grid(
            row=2, column=5, padx=4, sticky="w")

        ttk.Label(param_box, text="重命名延迟(秒):").grid(
            row=3, column=0, sticky="w", pady=3)
        ttk.Spinbox(param_box, from_=0, to=5, increment=0.05,
                    textvariable=self.delay_var, width=10).grid(
            row=3, column=1, padx=4, sticky="w")

        ttk.Label(param_box, text="输入价格(元/千tok):").grid(
            row=3, column=2, sticky="w", padx=(15, 0))
        ttk.Entry(param_box, textvariable=self.price_in_var, width=10).grid(
            row=3, column=3, padx=4, sticky="w")

        ttk.Label(param_box, text="输出价格(元/千tok):").grid(
            row=3, column=4, sticky="w", padx=(15, 0))
        ttk.Entry(param_box, textvariable=self.price_out_var, width=10).grid(
            row=3, column=5, padx=4, sticky="w")
        param_box.columnconfigure(1, weight=1)

        # ---------- 按钮区 ----------
        btn_bar = ttk.Frame(self, padding=(6, 0, 6, 4))
        btn_bar.pack(fill="x")
        self.preview_btn = ttk.Button(
            btn_bar, text="▶  生成翻译预览", width=22, command=self.preview)
        self.preview_btn.pack(side="left", padx=2)

        # ★ 执行任务时启用多线程并发
        ttk.Button(btn_bar, text="✔  执行选中任务", width=22,
                   command=self.execute_selected
                   ).pack(side="left", padx=2)

        ttk.Button(btn_bar, text="☑  全选/全不选", width=20,
                   command=lambda: self.toggle_all(self.table)
                   ).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="✖  清空预览", width=15,
                   command=lambda: self.table.clear()).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="↺  恢复默认参数", width=18,
                   command=self.reset_params).pack(side="left", padx=2)

        body = ttk.Frame(self, padding=(6, 0, 6, 4))
        body.pack(fill="both", expand=True)
        self.table = PreviewTable(body)
        self.table.pack(fill="both", expand=True)

        stats_bar = ttk.Frame(self, padding=(6, 0, 6, 6))
        stats_bar.pack(fill="x")
        ttk.Label(stats_bar, textvariable=self.stats_var,
                  foreground="#004080",
                  font=("Consolas", 10)).pack(anchor="w")

    # ---------- 参数辅助 ----------
    def _toggle_key(self):
        self.key_entry.config(show="" if self.show_key_var.get() else "•")

    def _get_delay(self):
        try:
            return float(self.delay_var.get())
        except ValueError:
            return 0.05

    def _get_workers(self):
        try:
            return max(1, min(16, int(self.workers_var.get())))
        except (ValueError, AttributeError):
            return 8

    def reset_params(self):
        from config_manager import DEFAULT_CONFIG
        self.model_var.set(DEFAULT_CONFIG["MODEL"])
        self.max_len_var.set(str(DEFAULT_CONFIG["MAX_TOTAL_LENGTH"]))
        self.min_len_var.set(str(DEFAULT_CONFIG["MIN_TRANSLATED_LENGTH"]))
        self.retry_var.set(str(DEFAULT_CONFIG["RETRY_TIMES"]))
        self.delay_var.set(str(DEFAULT_CONFIG["DELAY"]))
        self.price_in_var.set(str(DEFAULT_CONFIG["INPUT_TOKEN_PRICE"]))
        self.price_out_var.set(str(DEFAULT_CONFIG["OUTPUT_TOKEN_PRICE"]))
        self.workers_var.set("4")
        self.set_status("已恢复默认翻译参数")

    # ==========================================================
    #                   ★ 执行选中任务（多线程）
    # ==========================================================
    def execute_selected(self):
        """调用基类 process_table，传入界面上的并发数"""
        workers = self._get_workers()
        self.process_table(
            self.table,
            delay=self._get_delay(),
            module_key="B",
            ask=True,
            max_workers=workers,
        )

    # ---------- 预览 ----------
    def preview(self):
        if not self.ensure_dir():
            return
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning("提示", "请填写 DeepSeek API Key")
            return

        try:
            model = self.model_var.get().strip() or "deepseek-chat"
            max_len = int(self.max_len_var.get())
            min_len = int(self.min_len_var.get())
            retry = int(self.retry_var.get())
            delay = float(self.delay_var.get())
            price_in = float(self.price_in_var.get())
            price_out = float(self.price_out_var.get())
            workers = self._get_workers()
        except ValueError as e:
            messagebox.showwarning("参数错误", f"请检查参数格式：{e}")
            return

        if max_len < 20 or max_len > 200:
            messagebox.showwarning("参数错误", "名称最大长度应在 20~200 之间")
            return
        if min_len < 1 or min_len >= max_len:
            messagebox.showwarning("参数错误", "译文最短长度应在 1~最大长度 之间")
            return

        from config_manager import update_config
        update_config(
            DEEPSEEK_API_KEY=api_key,
            MODEL=model,
            MAX_TOTAL_LENGTH=max_len,
            MIN_TRANSLATED_LENGTH=min_len,
            RETRY_TIMES=retry,
            DELAY=delay,
            INPUT_TOKEN_PRICE=price_in,
            OUTPUT_TOKEN_PRICE=price_out,
            LAST_TARGET_DIR=str(self.target_dir),
        )

        folder_names = list_target_folders(self.target_dir)
        if not folder_names:
            messagebox.showinfo("提示", "未发现文件夹")
            return

        self.table.clear()
        self.preview_btn.config(state="disabled")
        self.stats_var.set(f"正在并发翻译 (并发数 {workers})...")
        self.set_status(f"正在批量翻译 {len(folder_names)} 个文件夹...")

        def worker():
            from translator import DeepSeekBatchTranslator
            translator = DeepSeekBatchTranslator(api_key=api_key, model=model)

            def cb(msg):
                self.app.root.after(0, lambda m=msg: self.set_status(m))

            try:
                results = translator.translate_folders(
                    folder_names,
                    max_total_len=max_len,
                    min_translated_len=min_len,
                    retry_times=retry,
                    progress_cb=cb,
                    max_workers=workers,
                    target_dir=self.target_dir,  # ★ 新增
                )
            except Exception as e:
                self.app.root.after(0, lambda err=str(e):
                                    messagebox.showerror("错误", err))
                self.app.root.after(0,
                                    lambda: self.preview_btn.config(state="normal"))
                return

            def add_all():
                for d in results:
                    task = Task("B", d["old"])
                    if d["error"]:
                        task.status = "skip"
                        task.message = d["error"]
                    elif not d["new"] or d["new"] == d["old"]:
                        task.status = "skip"
                        task.message = "无需修改"
                    else:
                        task.new = d["new"]
                    self.table.append_task(task)

                cost_in = translator.total_prompt_tokens / 1000 * price_in
                cost_out = translator.total_completion_tokens / 1000 * price_out
                self.stats_var.set(
                    f"📊 请求 {translator.request_count} 次  |  "
                    f"并发数 {workers}  |  "
                    f"输入 {translator.total_prompt_tokens} tok (¥{cost_in:.4f})  |  "
                    f"输出 {translator.total_completion_tokens} tok (¥{cost_out:.4f})  |  "
                    f"总费用 ¥{cost_in + cost_out:.4f}"
                )
                self.preview_btn.config(state="normal")
                self.set_status(f"翻译完成: {len(results)} 条，勾选后执行")

            self.app.root.after(0, add_all)

        threading.Thread(target=worker, daemon=True).start()

    # ---------- 单任务执行 ----------
    def _execute_one(self, task):
        if task.type == "B":
            return rename_item(self.target_dir / task.old,
                               self.target_dir / task.new)
        return "error", "未知任务类型"