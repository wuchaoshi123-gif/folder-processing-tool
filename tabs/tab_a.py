# tabs/tab_a.py
"""A 菜单：文件夹名称清洗与重命名
★ v3 合并优化版:
  - A-2/A-3/A-4 合并为一次扫描 + 一次 rename（3 倍提速）
  - 线程数默认 4（降低 NTFS 目录锁争用）
  - 线程数可在界面调整
"""
import random
import string
import tkinter as tk
from datetime import datetime
from tkinter import ttk, messagebox

from core.task import Task
from core.preview_table import PreviewTable
from core.concurrent import run_concurrent
from core.utils import (list_target_folders, clean_folder_name,
                        strip_underscore_prefix, rename_item, move_folder)
from .base_tab import BaseTab


class TabA(BaseTab):
    TAB_NAME = "A 名称清洗"
    TAB_KEY = "A"

    DEFAULT_WORKERS = 4
    UI_REFRESH_BATCH = 200

    def _build_ui(self):
        left = ttk.Frame(self, padding=6)
        left.pack(side="left", fill="y")

        ttk.Label(left, text="一键处理",
                  font=("", 11, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(left, text="A1 → 名称清洗\n自动串行 + 多线程并发",
                  foreground="#666", justify="left").pack(anchor="w", pady=(0, 8))

        # ★ 线程数选择
        wk_box = ttk.Frame(left)
        wk_box.pack(fill="x", pady=(0, 6))
        ttk.Label(wk_box, text="线程数:").pack(side="left")
        self.workers_var = tk.StringVar(value=str(self.DEFAULT_WORKERS))
        ttk.Spinbox(wk_box, from_=1, to=16, width=5,
                    textvariable=self.workers_var).pack(side="left", padx=4)
        ttk.Label(wk_box, text="(SSD 建议 4, HDD 建议 2)",
                  foreground="#888", font=("", 8)).pack(side="left")

        self.run_btn = ttk.Button(left, text="▶  一键处理", width=22,
                                   command=self.run_all)
        self.run_btn.pack(fill="x", pady=4)

        ttk.Separator(left, orient="h").pack(fill="x", pady=8)
        ttk.Button(left, text="✖  清空预览", width=22,
                   command=lambda: self.table.clear()).pack(fill="x", pady=2)
        ttk.Separator(left, orient="h").pack(fill="x", pady=8)

        info = (
            "处理顺序:\n"
            "  ① 移动🈴 → 集合\n"
            "  ② 名称清洗（一次完成）\n"
            "       加后缀\n"
            "     + 去 _ 前缀\n"
            "     + 清洗非法字符\n"
            "\n"
            "颜色区分:\n"
            "  ■ 蓝  A-1 移动\n"
            "  ■ 黄  A-2 清洗\n"
            "  ■ 红  失败行"
        )
        ttk.Label(left, text=info, foreground="#444",
                  font=("Consolas", 8), justify="left").pack(
            anchor="w", pady=(4, 0))

        right = ttk.Frame(self, padding=(0, 6, 6, 6))
        right.pack(side="left", fill="both", expand=True)
        self.table = PreviewTable(right)
        self.table.pack(fill="both", expand=True)

        self.hint_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.hint_var,
                  foreground="#804000", font=("Consolas", 9),
                  wraplength=900, justify="left").pack(anchor="w", pady=(4, 0))

    # ============ 线程数 ============
    def _get_workers(self):
        try:
            return max(1, min(16, int(self.workers_var.get())))
        except (ValueError, AttributeError):
            return self.DEFAULT_WORKERS

    # ============ A-1: 移动🈴 ============
    def _build_a1(self):
        tasks = []
        for f in list_target_folders(self.target_dir):
            if "🈴" in f:
                tasks.append(Task("A-1", f, f))
        print(f"▶ A-1 发现 {len(tasks)} 个带 🈴 的文件夹")
        return tasks

    # ============ ★ A-2/3/4 合并：一次扫描 + 一次 rename ============
    def _build_a234(self):
        """
        合并原 A-2/A-3/A-4：
          原始名 f
            → 加 4 字母后缀:    f + " " + suffix
            → 去 _ 及之前:      strip_underscore_prefix
            → 清洗非法字符:     clean_folder_name
            → 最终名 final
        只有 final != f 时才生成任务
        """
        tasks = []
        seen = set()   # 防止同批次内重名

        for f in list_target_folders(self.target_dir):
            # 步骤 2: 加后缀
            suffix = "".join(random.choices(string.ascii_lowercase, k=4))
            step = f"{f} {suffix}"

            # 步骤 3: 去 _ 及之前
            stripped = strip_underscore_prefix(step)
            if stripped:
                step = stripped

            # 步骤 4: 清洗
            cleaned = clean_folder_name(step)
            if cleaned:
                step = cleaned

            final = step

            # 防重名（极端情况兜底）
            base_final = final
            n = 1
            while final in seen:
                n += 1
                final = f"{base_final} {n}"
            seen.add(final)

            if final != f:
                tasks.append(Task("A-2", f, final))

        print(f"▶ A-2 发现 {len(tasks)} 个待清洗的文件夹")
        return tasks

    # ============ 一键执行 ============
    def run_all(self):
        if not self.ensure_dir():
            return
        if not messagebox.askyesno(
            "确认",
            "将按顺序处理所有子文件夹:\n"
            "  ① 移动带🈴 的文件夹到【000000集合】\n"
            "  ② 名称清洗（加后缀 + 去 _ 前缀 + 清洗）\n"
            "\n"
            "包含重命名操作，请确保已备份重要文件。\n\n确定继续?"
        ):
            return

        workers = self._get_workers()
        self.run_btn.config(state="disabled")
        self.table.clear()
        self.hint_var.set("")
        self.set_status(f"A 模块: 开始处理 (线程数 {workers})...")
        self.app.root.update_idletasks()

        start_time = datetime.now()
        logger = self.make_logger()

        stages = [
            ("A-1", "① 移动🈴 到集合", self._build_a1),
            ("A-2", "② 名称清洗", self._build_a234),
        ]

        total_ok = total_skip = total_err = 0
        stage_stats = []

        try:
            for stage_type, stage_label, build_fn in stages:
                self.set_status(f"A 模块: {stage_label} - 扫描中...")
                self.app.root.update_idletasks()

                try:
                    tasks = build_fn()
                except Exception as e:
                    self.hint_var.set(
                        self.hint_var.get() + f"\n⚠️ {stage_label} 扫描失败: {e}")
                    continue

                self.table.add_header(
                    f"══ {stage_label}  ({len(tasks)} 条) ══")

                if not tasks:
                    self.set_status(f"A 模块: {stage_label} - 无任务,跳过")
                    self.app.root.update_idletasks()
                    stage_stats.append((stage_label, 0, 0, 0))
                    continue

                base_idx = len(self.table.tasks)
                self.table.append_tasks_batch(tasks, auto_scroll=False)
                self.app.root.update_idletasks()

                self.set_status(
                    f"A 模块: {stage_label} - 并发执行中 "
                    f"({len(tasks)} 条, {workers} 线程)...")
                self.app.root.update_idletasks()

                indexed = list(enumerate(tasks))

                def progress_cb(done, total):
                    if done % 100 == 0 or done == total:
                        self.set_status(
                            f"A 模块: {stage_label} 进度 {done}/{total}")

                results = run_concurrent(
                    indexed, self._execute_one,
                    max_workers=workers,
                    progress_cb=progress_cb,
                )

                ok = skip = err = 0
                for k, (idx_in_stage, task, status, msg) in enumerate(results, 1):
                    task.status = status
                    task.message = msg
                    logger.log(task)
                    self.table.update_task_at(base_idx + idx_in_stage, task)
                    if status == "success":
                        ok += 1
                    elif status == "skip":
                        skip += 1
                    else:
                        err += 1
                    if k % self.UI_REFRESH_BATCH == 0:
                        self.app.root.update_idletasks()

                self.app.root.update_idletasks()

                stage_stats.append((stage_label, ok, skip, err))
                total_ok += ok
                total_skip += skip
                total_err += err

                self.set_status(
                    f"A 模块: {stage_label} 完成 ✔{ok} ⏭{skip} ✖{err}")
                self.app.root.update_idletasks()

        finally:
            self.run_btn.config(state="normal")

        json_path, _ = logger.save("A")

        elapsed = (datetime.now() - start_time).total_seconds()
        summary = [f"处理完成,耗时 {elapsed:.1f} 秒", "─" * 40]
        for name, ok, skip, err in stage_stats:
            summary.append(f"  {name}  成功 {ok}  跳过 {skip}  失败 {err}")
        summary.append("─" * 40)
        summary.append(
            f"  合计    成功 {total_ok}  跳过 {total_skip}  失败 {total_err}")
        summary.append(f"  线程数  {workers}")

        self.hint_var.set("\n".join(summary))
        self.set_status(
            f"A 模块: 完成 ✔{total_ok} ⏭{total_skip} ✖{total_err}")

        messagebox.showinfo(
            "A 模块处理完成",
            "\n".join(summary) + "\n\n"
            f"报告已保存:\n"
            f"{json_path.parent if json_path else self.target_dir / '_logs'}"
        )
        self.refresh_reports()

    # ============ 单任务执行 ============
    def _execute_one(self, task):
        t = task.type
        if t == "A-1":
            collect = self.target_dir.parent / "000000集合"
            collect.mkdir(exist_ok=True)
            return move_folder(self.target_dir / task.old,
                               collect / task.new)
        if t == "A-2":
            return rename_item(self.target_dir / task.old,
                               self.target_dir / task.new)
        return "error", "未知任务类型"