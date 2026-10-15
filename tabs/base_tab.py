# tabs/base_tab.py
"""Tab 基类，提供通用能力（支持多线程并发执行）"""
import time
from tkinter import ttk, messagebox

from core.logger import OperationLogger
from core.concurrent import run_concurrent


class BaseTab(ttk.Frame):
    TAB_NAME = "?"
    TAB_KEY = "?"
    DEFAULT_WORKERS = 8   # 默认并发线程数

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build_ui()

    # ---------- 子类必须实现 ----------
    def _build_ui(self):
        raise NotImplementedError

    def _execute_one(self, task):
        raise NotImplementedError

    # ---------- 便捷属性/方法 ----------
    @property
    def target_dir(self):
        return self.app.target_dir

    def ensure_dir(self):
        return self.app.ensure_dir()

    def set_status(self, msg):
        # ★ 只在文本真的变化时更新
        try:
            if self.app.status_var.get() == msg:
                return
        except Exception:
            pass
        self.app.status_var.set(msg)

    def make_logger(self):
        return OperationLogger(self.target_dir)

    def refresh_reports(self):
        self.app.refresh_reports()

    # ==========================================================
    #             通用执行：支持串行 / 多线程并发
    # ==========================================================
    def process_table(self, table, delay=0.05, module_key=None,
                      ask=True, max_workers=None):
        """
        执行表格里选中的任务

        max_workers:
          - None  -> 使用 self.DEFAULT_WORKERS
          - 1     -> 串行执行（保留 delay 间隔）
          - >1    -> 多线程并发执行（delay 失效）
        """
        if max_workers is None:
            max_workers = self.DEFAULT_WORKERS

        to_run = [(i, t) for i, t in table.get_checked_tasks()
                  if t.status not in ("success", "skip")]

        if not to_run:
            messagebox.showinfo("提示", "没有可执行的任务（未勾选或已执行）")
            return None

        if max_workers > 1:
            confirm_msg = (f"将执行 {len(to_run)} 个任务\n"
                           f"并发线程数: {max_workers}\n\n确定继续?")
        else:
            confirm_msg = f"将执行 {len(to_run)} 个任务，确定继续?"

        if ask and not messagebox.askyesno("确认执行", confirm_msg):
            return None

        logger = self.make_logger()
        ok = skip = err = 0

        if max_workers > 1:
            # ============ 并发执行 ============
            self.set_status(
                f"并发执行中 ({len(to_run)} 条, {max_workers} 线程)...")

            def progress_cb(done, total):
                self.set_status(f"执行中 {done}/{total}...")
                # 保持 UI 响应
                self.app.root.update_idletasks()

            results = run_concurrent(
                to_run, self._execute_one,
                max_workers=max_workers,
                progress_cb=progress_cb,
            )

            # 主线程回填结果 & 写日志
            for idx, task, status, msg in results:
                task.status = status
                task.message = msg
                logger.log(task)
                table.update_task_at(idx, task)

                if status == "success":
                    ok += 1
                elif status == "skip":
                    skip += 1
                else:
                    err += 1

            self.app.root.update_idletasks()

        else:
            # ============ 串行执行（保留 delay） ============
            for idx, task in to_run:
                status, msg = self._execute_one(task)
                task.status = status
                task.message = msg
                logger.log(task)
                table.update_task_at(idx, task)
                self.app.root.update_idletasks()
                if delay > 0:
                    time.sleep(delay)
                if status == "success":
                    ok += 1
                elif status == "skip":
                    skip += 1
                else:
                    err += 1

        json_path, _ = logger.save(module_key or self.TAB_KEY)

        workers_txt = (f" (并发 {max_workers})"
                       if max_workers > 1 else "")
        self.set_status(
            f"执行完成{workers_txt}: 成功 {ok}, 跳过 {skip}, 失败 {err}")

        messagebox.showinfo(
            "执行完成",
            f"成功: {ok}\n跳过: {skip}\n失败: {err}\n"
            f"并发数: {max_workers}\n\n"
            f"报告已保存到:\n"
            f"{json_path.parent if json_path else self.target_dir / '_logs'}"
        )
        self.refresh_reports()
        return ok, skip, err

    # ==========================================================
    def toggle_all(self, table):
        real_tasks = [t for t in table.tasks if t is not None]
        if not real_tasks:
            return
        all_checked = all(t.checked for t in real_tasks)
        for t in real_tasks:
            t.checked = not all_checked
        table.update_all()