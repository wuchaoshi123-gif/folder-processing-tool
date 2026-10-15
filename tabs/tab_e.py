# tabs/tab_e.py
"""
E 菜单：数据入库
★ v3 新增:
  - 顶部 E1/E2 模式切换
    · E1 读取入库：从 描述.txt 提取尺码（跳过 OCR）
    · E2 扫描入库：原 OCR 流程
  - 模式持久化到 config.json
"""
import os
import re
import time
import json
import threading
import multiprocessing
import tkinter as tk
from pathlib import Path
from datetime import datetime
from tkinter import ttk, messagebox, filedialog
from concurrent.futures import (ThreadPoolExecutor, ProcessPoolExecutor,
                                 as_completed)

from core.task import Task
from core.preview_table import PreviewTable
from core.brand_manager import BrandManager
from core.price_extractor import extract_price
from core.db_manager import DBManager
from core.data_exporter import export_local_url_txt
from .base_tab import BaseTab


class TabE(BaseTab):
    TAB_NAME = "E 数据入库"
    TAB_KEY = "E"

    # ---------- 并发参数 ----------
    SCAN_WORKERS = 16
    TRANSLATE_WORKERS = 8
    EXPORT_WORKERS = 8
    OCR_THREADS = 16
    OCR_PROCESSES = 6
    OCR_CHUNK_SIZE = 50
    E1_READ_WORKERS = 16   # ★ E1 读描述.txt 的线程数

    # ==========================================================
    #                       UI 构建
    # ==========================================================
    def _build_ui(self):
        self.hint_var = tk.StringVar(value="")

        from config_manager import load_config
        cfg = load_config()

        # ==========================================================
        #  ★ 模式切换（E1 读取入库 / E2 扫描入库）
        # ==========================================================
        mode_box = ttk.LabelFrame(self, text=" 入库模式 ", padding=6)
        mode_box.pack(fill="x", padx=6, pady=(6, 4))

        self.mode_var = tk.StringVar(value=cfg.get("E_IMPORT_MODE", "E2"))

        ttk.Radiobutton(
            mode_box,
            text="E1 读取入库（从 描述.txt 读取尺码）",
            variable=self.mode_var, value="E1",
            command=self._on_mode_change,
        ).pack(side="left", padx=6)

        ttk.Radiobutton(
            mode_box,
            text="E2 扫描入库（OCR 识别尺码）",
            variable=self.mode_var, value="E2",
            command=self._on_mode_change,
        ).pack(side="left", padx=6)

        self.mode_hint_var = tk.StringVar(value="")
        ttk.Label(mode_box, textvariable=self.mode_hint_var,
                  foreground="#004080",
                  font=("Consolas", 9, "bold")).pack(side="left", padx=15)

        self.app.root.after(100, self._on_mode_change)

        # ---------- 参数区 ----------
        param_box = ttk.LabelFrame(self, text=" 参数设置 ", padding=8)
        param_box.pack(fill="x", padx=6, pady=(6, 4))

        # 域名
        ttk.Label(param_box, text="图片服务器域名:").grid(
            row=0, column=0, sticky="w", pady=3)
        self.domain_var = tk.StringVar(value=cfg.get(
            "IMG_DOMAIN", "http://img.ywzt.org"))
        ttk.Entry(param_box, textvariable=self.domain_var,
                  width=42).grid(row=0, column=1, columnspan=3,
                                 padx=4, sticky="ew")

        # 数据库路径
        ttk.Label(param_box, text="数据库路径:").grid(
            row=1, column=0, sticky="w", pady=3)
        self.db_var = tk.StringVar(value=cfg.get(
            "DB_PATH", str(Path.cwd() / "data" / "products.db")))
        ttk.Entry(param_box, textvariable=self.db_var,
                  width=42).grid(row=1, column=1, columnspan=2,
                                 padx=4, sticky="ew")
        ttk.Button(param_box, text="浏览",
                   command=self._choose_db).grid(row=1, column=3, padx=4)

        # 品牌文档目录
        ttk.Label(param_box, text="品牌文档目录:").grid(
            row=2, column=0, sticky="w", pady=3)
        self.brand_dir_var = tk.StringVar(value=cfg.get(
            "BRAND_DIR", str(Path.cwd() / "data")))
        ttk.Entry(param_box, textvariable=self.brand_dir_var,
                  width=42).grid(row=2, column=1, columnspan=2,
                                 padx=4, sticky="ew")
        ttk.Button(param_box, text="浏览",
                   command=self._choose_brand_dir).grid(
            row=2, column=3, padx=4)

        # OCR 引擎状态
        ttk.Label(param_box, text="OCR 引擎:").grid(
            row=4, column=0, sticky="w", pady=3)
        self.ocr_status_var = tk.StringVar(value="未检测")
        ttk.Label(param_box, textvariable=self.ocr_status_var,
                  foreground="#004080",
                  font=("Consolas", 9, "bold")).grid(
            row=4, column=1, columnspan=2, sticky="w", padx=4)

        # 翻译线程数
        ttk.Label(param_box, text="翻译线程数:").grid(
            row=4, column=2, sticky="w", padx=(15, 0))
        self.trans_workers_var = tk.StringVar(value=str(self.TRANSLATE_WORKERS))
        ttk.Spinbox(param_box, from_=1, to=32,
                    textvariable=self.trans_workers_var,
                    width=6).grid(row=4, column=3, sticky="w", padx=4)

        # 翻译开关
        self.translate_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(param_box, text="翻译成俄语",
                        variable=self.translate_var).grid(
            row=5, column=0, sticky="w", pady=3)

        param_box.columnconfigure(1, weight=1)

        # ---------- 按钮区 ----------
        btn_bar = ttk.Frame(self, padding=(6, 0, 6, 4))
        btn_bar.pack(fill="x")

        self.scan_btn = ttk.Button(
            btn_bar, text="▶  扫描预览", width=15, command=self.scan_preview)
        self.scan_btn.pack(side="left", padx=2)

        self.run_btn = ttk.Button(
            btn_bar, text="✔  执行入库", width=15, command=self.run_import)
        self.run_btn.pack(side="left", padx=2)

        self.retry_btn = ttk.Button(
            btn_bar, text="🔄  二次识别", width=15,
            command=self.run_retry_batch)
        self.retry_btn.pack(side="left", padx=2)

        ttk.Button(btn_bar, text="🔍 检测 OCR 引擎", width=15,
                   command=self._check_ocr_engine).pack(side="left", padx=2)

        ttk.Button(btn_bar, text="✖ 清空", width=10,
                   command=lambda: self.table.clear()).pack(side="left", padx=2)

        ttk.Button(btn_bar, text="📊 数据库统计", width=14,
                   command=self.show_db_stats).pack(side="left", padx=2)

        # 提示文本
        self.retry_info_var = tk.StringVar(value="")
        ttk.Label(btn_bar, textvariable=self.retry_info_var,
                  foreground="#804000",
                  font=("Consolas", 9, "bold")).pack(side="left", padx=10)

        # ---------- 表格 ----------
        body = ttk.Frame(self, padding=(6, 0, 6, 4))
        body.pack(fill="both", expand=True)
        self.table = PreviewTable(body)
        self.table.pack(fill="both", expand=True)

        # ---------- 底部状态 ----------
        ttk.Label(self, textvariable=self.hint_var,
                  foreground="#804000", font=("Consolas", 9),
                  justify="left").pack(anchor="w", padx=8, pady=(0, 6))

        # ★ 启动时【不检测】OCR 引擎，避免卡顿
        #   检测时机：
        #     · 用户点击"🔍 检测 OCR 引擎"
        #     · 用户切换到 E2 模式
        self._ocr_checked = False  # 是否已检测过

    # ==========================================================
    def _on_mode_change(self):
        """模式切换时更新提示并保存到配置"""
        mode = self.mode_var.get()
        if mode == "E1":
            self.mode_hint_var.set(
                "💡 从每个文件夹的 描述.txt 读取尺码，跳过 OCR")
            # E1 不依赖 OCR，不检测
        else:
            self.mode_hint_var.set(
                "💡 使用 OCR 识别图片尺码（原流程）")
            # ★ E2 需要 OCR：若尚未检测，则触发一次（异步）
            if not getattr(self, "_ocr_checked", False):
                self.app.root.after(100, self._check_ocr_engine)

        try:
            from config_manager import update_config
            update_config(E_IMPORT_MODE=mode)
        except Exception:
            pass

    def _ensure_dir(self):
        """兼容别名：调用基类的 ensure_dir"""
        return self.ensure_dir()

    # ==========================================================
    #                       辅助方法
    # ==========================================================
    def _choose_db(self):
        p = filedialog.asksaveasfilename(
            defaultextension=".db",
            filetypes=[("SQLite DB", "*.db"), ("All", "*.*")])
        if p:
            self.db_var.set(p)

    def _choose_brand_dir(self):
        p = filedialog.askdirectory()
        if p:
            self.brand_dir_var.set(p)

    def _check_ocr_engine(self):
        """检测 OCR 引擎状态（后台线程）
        ★ 加 _ocr_checked 标记，避免重复触发加载
        """
        if getattr(self, "_ocr_checked", False):
            return

        self._ocr_checked = True
        self.ocr_status_var.set("检测中（首次加载约 3~30 秒）...")

        def worker():
            try:
                from core.e_pipeline import get_backend_info
                info = get_backend_info()
            except Exception as e:
                info = f"检测失败: {str(e)[:60]}"
                print(f"❌ OCR 检测异常: {e}")

            self.app.root.after(
                0, lambda i=info: self.ocr_status_var.set(i))

        threading.Thread(target=worker, daemon=True).start()

    def _set_ocr_status(self, info):
        self.ocr_status_var.set(info)

    def _update_progress_safe(self, text):
        """安全更新进度"""
        self.app.root.after(0, lambda: self.set_status(text))

    def _ui_sync(self, fn, timeout=30):
        """在 Tk 主线程同步执行 fn 并等待返回（子线程专用）"""
        done = threading.Event()
        box = {}

        def wrapper():
            try:
                box["value"] = fn()
            except Exception as e:
                box["error"] = e
            finally:
                done.set()

        self.app.root.after(0, wrapper)
        if not done.wait(timeout):
            raise TimeoutError("UI 同步超时")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    # ==========================================================
    #                       扫描预览
    # ==========================================================
    def scan_preview(self):
        if not self.ensure_dir():
            return
        t0 = time.time()
        groups = self._scan_groups()
        dt = time.time() - t0

        tasks = []
        for g in groups:
            tasks.append(Task("E", g["onlymulu"], f"{g['images']} 图",
                              extra={"images": g["images"]}))
        self.table.set_tasks(tasks)
        self.set_status(f"扫描完成: {len(groups)} 组, 耗时 {dt:.2f}s")
        self.hint_var.set(
            f"共 {len(groups)} 组产品, 扫描耗时 {dt:.2f}s\n"
            f"点击【执行入库】开始处理")

    def _scan_groups(self):
        """三级并行扫描（★ scandir + break）"""
        target = self.target_dir
        target_str = str(target)
        print(f"\n🔍 扫描根目录: {target_str}")

        t_start = time.time()

        # ============================================
        # 一级: 找 AP 目录
        # ============================================
        ap_dirs = []
        target_name = target.name

        try:
            with os.scandir(target) as it:
                for e in it:
                    if re.match(r"^AP\d+image$", e.name, re.IGNORECASE):
                        ap_dirs.append((e.name, e.path))
        except OSError as e:
            print(f"   ❌ {e}")
            return []

        if not ap_dirs and re.match(r"^AP\d+image$", target_name, re.IGNORECASE):
            ap_dirs = [(target_name, target_str)]
        if not ap_dirs:
            ap_dirs = [(target_name, target_str)]

        t1 = time.time()
        print(f"   [① 一级 {t1 - t_start:.2f}s, {len(ap_dirs)} 个 AP]")

        # ============================================
        # 二级: 列出产品子目录
        # ============================================
        def list_products(ap_info):
            ap_name, ap_path = ap_info
            subs = []
            try:
                with os.scandir(ap_path) as it:
                    for e in it:
                        if e.is_dir(follow_symlinks=False):
                            subs.append((ap_name, e.name, e.path))
            except OSError:
                pass
            return subs

        all_subs = []
        with ThreadPoolExecutor(max_workers=16) as ex:
            for sub_list in ex.map(list_products, ap_dirs):
                all_subs.extend(sub_list)

        t2 = time.time()
        print(f"   [② 二级 {t2 - t1:.2f}s, {len(all_subs)} 个产品]")

        # ============================================
        # 三级: scandir + break（数到 15 个就停）
        # ============================================
        def scan_product(sub_info):
            ap_name, product_name, product_path = sub_info
            imgs = []
            try:
                with os.scandir(product_path) as it:
                    for e in it:
                        name = e.name
                        lower = name.lower()
                        if lower.endswith(".jpg") or lower.endswith(".jpeg"):
                            imgs.append(name)
                            if len(imgs) >= 15:
                                break
            except OSError:
                pass

            def _k(x):
                stem = x.rsplit(".", 1)[0]
                return int(stem) if stem.isdigit() else 9999
            imgs.sort(key=_k)

            return {
                "ap_name": ap_name,
                "product": product_name,
                "onlymulu": f"{ap_name}\\{product_name}",
                "local_dir": product_path,
                "images": imgs,
                "image_count": len(imgs),
            }

        groups = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            for g in ex.map(scan_product, all_subs, chunksize=100):
                groups.append(g)

        t3 = time.time()
        print(f"   [③ 三级 {t3 - t2:.2f}s, {len(groups)} 组]")
        print(f"   ✓ 总耗时 {t3 - t_start:.2f}s")

        if not groups:
            print(f"   ⚠️ 扫描为空")

        return groups

    # ==========================================================
    #                       执行入库（主流程）
    # ==========================================================
    def run_import(self):
        if not self.ensure_dir():
            return

        mode = self.mode_var.get()
        if mode == "E1":
            step3 = "  3. 读取 描述.txt 提取尺码（E1）"
        else:
            step3 = "  3. 3A 整图 OCR（E2）"

        if not messagebox.askyesno(
            "确认",
            f"将开始数据入库流程 ({mode}):\n"
            "  1. 扫描本地图片\n"
            "  2. 品牌识别 + 英文名提取\n"
            f"{step3}\n"
            "  4. 翻译俄语（仅成功项）\n"
            "  5. 写入数据库\n"
            "  6. 保存失败队列\n"
            "  7. 导出 txt\n\n"
            "确定继续?"):
            return

        from config_manager import update_config
        update_config(
            IMG_DOMAIN=self.domain_var.get().strip(),
            DB_PATH=self.db_var.get().strip(),
            BRAND_DIR=self.brand_dir_var.get().strip(),
            E_IMPORT_MODE=mode,
        )

        self.run_btn.config(state="disabled")
        self.scan_btn.config(state="disabled")
        self.retry_btn.config(state="disabled")

        def worker():
            try:
                self._import_worker()
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                err_msg = str(e)
                self.app.root.after(
                    0,
                    lambda msg=err_msg, t=tb: messagebox.showerror(
                        "错误", f"{msg}\n\n{t[:800]}")
                )
            finally:
                self.app.root.after(
                    0, lambda: self.run_btn.config(state="normal"))
                self.app.root.after(
                    0, lambda: self.scan_btn.config(state="normal"))
                self.app.root.after(
                    0, lambda: self.retry_btn.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _import_worker(self):
        """主处理流程"""
        prepared = []
        ocr_results = {}
        rufanyi_map = {}
        timings = {}

        domain = self.domain_var.get().strip().rstrip("/")
        db_path = self.db_var.get().strip()
        brand_dir = self.brand_dir_var.get().strip()
        trans_workers = max(1, int(self.trans_workers_var.get() or 8))
        do_translate = self.translate_var.get()
        mode = self.mode_var.get()

        t_all = time.time()

        # ==========================================================
        #  阶段① 扫描
        # ==========================================================
        t0 = time.time()
        self.set_status("① 扫描目录...")
        groups = self._scan_groups()
        timings["① 扫描"] = time.time() - t0

        total = len(groups)
        if total == 0:
            self.app.root.after(0, lambda: messagebox.showinfo(
                "提示", "未找到产品目录"))
            return

        print(f"\n{'=' * 60}")
        print(f"▶ 模式: {mode}  扫描到 {total} 组产品")
        print(f"   [① 扫描 {timings['① 扫描']:.2f}s]")
        print(f"{'=' * 60}")

        # ==========================================================
        #  阶段② 构建 prepared
        # ==========================================================
        t0 = time.time()
        self.set_status("② 提取品牌/价格/URL/英文名...")

        bm = BrandManager(brand_dir)
        print(f"   品牌文档: {bm.debug_info()}")

        from core.ru_translator import EnToRuTranslator

        for idx, g in enumerate(groups, 1):
            images = g["images"]
            if not images:
                continue

            product = g["product"]
            onlymulu = g["onlymulu"]
            ap_name = g["ap_name"]
            local_dir = g["local_dir"]

            local_urls = [os.path.join(local_dir, img) for img in images]
            web_urls = [f"{domain}/{ap_name}/{product}/{img}"
                        for img in images]

            chuprice = extract_price(product)
            brand, sizechart, matched = bm.identify(product)
            banma = bm.get_banma(brand)

            englishname = EnToRuTranslator.clean_english_name(product)

            first_img = None
            for img in images:
                if img == "1.jpg":
                    first_img = os.path.join(local_dir, img)
                    break
            if not first_img:
                first_img = local_urls[0]

            prepared.append({
                "idx": idx,
                "onlymulu": onlymulu,
                "ap_name": ap_name,
                "product": product,
                "englishname": englishname,
                "local_dir": local_dir,
                "local_urls": local_urls,
                "web_urls": web_urls,
                "images": len(images),
                "chuprice": chuprice,
                "brand": brand,
                "sizechart": sizechart,
                "banma": banma,
                "first_img": first_img,
            })

        timings["② 品牌/URL"] = time.time() - t0
        print(f"   [② 品牌/URL {timings['② 品牌/URL']:.2f}s, "
              f"{len(prepared)} 组待 OCR]")

        # ==========================================================
        #  阶段③ 分流: E1 描述.txt / E2 OCR
        # ==========================================================
        t0 = time.time()
        ocr_results = {}
        stage_a_fail = []
        stage_a_ok = 0
        failed_path = None

        if mode == "E1":
            # ---------- E1 读取入库 ----------
            self.set_status("③-E1 读取 描述.txt 提取尺码...")

            from core.desc_size_parser import parse_sizes_from_desc

            total_e1 = len(prepared)

            self.table.add_header(
                f"══ ③-E1 读取尺码 ({total_e1} 组) ══")
            base_idx = len(self.table.tasks)
            self.table.append_tasks_batch(
                [Task("C-1", p["onlymulu"], "") for p in prepared],
                auto_scroll=False,
                max_display=2000,
            )
            self.app.root.update_idletasks()

            def _read_one(p):
                try:
                    dp = Path(p["local_dir"]) / "描述.txt"
                    if not dp.exists():
                        return p["idx"], None, False, "", "无描述.txt"
                    text = dp.read_text(
                        encoding="utf-8", errors="ignore")
                    if not text.strip():
                        return p["idx"], None, False, "", "描述.txt为空"
                    sizes, has_ban, raw, reason = parse_sizes_from_desc(
                        text, p.get("banma"))
                    return p["idx"], sizes, has_ban, raw, reason
                except Exception as e:
                    return (p["idx"], None, False, "",
                            f"读取失败: {str(e)[:60]}")

            done = 0
            t_e1_start = time.time()
            last_status = time.time()

            with ThreadPoolExecutor(
                    max_workers=self.E1_READ_WORKERS) as ex:
                futures = {ex.submit(_read_one, p): p for p in prepared}
                for fut in as_completed(futures):
                    p = futures[fut]
                    idx, sizes, has_ban, raw, reason = fut.result()
                    if sizes is not None:
                        ocr_results[idx] = (sizes, has_ban, raw, reason)
                    else:
                        stage_a_fail.append({
                            "p": p, "text_full": raw, "reason": reason,
                        })
                    done += 1

                    now = time.time()
                    if (now - last_status) > 0.3 or done == total_e1:
                        elapsed = now - t_e1_start
                        speed = done / elapsed if elapsed > 0 else 0
                        self.set_status(
                            f"③-E1 {done}/{total_e1}  "
                            f"成功 {len(ocr_results)}  "
                            f"{speed:.0f} 条/秒")
                        last_status = now

            # 刷新表格
            for i, p in enumerate(prepared):
                real_idx = base_idx + i
                if real_idx >= len(self.table.tasks):
                    break
                task = self.table.tasks[real_idx]
                if task is None:
                    continue
                if p["idx"] in ocr_results:
                    sizes = ocr_results[p["idx"]][0]
                    task.status = "success"
                    task.message = f"✔{len(sizes)}码"
                else:
                    task.status = "error"
                    task.message = "失败"
                self.table.update_task_at(real_idx, task)
            self.app.root.update_idletasks()

            stage_a_ok = len(ocr_results)
            print(f"   [③-E1 成功 {stage_a_ok}/{total_e1}  "
                  f"失败 {len(stage_a_fail)}]")

            if stage_a_fail:
                failed_path = self._save_failed_queue(
                    stage_a_fail, phase="3a")
                print(f"   [失败队列已保存: {failed_path.name}]")
                self.app.root.after(
                    0, lambda n=len(stage_a_fail), p=failed_path.name:
                    self.retry_info_var.set(
                        f"E1 失败 {n} 条 → {p}"))

        else:
            # ---------- E2 原 OCR 流程 ----------
            self.set_status("③ 初始化 OCR 引擎...")

            from core.e_pipeline import (
                init_ocr_worker, get_backend_info, cleanup_temp_files
            )
            from core.e_pipeline_mp import (
                init_ocr_worker as mp_init_worker,
                ocr_batch_chunk,
            )

            init_ocr_worker()
            backend_info = get_backend_info()
            print(f"   [OCR 引擎: {backend_info}]")
            self.app.root.after(
                0, lambda info=backend_info: self._set_ocr_status(info))

            total_ocr = len(prepared)

            if total_ocr > 0:
                self.set_status(
                    f"③-A 整图 OCR ({total_ocr} 组, "
                    f"{self.OCR_PROCESSES} 进程)...")

                self.table.add_header(
                    f"══ ③-A 整图 OCR ({total_ocr} 组) ══")
                base_idx = len(self.table.tasks)
                self.table.append_tasks_batch(
                    [Task("C-1", p["onlymulu"], "") for p in prepared],
                    auto_scroll=False,
                    max_display=2000,
                )
                self.app.root.update_idletasks()

                args_list = [
                    (p["idx"], p["onlymulu"], p["first_img"], p["banma"])
                    for p in prepared
                ]

                CHUNK_SIZE = 50
                chunks = [args_list[i:i + CHUNK_SIZE]
                          for i in range(0, len(args_list), CHUNK_SIZE)]

                print(f"   [③-A {total_ocr} 个, {len(chunks)} 块, "
                      f"{self.OCR_PROCESSES} 进程]")

                done = 0
                t_ocr_start = time.time()
                last_status_update = time.time()

                with ProcessPoolExecutor(
                        max_workers=self.OCR_PROCESSES,
                        initializer=mp_init_worker,
                ) as ex:
                    results_iter = ex.map(
                        ocr_batch_chunk, chunks, chunksize=1)

                    for batch_results in results_iter:
                        for r in batch_results:
                            try:
                                idx, sizes, has_ban, text, reason = r
                            except Exception:
                                continue

                            if sizes is not None:
                                ocr_results[idx] = (
                                    sizes, has_ban, text, reason)
                                stage_a_ok += 1
                            else:
                                p = next((x for x in prepared
                                          if x["idx"] == idx), None)
                                if p:
                                    stage_a_fail.append({
                                        "p": p,
                                        "text_full": text,
                                        "reason": reason,
                                    })

                        done += len(batch_results)

                        now = time.time()
                        if (now - last_status_update) > 0.5 \
                                or done == total_ocr:
                            elapsed = now - t_ocr_start
                            speed = done / elapsed if elapsed > 0 else 0
                            pct = (done / total_ocr * 100
                                   if total_ocr > 0 else 0)
                            if speed > 0:
                                remain_sec = (total_ocr - done) / speed
                                remain_str = (
                                    f"{remain_sec / 60:.1f}分"
                                    if remain_sec >= 60
                                    else f"{remain_sec:.0f}秒")
                            else:
                                remain_str = "计算中"

                            self.set_status(
                                f"③-A {done}/{total_ocr} ({pct:.1f}%)  "
                                f"成功 {stage_a_ok}  |  "
                                f"{speed:.1f} 张/秒  |  "
                                f"剩余 {remain_str}")
                            last_status_update = now

                # 刷新表格
                self.set_status("③-A 刷新表格...")
                self.app.root.update_idletasks()
                for i, p in enumerate(prepared):
                    real_idx = base_idx + i
                    if real_idx >= len(self.table.tasks):
                        break
                    t = self.table.tasks[real_idx]
                    if t is None:
                        continue
                    if p["idx"] in ocr_results:
                        sizes = ocr_results[p["idx"]][0]
                        t.status = "success"
                        t.message = f"✔{len(sizes)}码"
                    else:
                        t.status = "error"
                        t.message = "失败"
                    self.table.update_task_at(real_idx, t)

            print(f"   [③-A 成功 {stage_a_ok}/{total_ocr}  "
                  f"失败 {len(stage_a_fail)}]")

            try:
                cleanup_temp_files()
            except Exception:
                pass

            if stage_a_fail:
                failed_path = self._save_failed_queue(
                    stage_a_fail, phase="3a")
                print(f"   [失败队列已保存: {failed_path.name}]")
                self.app.root.after(
                    0, lambda n=len(stage_a_fail), p=failed_path.name:
                    self.retry_info_var.set(
                        f"3A 失败 {n} 条 → {p}"))

        timings["③ 尺码提取"] = time.time() - t0
        print(f"   [③ 总耗时 {timings['③ 尺码提取']:.2f}s]")

        # ==========================================================
        #  阶段④ 翻译（仅成功项）
        # ==========================================================
        t0 = time.time()

        if do_translate and ocr_results:
            self.set_status(
                f"④ 翻译英文→俄语 ({trans_workers} 线程)...")
            from config_manager import load_config
            cfg = load_config()
            api_key = cfg.get("DEEPSEEK_API_KEY", "")

            if api_key:
                try:
                    from core.ru_translator import EnToRuTranslator
                    translator = EnToRuTranslator(
                        api_key=api_key,
                        model=cfg.get("MODEL", "deepseek-chat"))

                    ok_prepared = [p for p in prepared
                                   if p["idx"] in ocr_results]

                    products = [p["product"] for p in ok_prepared]
                    idx_list = [p["idx"] for p in ok_prepared]

                    if products:
                        print(f"   [翻译源: {len(products)} 个产品名]")
                        results = translator.translate_products(
                            products, max_workers=trans_workers)
                        for i, r in enumerate(results):
                            if i < len(idx_list) and r["rufanyi"]:
                                rufanyi_map[idx_list[i]] = r["rufanyi"]

                        for r in results[:3]:
                            print(f"     原: {r['original'][:60]}")
                            print(f"     俄: {r['rufanyi'][:60]}")

                    translator.close()
                    print(f"   [翻译完成: {len(rufanyi_map)} 条]")
                except Exception as e:
                    import traceback
                    print(f"   翻译失败: {e}")
                    print(traceback.format_exc())

        timings["④ 翻译"] = time.time() - t0
        print(f"   [④ 翻译 {timings['④ 翻译']:.2f}s, "
              f"{len(rufanyi_map)} 条]")

        # ==========================================================
        #  阶段⑤ 写库 + 导出（仅成功项）
        # ==========================================================
        t0 = time.time()
        self.set_status("⑤ 写库 + 导出...")

        db = DBManager(db_path)
        ok_cnt = dup_cnt = 0

        for p in prepared:
            idx = p["idx"]
            if idx not in ocr_results:
                continue

            sizes, has_ban, raw, reason = ocr_results[idx]

            data = {
                "nums": idx,
                "onlymulu": p["onlymulu"],
                "englishname": p.get("englishname", ""),
                "local_url": "\n".join(p["local_urls"]),
                "web_url": "\n".join(p["web_urls"]),
                "rufanyi": rufanyi_map.get(idx, ""),
                "shoessize": ",".join(sizes),
                "chuprice": p["chuprice"],
                "images": p["images"],
                "bands": p["brand"],
                "bandsizechart": p["sizechart"],
                "source_dir": str(self.target_dir),
            }

            r = db.upsert_product(data)
            if r == "inserted":
                ok_cnt += 1
            elif r == "duplicate":
                dup_cnt += 1

        db.close()
        timings["⑤ 写库"] = time.time() - t0
        print(f"   [⑤ 写库 {timings['⑤ 写库']:.2f}s  "
              f"新增 {ok_cnt}  重复 {dup_cnt}]")

        total_time = time.time() - t_all

        # ==========================================================
        #  汇总
        # ==========================================================
        print(f"\n{'=' * 60}")
        print(f"📊 耗时分析 (共 {total} 组, 模式 {mode})")
        print(f"{'=' * 60}")
        for k, v in timings.items():
            pct = (v / total_time * 100) if total_time > 0 else 0
            bar = "█" * int(pct / 2)
            print(f"  {k:<12} {v:>8.2f}s  {pct:>5.1f}%  {bar}")
        print(f"{'─' * 60}")
        print(f"  总计         {total_time:>8.2f}s")
        print(f"{'=' * 60}")

        summary_lines = [
            f"处理完成 ({mode} 模式), 耗时 {total_time:.1f} 秒",
            "─" * 45,
        ]
        for k, v in timings.items():
            pct = (v / total_time * 100) if total_time > 0 else 0
            summary_lines.append(f"  {k:<12} {v:>7.2f}s ({pct:>4.1f}%)")
        summary_lines.append("─" * 45)
        summary_lines.append(f"  成功入库: {ok_cnt}")
        summary_lines.append(f"  重复丢弃: {dup_cnt}")
        summary_lines.append(f"  尺码失败: {len(stage_a_fail)}")
        summary_lines.append("─" * 45)
        summary_lines.append(f"  总计:     {total} 组")
        summary_lines.append(f"  数据库:   {db_path}")
        if failed_path:
            summary_lines.append("")
            summary_lines.append("失败文档已保存:")
            summary_lines.append(f"  {failed_path.name}")
            summary_lines.append("")
            summary_lines.append("★ 点击【🔄 二次识别】继续处理")

        self.set_status(
            f"E 模块 ({mode}): 完成 ✔{ok_cnt} ⏭{dup_cnt} "
            f"失败 {len(stage_a_fail)} 耗时 {total_time:.1f}s")
        self.app.root.after(0, lambda: self.hint_var.set(
            "\n".join(summary_lines)))
        self.app.root.after(0, lambda: messagebox.showinfo(
            "入库完成", "\n".join(summary_lines)))

    # ==========================================================
    #               ★ 保存失败队列
    # ==========================================================
    def _save_failed_queue(self, fail_items, phase="3a"):
        """保存失败项到 JSON"""
        log_dir = Path(self.target_dir) / "_logs"
        log_dir.mkdir(exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = log_dir / f"failed_queue_{phase}_{ts}.json"

        data = []
        for item in fail_items:
            p = item["p"]
            banma = list(p.get("banma", []))
            data.append({
                "idx": p.get("idx", 0),
                "onlymulu": p.get("onlymulu", ""),
                "ap_name": p.get("ap_name", ""),
                "product": p.get("product", ""),
                "first_img": p.get("first_img", ""),
                "local_dir": p.get("local_dir", ""),
                "local_urls": list(p.get("local_urls", [])),
                "web_urls": list(p.get("web_urls", [])),
                "images": p.get("images", 0),
                "chuprice": p.get("chuprice"),
                "brand": p.get("brand", ""),
                "sizechart": p.get("sizechart", ""),
                "banma": banma,
                "englishname": p.get("englishname", ""),
                "reason": item.get("reason", ""),
                "ocr_text_prev": item.get("text_full", ""),
            })

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return path

    # ==========================================================
    #               ★ 二次识别（独立流程，仅 E2 用）
    # ==========================================================
    def run_retry_batch(self):
        """读失败文档 → 3B 拼接 OCR → 翻译 → 入库"""
        if not self._ensure_dir():
            return

        log_dir = Path(self.target_dir) / "_logs"
        if not log_dir.exists():
            messagebox.showinfo("提示", "无 _logs 目录，无失败文档")
            return

        files_3a = sorted(log_dir.glob("failed_queue_3a_*.json"),
                          reverse=True)
        files_3b = sorted(log_dir.glob("failed_queue_3b_*.json"),
                          reverse=True)
        all_files = files_3a + files_3b

        if not all_files:
            messagebox.showinfo("提示", "无失败文档，请先执行入库")
            return

        choice = self._choose_failed_file(all_files)
        if choice is None:
            return

        failed_path = choice
        print(f"\n{'=' * 60}")
        print(f"▶ 二次识别: {failed_path.name}")
        print(f"{'=' * 60}")

        try:
            with open(failed_path, "r", encoding="utf-8") as f:
                failed_items = json.load(f)
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return

        if not failed_items:
            messagebox.showinfo("提示", "失败文档为空")
            return

        prepared = []
        for item in failed_items:
            prepared.append({
                "idx": item["idx"],
                "onlymulu": item["onlymulu"],
                "ap_name": item["ap_name"],
                "product": item["product"],
                "first_img": item["first_img"],
                "local_dir": item.get("local_dir", ""),
                "local_urls": item["local_urls"],
                "web_urls": item["web_urls"],
                "images": item["images"],
                "chuprice": item["chuprice"],
                "brand": item["brand"],
                "sizechart": item["sizechart"],
                "banma": item["banma"],
                "englishname": item["englishname"],
            })

        total = len(prepared)
        print(f"   待二次识别: {total} 条")

        if not messagebox.askyesno(
            "确认二次识别",
            f"将二次识别 {total:,} 条失败项\n\n"
            f"源文档: {failed_path.name}\n\n"
            f"确定继续?"):
            return

        self.retry_btn.config(state="disabled")
        self.set_status(f"🔄 二次识别 {total} 条...")

        def worker():
            try:
                self._retry_worker(prepared, failed_path)
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                err_msg = str(e)
                self.app.root.after(
                    0,
                    lambda msg=err_msg, t=tb: messagebox.showerror(
                        "错误", f"{msg}\n\n{t[:800]}")
                )
            finally:
                self.app.root.after(
                    0, lambda: self.retry_btn.config(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _retry_worker(self, prepared, failed_path):
        """二次识别主流程（原 E2 拼接 OCR）"""
        from core.e_pipeline_mp import (
            init_ocr_worker as mp_init_worker,
            ocr_retry_chunk,
        )

        t_all = time.time()
        timings = {}

        self._ui_sync(lambda: self.table.clear())

        # ==========================================================
        #  阶段① 二次识别
        # ==========================================================
        t0 = time.time()
        self._update_progress_safe(f"① 二次识别 {len(prepared)} 条...")

        total = len(prepared)
        ocr_results = {}

        args_list = [
            (p["idx"], p["onlymulu"], p["first_img"], p["banma"], "")
            for p in prepared
        ]
        CHUNK_SIZE = 50
        chunks = [args_list[i:i + CHUNK_SIZE]
                  for i in range(0, len(args_list), CHUNK_SIZE)]

        def _setup_table():
            self.table.clear()
            self.table.add_header(f"══ 二次识别 ({total} 条) ══")
            self.table.append_tasks_batch(
                [Task("C-1", p["onlymulu"], "") for p in prepared],
                auto_scroll=False,
                max_display=2000,
            )

        self._ui_sync(_setup_table)
        base_idx = len(self.table.tasks)

        success_cnt = 0
        fail_items = []

        with ProcessPoolExecutor(
                max_workers=self.OCR_PROCESSES,
                initializer=mp_init_worker,
        ) as ex:
            futures = {ex.submit(ocr_retry_chunk, chunk): i
                       for i, chunk in enumerate(chunks)}

            done = 0
            t_retry_start = time.time()

            for fut in as_completed(futures):
                try:
                    batch_results = fut.result()
                except Exception:
                    batch_results = []

                for r in batch_results:
                    try:
                        idx, sizes, has_ban, text, reason = r
                    except Exception:
                        continue

                    if sizes is not None:
                        ocr_results[idx] = (sizes, has_ban, text, reason)
                        success_cnt += 1
                    else:
                        p = next((x for x in prepared
                                  if x["idx"] == idx), None)
                        if p:
                            fail_items.append({
                                "p": p, "text_full": text,
                                "reason": reason,
                            })

                done += len(batch_results)
                if done % 50 == 0 or done == total:
                    elapsed = time.time() - t_retry_start
                    speed = done / elapsed if elapsed > 0 else 0
                    pct = done / total * 100 if total > 0 else 0

                    if speed > 0:
                        remain_sec = (total - done) / speed
                        if remain_sec >= 60:
                            remain_str = f"{remain_sec / 60:.1f}分"
                        else:
                            remain_str = f"{remain_sec:.0f}秒"
                    else:
                        remain_str = "计算中"

                    self._update_progress_safe(
                        f"① 二次识别 {done}/{total} ({pct:.1f}%)  "
                        f"成功 {success_cnt}  |  "
                        f"{speed:.1f} 张/秒  |  "
                        f"剩余 {remain_str}")

        timings["① 二次识别"] = time.time() - t0
        print(f"   [① 二次识别 {timings['① 二次识别']:.2f}s  "
              f"成功 {success_cnt}/{total}]")

        if not ocr_results:
            self.app.root.after(0, lambda: messagebox.showinfo(
                "二次识别完成", "全部失败"))
            if fail_items:
                remain_path = self._save_failed_queue(fail_items, "3b")
                print(f"   [剩余失败已保存: {remain_path.name}]")
            return

        # ==========================================================
        #  阶段② 翻译
        # ==========================================================
        t0 = time.time()
        self._update_progress_safe(f"② 翻译 {success_cnt} 条...")

        rufanyi_map = {}
        from config_manager import load_config
        cfg = load_config()
        api_key = cfg.get("DEEPSEEK_API_KEY", "")
        do_translate = self.translate_var.get()

        if do_translate and api_key:
            try:
                from core.ru_translator import EnToRuTranslator
                translator = EnToRuTranslator(
                    api_key=api_key,
                    model=cfg.get("MODEL", "deepseek-chat"))

                ok_prepared = [p for p in prepared
                               if p["idx"] in ocr_results]

                products = [p["product"] for p in ok_prepared]
                idx_list = [p["idx"] for p in ok_prepared]

                if products:
                    trans_workers = max(
                        1, int(self.trans_workers_var.get() or 8))
                    results = translator.translate_products(
                        products, max_workers=trans_workers)
                    for i, r in enumerate(results):
                        if i < len(idx_list) and r["rufanyi"]:
                            rufanyi_map[idx_list[i]] = r["rufanyi"]
                translator.close()
            except Exception as e:
                print(f"   [翻译失败: {e}]")

        timings["② 翻译"] = time.time() - t0
        print(f"   [② 翻译 {timings['② 翻译']:.2f}s  "
              f"{len(rufanyi_map)} 条]")

        # ==========================================================
        #  阶段③ 入库
        # ==========================================================
        t0 = time.time()
        self._update_progress_safe(f"③ 入库 {success_cnt} 条...")

        db = DBManager(self.db_var.get().strip())

        ok_cnt = dup_cnt = 0
        for p in prepared:
            idx = p["idx"]
            if idx not in ocr_results:
                continue

            sizes, has_ban, raw, reason = ocr_results[idx]

            data = {
                "nums": idx,
                "onlymulu": p["onlymulu"],
                "englishname": p.get("englishname", ""),
                "local_url": "\n".join(p["local_urls"]),
                "web_url": "\n".join(p["web_urls"]),
                "rufanyi": rufanyi_map.get(idx, ""),
                "shoessize": ",".join(sizes),
                "chuprice": p["chuprice"],
                "images": p["images"],
                "bands": p["brand"],
                "bandsizechart": p["sizechart"],
                "source_dir": str(self.target_dir),
            }
            r = db.upsert_product(data)
            if r == "inserted":
                ok_cnt += 1
            elif r == "duplicate":
                dup_cnt += 1

        db.close()
        timings["③ 入库"] = time.time() - t0
        print(f"   [③ 入库 {timings['③ 入库']:.2f}s  "
              f"新增 {ok_cnt}  重复 {dup_cnt}]")

        # ==========================================================
        #  阶段④ 剩余失败 → 新文档
        # ==========================================================
        remain_path = None
        if fail_items:
            remain_path = self._save_failed_queue(fail_items, "3b")
            print(f"   [剩余失败已保存: {remain_path.name}]")

        # ==========================================================
        #  汇总
        # ==========================================================
        total_time = time.time() - t_all

        summary = [
            f"二次识别完成,耗时 {total_time:.1f}s",
            "─" * 45,
            f"  待识别:  {total:,}",
            f"  成功:    {success_cnt:,}  "
            f"({success_cnt / total * 100:.1f}%)",
            f"  入库:    {ok_cnt:,}  重复 {dup_cnt:,}",
            f"  剩余失败: {len(fail_items):,}",
        ]
        if remain_path:
            summary.append(f"  失败文档: {remain_path.name}")

        self.app.root.after(
            0, lambda: messagebox.showinfo(
                "二次识别完成", "\n".join(summary)))
        self.app.root.after(
            0, lambda: self.set_status(
                f"二次识别完成: 成功 {success_cnt} 入库 {ok_cnt}"))
        self.app.root.after(
            0, lambda: self.retry_info_var.set(
                f"上次: 成功 {success_cnt}/{total}"))

    def _choose_failed_file(self, files):
        """选择失败文档"""
        win = tk.Toplevel(self.app.root)
        win.title("选择失败文档")
        win.geometry("700x500")
        win.transient(self.app.root)
        win.grab_set()

        result = {"path": None}

        ttk.Label(win, text="请选择要二次识别的失败文档:",
                  font=("", 11, "bold"), padding=10).pack(anchor="w")

        lb = tk.Listbox(win, font=("Consolas", 9))
        lb.pack(fill="both", expand=True, padx=10, pady=5)

        for i, f in enumerate(files):
            size = f.stat().st_size / 1024
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    cnt = len(json.load(fp))
            except Exception:
                cnt = "?"
            lb.insert("end", f"{f.name}  [{cnt} 条]  {size:.1f}KB")

        lb.selection_set(0)

        def on_ok():
            sel = lb.curselection()
            if sel:
                result["path"] = files[sel[0]]
            win.destroy()

        btn = ttk.Frame(win, padding=10)
        btn.pack(fill="x")
        ttk.Button(btn, text="取消",
                   command=win.destroy).pack(side="right", padx=4)
        ttk.Button(btn, text="✔ 确定",
                   command=on_ok).pack(side="right", padx=4)

        win.wait_window()
        return result["path"]

    # ==========================================================
    #                       数据库统计
    # ==========================================================
    def show_db_stats(self):
        db_path = self.db_var.get().strip()
        if not Path(db_path).exists():
            messagebox.showinfo("提示", f"数据库不存在:\n{db_path}")
            return

        db = DBManager(db_path)
        cur = db.conn.cursor()

        lines = []
        sep = "═" * 70

        lines.append(sep)
        lines.append("📁 数据库文件信息")
        lines.append(sep)
        file_size = Path(db_path).stat().st_size
        lines.append(f"  路径:     {db_path}")
        lines.append(f"  大小:     {self._format_size(file_size)}")
        lines.append("")

        lines.append(sep)
        lines.append("📊 总体统计")
        lines.append(sep)
        cur.execute("SELECT COUNT(*) FROM products")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM failed_items")
        failed = cur.fetchone()[0]
        cur.execute("""SELECT COUNT(*) FROM products
                       WHERE shoessize IS NOT NULL AND shoessize != ''""")
        with_size = cur.fetchone()[0]
        cur.execute("""SELECT COUNT(*) FROM products
                       WHERE rufanyi IS NOT NULL AND rufanyi != ''""")
        with_trans = cur.fetchone()[0]

        lines.append(f"  产品记录总数:   {total:,}")
        lines.append(f"  失败记录总数:   {failed:,}")
        if total > 0:
            lines.append(f"  有尺码记录:     {with_size:,}  "
                         f"({with_size / total * 100:.1f}%)")
            lines.append(f"  有翻译记录:     {with_trans:,}  "
                         f"({with_trans / total * 100:.1f}%)")
        lines.append("")

        if total > 0:
            cur.execute("""SELECT MIN(chuprice), MAX(chuprice),
                                  AVG(chuprice), SUM(chuprice)
                           FROM products WHERE chuprice IS NOT NULL""")
            pmin, pmax, pavg, psum = cur.fetchone()
            if pmin is not None:
                lines.append(sep)
                lines.append("💰 价格统计")
                lines.append(sep)
                lines.append(f"  最低: {pmin}  最高: {pmax}  "
                             f"平均: {pavg:.1f}  总和: {psum:,}")
                lines.append("")

        if total > 0:
            lines.append(sep)
            lines.append("🏷️  品牌分布")
            lines.append(sep)
            cur.execute("""SELECT bands, COUNT(*) FROM products
                           GROUP BY bands ORDER BY COUNT(*) DESC""")
            brands = cur.fetchall()
            lines.append(f"  品牌种类: {len(brands)}")
            for brand, cnt in brands:
                pct = cnt / total * 100
                b_disp = (brand or "(空)")[:24]
                lines.append(f"  {b_disp:<24} {cnt:>6,}   {pct:>5.1f}%")
            lines.append("")

        if total > 0:
            lines.append(sep)
            lines.append("🕐 最近入库 10 条")
            lines.append(sep)
            cur.execute("""SELECT id, onlymulu, englishname, rufanyi,
                                  bands, chuprice, images, shoessize
                           FROM products ORDER BY id DESC LIMIT 10""")
            rows = cur.fetchall()
            for rid, om, en, ru, bands, price, images, sizes in rows:
                om_disp = (om or "")[:55]
                en_disp = (en or "")[:60]
                ru_disp = (ru or "")[:60]
                b_disp = (bands or "")[:15]
                lines.append(f"  [{rid}] {om_disp}")
                lines.append(f"       英文: {en_disp}")
                lines.append(f"       俄语: {ru_disp}")
                lines.append(f"       品牌={b_disp}  价={price}  "
                             f"图={images}  尺码={(sizes or '')[:50]}")
            lines.append("")

        if failed > 0:
            lines.append(sep)
            lines.append("❌ 失败原因分布")
            lines.append(sep)
            cur.execute("""SELECT reason, COUNT(*) FROM failed_items
                           GROUP BY reason ORDER BY COUNT(*) DESC""")
            for r, c in cur.fetchall():
                pct = c / failed * 100
                lines.append(f"  {r:<30} {c:>6,}   {pct:>5.1f}%")
            lines.append("")

        lines.append(sep)
        lines.append(f"统计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(sep)

        db.close()
        self._show_text_dialog("数据库完整统计", "\n".join(lines))

    def _show_text_dialog(self, title, text, width=100, height=40):
        win = tk.Toplevel(self.app.root)
        win.title(title)
        win.geometry(f"{width * 8}x{height * 20}")
        win.transient(self.app.root)

        bar = ttk.Frame(win, padding=4)
        bar.pack(fill="x")

        ttk.Button(bar, text="复制全部",
                   command=lambda: self._copy_to_clipboard(win, text)).pack(
            side="left", padx=2)
        ttk.Button(bar, text="保存为 txt",
                   command=lambda: self._save_to_file(text)).pack(
            side="left", padx=2)
        ttk.Button(bar, text="关闭",
                   command=win.destroy).pack(side="right", padx=2)

        from tkinter.scrolledtext import ScrolledText
        txt = ScrolledText(win, wrap="none", font=("Consolas", 9))
        txt.pack(fill="both", expand=True, padx=4, pady=4)
        txt.insert("1.0", text)
        txt.config(state="disabled")

        xsb = ttk.Scrollbar(win, orient="horizontal", command=txt.xview)
        xsb.pack(fill="x")
        txt.config(xscrollcommand=xsb.set)

    def _copy_to_clipboard(self, win, text):
        win.clipboard_clear()
        win.clipboard_append(text)
        messagebox.showinfo("提示", "已复制到剪贴板")

    def _save_to_file(self, text):
        p = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
            initialfile=f"db_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        )
        if p:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(text)
                messagebox.showinfo("提示", f"已保存到:\n{p}")
            except Exception as e:
                messagebox.showerror("错误", str(e))

    @staticmethod
    def _format_size(size_bytes):
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"

    def _execute_one(self, task):
        return "skip", "E 模块无单任务执行"