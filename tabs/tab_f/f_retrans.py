# tabs/tab_f/f_retrans.py
"""F 菜单 — 二次翻译（英译俄）"""
import re
import shutil
import threading
import tkinter as tk
from pathlib import Path
from datetime import datetime
from tkinter import ttk, messagebox

from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from openpyxl import Workbook
    _XLSX_OK = True
except ImportError:
    _XLSX_OK = False


class FRetransMixin:
    """二次翻译"""

    def _update_retrans_scope(self):
        if not hasattr(self, "retrans_scope_var"):
            return
        n = len(self._all_rows)
        has_en = sum(1 for r in self._all_rows
                     if (r.get("englishname") or "").strip())
        self.retrans_scope_var.set(
            f"影响范围: {n:,} 条, 其中有英文名 {has_en:,} 条")

    def _preview_retranslate(self):
        if not self._all_rows:
            messagebox.showinfo("提示", "请先查询出结果")
            return

        from config_manager import load_config
        cfg = load_config()
        api_key = cfg.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            messagebox.showerror("缺少 API Key",
                                 "请先在 B 菜单或 config.json 中配置 DEEPSEEK_API_KEY")
            return

        items = []
        for row in self._all_rows:
            en = (row.get("englishname") or "").strip()
            if en:
                items.append({
                    "id": row.get("id"),
                    "englishname": en,
                    "old_rufanyi": row.get("rufanyi") or "",
                })

        if not items:
            messagebox.showinfo("提示", "当前查询结果中没有【英文名】可用")
            return

        if not messagebox.askyesno(
            "二次翻译",
            f"将对 {len(items):,} 条记录进行英译俄\n\n"
            f"并发: {self.retrans_workers_var.get()} 线程\n"
            f"批次大小: {self.retrans_batch_var.get()}\n\n"
            f"⚠️ 会消耗 API Token\n\n是否继续？"):
            return

        self.set_status(f"🌐 正在翻译 {len(items)} 条...")
        mode = self.retrans_mode_var.get()

        def worker():
            try:
                if mode == "word":
                    results = self._run_word_translate(items)
                else:
                    results = self._run_retranslate(items)
                self.app.root.after(
                    0, lambda: self._show_retranslate_report(results))
            except Exception as e:
                import traceback
                err = str(e)
                tb = traceback.format_exc()
                self.app.root.after(
                    0, lambda: messagebox.showerror(
                        "翻译失败", f"{err}\n\n{tb[:500]}"))
                self.app.root.after(0, lambda: self.set_status("翻译失败"))

        threading.Thread(target=worker, daemon=True).start()

    def _run_retranslate(self, items):
        from config_manager import load_config
        from core.ru_translator import EnToRuTranslator

        cfg = load_config()
        api_key = cfg.get("DEEPSEEK_API_KEY", "")
        model = cfg.get("MODEL", "deepseek-chat")

        workers = max(1, int(self.retrans_workers_var.get() or 8))
        batch_size = max(5, int(self.retrans_batch_var.get() or 20))

        translator = EnToRuTranslator(api_key=api_key, model=model)
        english_list = [it["englishname"] for it in items]
        results = translator._do_batch_translate_parallel(
            english_list, max_workers=workers, batch_size=batch_size)
        translator.close()

        output = []
        for i, it in enumerate(items):
            new_ru = results[i] if i < len(results) else ""
            output.append({
                "id": it["id"],
                "englishname": it["englishname"],
                "old_rufanyi": it["old_rufanyi"],
                "new_rufanyi": new_ru,
                "changed": new_ru != it["old_rufanyi"],
            })
        return output

    def _load_brand_keywords(self):
        try:
            from config_manager import load_config
            cfg = load_config()
            brand_dir = cfg.get("BRAND_DIR", "") or str(Path.cwd() / "data")
            allbands_path = Path(brand_dir) / "allbands.txt"
            if not allbands_path.exists():
                return set()
            keywords = set()
            with open(allbands_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip().lower()
                    if line and not line.startswith("#"):
                        keywords.add(line)
            print(f"[F] ✅ 已加载 {len(keywords)} 个品牌关键词")
            return keywords
        except Exception as e:
            print(f"[F] ⚠️ 加载品牌关键词失败: {e}")
            return set()

    def _run_word_translate(self, items):
        from config_manager import load_config
        from core.ru_translator import EnToRuTranslator

        cfg = load_config()
        api_key = cfg.get("DEEPSEEK_API_KEY", "")
        model = cfg.get("MODEL", "deepseek-chat")
        workers = max(1, int(self.retrans_workers_var.get() or 8))
        batch_size = max(5, int(self.retrans_batch_var.get() or 20))

        brand_keywords = self._load_brand_keywords()

        all_words = set()
        for it in items:
            for w in re.findall(r"[a-zA-Z]+", it["englishname"]):
                all_words.add(w)

        words_to_translate = []
        brand_words_kept = []
        for w in all_words:
            if w.lower() in brand_keywords:
                brand_words_kept.append(w)
            else:
                words_to_translate.append(w)

        word_dict = {}
        if words_to_translate:
            translator = EnToRuTranslator(api_key=api_key, model=model)
            batches = [words_to_translate[i:i + batch_size]
                       for i in range(0, len(words_to_translate), batch_size)]

            def do_batch(words):
                return translator._do_batch_translate(words)

            with ThreadPoolExecutor(max_workers=workers) as ex:
                futures = {ex.submit(do_batch, b): b for b in batches}
                for fut in as_completed(futures):
                    batch = futures[fut]
                    try:
                        translated = fut.result()
                        for j, w in enumerate(batch):
                            if j < len(translated) and translated[j]:
                                word_dict[w] = translated[j]
                    except Exception:
                        pass
            translator.close()

        for w in brand_words_kept:
            word_dict[w] = w

        output = []
        for it in items:
            words = re.findall(r"[a-zA-Z]+", it["englishname"])
            new_parts = []
            for w in words:
                if w.lower() in brand_keywords:
                    new_parts.append(w)
                elif w in word_dict:
                    new_parts.append(word_dict[w])
                else:
                    new_parts.append(w)
            new_ru = " ".join(new_parts)
            new_ru = re.sub(r"[^a-zA-Z0-9\u0400-\u04FF\s]", " ", new_ru)
            new_ru = " ".join(new_ru.split())
            output.append({
                "id": it["id"],
                "englishname": it["englishname"],
                "old_rufanyi": it["old_rufanyi"],
                "new_rufanyi": new_ru,
                "changed": new_ru != it["old_rufanyi"],
            })
        return output

    def _show_retranslate_report(self, results):
        total = len(results)
        changed = sum(1 for r in results if r["changed"])
        failed = sum(1 for r in results if not r["new_rufanyi"])

        win = tk.Toplevel(self.app.root)
        win.title("翻译对照报告 - 预览")
        win.geometry("1200x750")
        win.transient(self.app.root)
        win.grab_set()

        stat = ttk.Frame(win, padding=10)
        stat.pack(fill="x")
        mode = self.retrans_mode_var.get()
        mode_label = "逐词翻译 (保留品牌)" if mode == "word" else "整句翻译"
        ttk.Label(stat, text=f"🌐 翻译对照报告  【{mode_label}】",
                  font=("", 13, "bold")).pack(anchor="w")
        ttk.Label(stat,
                  text=f"  总数: {total:,}    变化: {changed:,}    "
                       f"失败: {failed:,}",
                  font=("", 10)).pack(anchor="w", pady=(4, 0))
        ttk.Label(stat,
                  text="  请检查下方对照表,确认无误后点击【执行覆盖】按钮",
                  foreground="#804000",
                  font=("", 9)).pack(anchor="w", pady=(4, 0))

        table_frame = ttk.Frame(win, padding=(10, 0, 10, 0))
        table_frame.pack(fill="both", expand=True)

        cols = ("id", "en", "old", "new", "changed")
        tree = ttk.Treeview(table_frame, columns=cols, show="headings")
        tree.heading("id", text="ID")
        tree.heading("en", text="英文名")
        tree.heading("old", text="原俄语翻译")
        tree.heading("new", text="新俄语翻译")
        tree.heading("changed", text="变化")
        tree.column("id", width=60, anchor="center")
        tree.column("en", width=340, anchor="w")
        tree.column("old", width=340, anchor="w")
        tree.column("new", width=340, anchor="w")
        tree.column("changed", width=60, anchor="center")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for i, r in enumerate(results):
            if i >= 1000:
                break
            tree.insert("", "end", values=(
                r["id"],
                (r["englishname"] or "")[:80],
                (r["old_rufanyi"] or "(空)")[:80],
                (r["new_rufanyi"] or "(空)")[:80],
                "√" if r["changed"] else ""))

        btn = ttk.Frame(win, padding=12)
        btn.pack(fill="x", side="bottom")
        save_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(btn, text="保存对照报告 (xlsx)",
                        variable=save_var).pack(side="left", padx=4)

        def on_switch_mode():
            current = self.retrans_mode_var.get()
            new_mode = "sentence" if current == "word" else "word"
            new_label = "整句翻译" if new_mode == "sentence" else "逐词翻译"
            if not messagebox.askyesno(
                "切换翻译模式",
                f"将切换到【{new_label}】模式重新翻译。\n\n会再次消耗 Token,是否继续?"):
                return
            self.retrans_mode_var.set(new_mode)
            win.destroy()
            self.app.root.after(100, self._preview_retranslate)

        ttk.Button(btn, text="🔄 切换翻译模式", width=18,
                   command=on_switch_mode).pack(side="right", padx=6)
        ttk.Button(btn, text="✖ 取消", width=14,
                   command=win.destroy).pack(side="right", padx=6)

        def on_execute():
            if not messagebox.askyesno(
                "确认覆盖",
                f"将用新翻译覆盖数据库中的俄语翻译字段。\n\n"
                f"影响记录: {total:,} 条, 其中变化: {changed:,} 条\n\n"
                f"⚠️ 会自动备份数据库,此操作不可撤销。\n\n确定执行?"):
                return
            try:
                report_path = self._save_retranslate_report(results) if save_var.get() else None
                ok, err = self._write_retranslate_results(results)
                if err:
                    messagebox.showerror(
                        "部分失败",
                        f"成功 {ok} 条, 失败 {len(err)} 条\n\n"
                        f"错误样本:\n" + "\n".join(err[:5]))
                else:
                    msg = f"✅ 成功更新 {ok} 条俄语翻译"
                    if report_path:
                        msg += f"\n\n报告已保存:\n{report_path}"
                    messagebox.showinfo("执行完成", msg)
                win.destroy()
            except Exception as e:
                import traceback
                messagebox.showerror("执行失败",
                                     f"{e}\n\n{traceback.format_exc()[:500]}")

        tk.Button(btn, text="✔ 执行覆盖", width=16,
                  font=("", 10, "bold"),
                  bg="#E8FFE8", activebackground="#C8FFC8",
                  relief="raised", bd=2,
                  command=on_execute).pack(side="right", padx=6)

    def _save_retranslate_report(self, results):
        if not _XLSX_OK:
            return None
        try:
            default_dir = Path(self.db_path_var.get()).parent
            report_path = default_dir / (
                f"retranslate_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
            wb = Workbook()
            ws = wb.active
            ws.title = "翻译对照"
            ws.append(["ID", "英文名", "原俄语翻译", "新俄语翻译",
                       "是否变化", "状态"])
            for r in results:
                ws.append([
                    r["id"], r["englishname"], r["old_rufanyi"],
                    r["new_rufanyi"], "√" if r["changed"] else "",
                    "成功" if r["new_rufanyi"] else "失败",
                ])
            wb.save(report_path)
            print(f"[F] 📄 报告已保存: {report_path}")
            return report_path
        except Exception as e:
            print(f"[F] ⚠️ 报告保存失败: {e}")
            return None

    def _write_retranslate_results(self, results):
        if not self._conn:
            return 0, ["数据库未连接"]

        db_path = Path(self.db_path_var.get().strip())
        backup = db_path.parent / (
            f"{db_path.stem}_preretrans_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        try:
            self._conn.commit()
            shutil.copy2(db_path, backup)
        except Exception as e:
            print(f"[F] ⚠️ 备份失败: {e}")

        cur = self._conn.cursor()
        ok = 0
        errors = []
        try:
            cur.execute("BEGIN")
            for r in results:
                if not r["new_rufanyi"]:
                    continue
                try:
                    cur.execute(
                        "UPDATE products SET rufanyi = ? WHERE id = ?",
                        (r["new_rufanyi"], r["id"]))
                    ok += cur.rowcount
                except Exception as e:
                    errors.append(f"ID {r['id']}: {str(e)[:60]}")
            self._conn.commit()

            id_map = {r["id"]: r["new_rufanyi"] for r in results}
            for row in self._all_rows:
                if row.get("id") in id_map:
                    row["rufanyi"] = id_map[row["id"]]
            self._render_page()
            self.set_status(f"✅ 二次翻译完成: 更新 {ok} 条 (备份: {backup.name})")
        except Exception as e:
            try:
                self._conn.rollback()
            except Exception:
                pass
            errors.append(str(e)[:100])

        return ok, errors