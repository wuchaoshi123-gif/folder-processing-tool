# tabs/tab_c.py
"""
C 菜单：图片批量处理（一键处理 + 归档 + 重命名）
  · 阶段①: 一次遍历完成 图片处理 + 归档（合并，不再独立归档）
  · 阶段②: 归档目录子文件夹名 去空格
"""
import os
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from tkinter import ttk, messagebox
import tkinter as tk

from core.task import Task
from core.preview_table import PreviewTable
from core.fs_executor import process_folder, rename_archive_sub
from core.utils import list_target_folders
from .base_tab import BaseTab


class TabC(BaseTab):
    TAB_NAME = "C 图片处理"
    TAB_KEY = "C"

    MIN_WORKERS = 1
    MAX_WORKERS = 12
    DEFAULT_WORKERS = 6      # ★ 默认 6 进程（本地盘最佳）
    CHUNK_SIZE = 200         # ★ 每块 200（减少 IPC）

    # ==========================================================
    #                     UI 构建
    # ==========================================================
    def _build_ui(self):
        cpu = multiprocessing.cpu_count()

        left = ttk.Frame(self, padding=6)
        left.pack(side="left", fill="y")

        ttk.Label(left, text="一键处理",
                  font=("", 11, "bold")).pack(anchor="w", pady=(0, 4))
        ttk.Label(left, text="处理+归档 一步完成",
                  foreground="#666", justify="left").pack(anchor="w", pady=(0, 8))

        wk_box = ttk.Frame(left)
        wk_box.pack(fill="x", pady=(0, 6))
        ttk.Label(wk_box, text="执行进程:").pack(side="left")
        self.workers_var = tk.StringVar(value=str(self.DEFAULT_WORKERS))
        ttk.Spinbox(wk_box, from_=self.MIN_WORKERS, to=self.MAX_WORKERS,
                    increment=1, textvariable=self.workers_var,
                    width=6).pack(side="left", padx=4)

        self.run_btn = ttk.Button(left, text="▶  一键处理", width=22,
                                   command=self.run_all)
        self.run_btn.pack(fill="x", pady=4)

        ttk.Separator(left, orient="h").pack(fill="x", pady=8)
        ttk.Button(left, text="✖  清空预览", width=22,
                   command=lambda: self.table.clear()).pack(fill="x", pady=2)
        ttk.Separator(left, orient="h").pack(fill="x", pady=8)

        info = (
            "内部流程:\n"
            "  ① 处理+归档（一步完成）\n"
            "     jpeg→jpg  删0010~0090\n"
            "     去0      保留1-9\n"
            "     立即归档到 9image/6image/Z000image\n"
            "  ② 归档目录子文件夹去空格\n"
            "\n"
            "性能:\n"
            f"  · CPU 核数: {cpu}\n"
            f"  · 默认进程: {self.DEFAULT_WORKERS}\n"
            f"  · 分块: {self.CHUNK_SIZE}\n"
            "\n"
            "颜色:\n"
            "  ■ 蓝  ① 处理+归档\n"
            "  ■ 紫  ② 重命名\n"
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
                  wraplength=900, justify="left").pack(
            anchor="w", pady=(4, 0))

    # ==========================================================
    def _get_workers(self):
        try:
            return max(self.MIN_WORKERS,
                       min(self.MAX_WORKERS, int(self.workers_var.get())))
        except (ValueError, AttributeError):
            return self.DEFAULT_WORKERS

    # ==========================================================
    #                     一键执行
    # ==========================================================
    def run_all(self):
        if not self.ensure_dir():
            return
        if not messagebox.askyesno(
            "确认",
            "将处理所有子文件夹图片:\n"
            "  ① 处理图片 (jpeg→jpg / 删0010~0090 / 去0 / 保留1-9)\n"
            "  ② 立即归档到 9image / 6image / Z000image\n"
            "  ③ 归档目录子文件夹去空格\n\n"
            "包含删除操作，请确保已备份重要文件。\n\n确定继续?"
        ):
            return

        workers = self._get_workers()
        self.run_btn.config(state="disabled")
        self.table.clear()
        self.hint_var.set("")
        self.set_status(f"C 模块: 开始（{workers} 进程）...")
        self.app.root.update_idletasks()

        start = datetime.now()
        logger = self.make_logger()
        target = str(self.target_dir)

        stats = {
            "s1": {"ok": 0, "skip": 0, "err": 0},
            "s2": {"ok": 0, "skip": 0, "err": 0},
        }

        try:
            # ================================================
            # 阶段1: 处理 + 归档（一步完成）
            # ================================================
            t0 = datetime.now()
            subs = list_target_folders(self.target_dir)
            total_subs = len(subs)
            print(f"\n▶ 扫描到 {total_subs} 个子文件夹")

            self.table.add_header(
                f"══ ① 处理+归档  ({total_subs} 个文件夹) ══")
            base_idx = len(self.table.tasks)

            # 预插行
            for sub in subs:
                self.table.append_task(Task("C-1", sub, ""))
            self.app.root.update_idletasks()

            self.set_status(
                f"① 处理+归档 ({total_subs} 文件夹, {workers} 进程)...")
            self.app.root.update_idletasks()

            stage1_results = self._run_parallel(
                fn=process_folder,
                args_list=[(target, sub) for sub in subs],
                workers=workers,
                base_idx=base_idx,
                logger=logger,
                label="① 处理+归档",
                packer=self._pack_stage1,
            )
            stats["s1"] = stage1_results["counts"]
            scan_sec = (datetime.now() - t0).total_seconds()
            print(f"   [① 处理+归档 {scan_sec:.2f}s, "
                  f"✔{stats['s1']['ok']} ⏭{stats['s1']['skip']} ✖{stats['s1']['err']}]")

            # ================================================
            # 阶段2: 归档目录子文件夹名 去空格
            # ================================================
            rename_items = []
            for arch in ("9image", "6image", "Z000image"):
                arch_path = self.target_dir / arch
                if not arch_path.exists():
                    continue
                try:
                    with os.scandir(arch_path) as it:
                        for entry in it:
                            try:
                                if entry.is_dir(follow_symlinks=False):
                                    rename_items.append((arch, entry.name))
                            except OSError:
                                continue
                except OSError:
                    continue

            if rename_items:
                self.table.add_header(
                    f"══ ② 归档重命名  ({len(rename_items)} 个文件夹) ══")
                base_idx = len(self.table.tasks)

                for arch, sub in rename_items:
                    new_sub = sub.replace(" ", "-")
                    while "--" in new_sub:
                        new_sub = new_sub.replace("--", "-")
                    new_sub = new_sub.strip("-")
                    self.table.append_task(
                        Task("C-6", f"{arch}/{sub}", f"{arch}/{new_sub}"))
                self.app.root.update_idletasks()

                self.set_status(
                    f"② 重命名中 ({len(rename_items)} 文件夹, {workers} 进程)...")
                self.app.root.update_idletasks()

                stage2_results = self._run_parallel(
                    fn=rename_archive_sub,
                    args_list=[(target, arch, sub)
                               for arch, sub in rename_items],
                    workers=workers,
                    base_idx=base_idx,
                    logger=logger,
                    label="② 重命名",
                    packer=self._pack_simple,
                )
                stats["s2"] = stage2_results["counts"]
                print(f"   [② 重命名 ✔{stats['s2']['ok']} "
                      f"⏭{stats['s2']['skip']} ✖{stats['s2']['err']}]")

        finally:
            self.run_btn.config(state="normal")

        json_path, _ = logger.save("C")

        # ================================================
        # 汇总
        # ================================================
        elapsed = (datetime.now() - start).total_seconds()
        ok_total = sum(s["ok"] for s in stats.values())
        skip_total = sum(s["skip"] for s in stats.values())
        err_total = sum(s["err"] for s in stats.values())

        summary = [
            f"处理完成,耗时 {elapsed:.1f} 秒",
            "─" * 45,
            f"① 处理+归档  ✔{stats['s1']['ok']}  "
            f"⏭{stats['s1']['skip']}  ✖{stats['s1']['err']}",
            f"② 重命名     ✔{stats['s2']['ok']}  "
            f"⏭{stats['s2']['skip']}  ✖{stats['s2']['err']}",
            "─" * 45,
            f"合计        ✔{ok_total}  ⏭{skip_total}  ✖{err_total}",
            f"执行进程    {workers}",
        ]
        self.hint_var.set("\n".join(summary))
        self.set_status(
            f"C 模块: 完成 ✔{ok_total} ⏭{skip_total} ✖{err_total}")
        messagebox.showinfo(
            "C 模块处理完成",
            "\n".join(summary) + "\n\n"
            f"报告已保存:\n"
            f"{json_path.parent if json_path else self.target_dir / '_logs'}"
        )
        self.refresh_reports()

    # ==========================================================
    #               通用并行执行
    # ==========================================================
    def _run_parallel(self, fn, args_list, workers, base_idx,
                      logger, label, packer):
        total = len(args_list)
        if total == 0:
            return {"counts": {"ok": 0, "skip": 0, "err": 0}, "raw": []}

        ok = skip = err = 0
        raw_results = []
        done = 0

        with ProcessPoolExecutor(max_workers=workers) as ex:
            for result in ex.map(fn, args_list, chunksize=self.CHUNK_SIZE):
                raw_results.append(result)
                status, msg = packer(result)

                if status == "success":
                    ok += 1
                elif status == "skip":
                    skip += 1
                else:
                    err += 1

                idx = base_idx + done
                if idx < len(self.table.tasks):
                    task = self.table.tasks[idx]
                    task.status = status
                    task.message = msg
                    logger.log(task)
                    self.table.update_task_at(idx, task)

                done += 1
                if done % 200 == 0 or done == total:
                    self.set_status(
                        f"{label} {done}/{total}  "
                        f"(✔{ok} ⏭{skip} ✖{err})")
                    self.app.root.update_idletasks()

        return {
            "counts": {"ok": ok, "skip": skip, "err": err},
            "raw": raw_results,
        }

    # ==========================================================
    #               结果打包为 (status, msg)
    # ==========================================================
    @staticmethod
    def _pack_stage1(result):
        """(sub, ok, skip, err, final_count, category) → (status, msg)"""
        sub, ok, sk, er, cnt, cat = result
        total = ok + sk + er
        if total == 0:
            return "skip", "无图片"
        if er > 0 and ok == 0:
            return "error", f"✖{er} 失败"
        if er > 0:
            return "error", f"✔{ok} ⏭{sk} ✖{er} → {cat}"
        return "success", f"✔{ok} ⏭{sk} 保留{cnt}张 → {cat}"

    @staticmethod
    def _pack_simple(result):
        """(sub, status, msg)"""
        _, status, msg = result
        return status, msg