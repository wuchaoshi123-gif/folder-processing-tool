# tabs/tab_f/f_edit.py
"""F 菜单 — 批量修改 + 删除记录"""
import re
import shutil
import tkinter as tk
from pathlib import Path
from datetime import datetime
from tkinter import ttk, messagebox


class FEditMixin:
    """批量修改 + 删除"""

    def _update_edit_scope(self):
        n = len(self._all_rows)
        self.edit_scope_var.set(f"影响范围: {n:,} 条 (当前查询结果)")
        if hasattr(self, "retrans_scope_var"):
            has_en = sum(1 for r in self._all_rows
                         if (r.get("englishname") or "").strip())
            self.retrans_scope_var.set(
                f"影响范围: {n:,} 条, 其中有英文名 {has_en:,} 条")

    def _get_edit_params(self):
        field_str = self.edit_field_var.get()
        field = (field_str.split("(")[-1].rstrip(")")
                 if "(" in field_str else field_str)
        mode = self.edit_mode_var.get()
        find = self.edit_find_var.get()
        replace = self.edit_replace_var.get()

        valid_fields = [f[0] for f in self.EDITABLE_FIELDS]
        if field not in valid_fields:
            messagebox.showerror("字段错误", f"字段 '{field}' 不允许修改")
            return None
        return field, mode, find, replace

    def _apply_replace(self, value, mode, find, replace):
        if value is None:
            value = ""
        value = str(value)
        try:
            if mode == "包含替换":
                if find in value:
                    return value.replace(find, replace)
            elif mode == "精确匹配":
                if value == find:
                    return replace
            elif mode == "正则替换":
                new_val, cnt = re.subn(find, replace, value)
                if cnt > 0:
                    return new_val
            elif mode == "前缀匹配":
                if value.startswith(find):
                    return replace + value[len(find):]
            elif mode == "后缀匹配":
                if value.endswith(find):
                    return value[:-len(find)] + replace if find else value
        except Exception:
            return None
        return None

    def _preview_batch_edit(self):
        if not self._all_rows:
            messagebox.showinfo("提示", "请先查询出结果")
            return
        params = self._get_edit_params()
        if not params:
            return
        field, mode, find, replace = params
        if not find and mode != "正则替换":
            messagebox.showwarning("提示", "请输入查找内容")
            return

        changes = []
        for row in self._all_rows:
            old_val = row.get(field)
            new_val = self._apply_replace(old_val, mode, find, replace)
            if new_val is not None and new_val != old_val:
                changes.append((row.get("id"), old_val, new_val))

        if not changes:
            messagebox.showinfo("预览", "没有匹配的记录")
            return
        self._show_preview_dialog(field, mode, find, replace, changes)

    def _show_preview_dialog(self, field, mode, find, replace, changes):
        win = tk.Toplevel(self.app.root)
        win.title("修改预览")
        win.geometry("900x600")
        win.transient(self.app.root)

        info = ttk.Frame(win, padding=8)
        info.pack(fill="x")
        ttk.Label(info, text=f"目标字段: {field}",
                  font=("", 10, "bold")).pack(anchor="w")
        ttk.Label(info, text=f"匹配模式: {mode}",
                  foreground="#004080").pack(anchor="w")
        ttk.Label(info, text=f"查找内容: {find!r}",
                  foreground="#804000").pack(anchor="w")
        ttk.Label(info, text=f"替换为:   {replace!r}",
                  foreground="#008000").pack(anchor="w")
        ttk.Label(info, text=f"★ 将修改 {len(changes):,} 条记录",
                  foreground="#C00000",
                  font=("", 11, "bold")).pack(anchor="w", pady=(6, 0))

        preview_frame = ttk.LabelFrame(win, text=" 前 30 条预览 ", padding=4)
        preview_frame.pack(fill="both", expand=True, padx=8, pady=4)

        tree = ttk.Treeview(preview_frame, columns=("id", "old", "new"),
                            show="headings")
        tree.heading("id", text="ID")
        tree.heading("old", text="旧值")
        tree.heading("new", text="新值")
        tree.column("id", width=80, anchor="center")
        tree.column("old", width=350, anchor="w")
        tree.column("new", width=350, anchor="w")

        vsb = ttk.Scrollbar(preview_frame, orient="vertical",
                            command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for rid, old, new in changes[:30]:
            tree.insert("", "end", values=(rid, str(old)[:80], str(new)[:80]))

        btn = ttk.Frame(win, padding=8)
        btn.pack(fill="x")
        if len(changes) > 30:
            ttk.Label(btn, text=f"... 还有 {len(changes)-30} 条未显示",
                      foreground="#888").pack(side="left")

        ttk.Button(btn, text="取消",
                   command=win.destroy).pack(side="right", padx=4)
        ttk.Button(btn, text="✔ 确认执行修改",
                   command=lambda: (win.destroy(),
                                    self._do_execute_batch_edit(
                                        field, mode, find, replace, changes))
                   ).pack(side="right", padx=4)

    def _execute_batch_edit(self):
        if not self._all_rows:
            messagebox.showinfo("提示", "请先查询出结果")
            return
        params = self._get_edit_params()
        if not params:
            return
        field, mode, find, replace = params
        if not find and mode != "正则替换":
            messagebox.showwarning("提示", "请输入查找内容")
            return

        changes = []
        for row in self._all_rows:
            old_val = row.get(field)
            new_val = self._apply_replace(old_val, mode, find, replace)
            if new_val is not None and new_val != old_val:
                changes.append((row.get("id"), old_val, new_val))

        if not changes:
            messagebox.showinfo("提示", "没有匹配的记录")
            return
        if not messagebox.askyesno(
            "确认修改",
            f"将修改 {len(changes):,} 条记录\n\n"
            f"目标字段: {field}\n匹配模式: {mode}\n"
            f"查找: {find!r}\n替换为: {replace!r}\n\n"
            f"⚠️ 建议先备份数据库。\n\n确定继续?"):
            return
        self._do_execute_batch_edit(field, mode, find, replace, changes)

    def _do_execute_batch_edit(self, field, mode, find, replace, changes):
        if not self._conn:
            messagebox.showerror("错误", "数据库未连接")
            return

        db_path = Path(self.db_path_var.get().strip())
        backup_path = db_path.parent / (
            f"{db_path.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        try:
            shutil.copy2(db_path, backup_path)
            print(f"[F] 数据库备份: {backup_path}")
        except Exception as e:
            print(f"[F] 备份失败: {e}")
            if not messagebox.askyesno("备份失败",
                                       f"无法备份: {e}\n\n仍要继续?"):
                return

        t0 = datetime.now()
        try:
            cur = self._conn.cursor()
            cur.execute("BEGIN")
            update_count = 0
            for rid, old, new in changes:
                cur.execute(
                    f"UPDATE products SET {field} = ? WHERE id = ?",
                    (new, rid))
                update_count += cur.rowcount
            self._conn.commit()

            elapsed = (datetime.now() - t0).total_seconds()
            change_map = {rid: new for rid, _, new in changes}
            for row in self._all_rows:
                if row.get("id") in change_map:
                    row[field] = change_map[row["id"]]

            self._render_page()
            self.status_var.set(
                f"✅ 修改完成: {update_count} 条 (备份: {backup_path.name})")
            messagebox.showinfo(
                "修改成功",
                f"成功修改 {update_count} 条记录\n\n"
                f"耗时: {elapsed:.2f}s\n备份: {backup_path}")
        except Exception as e:
            try:
                self._conn.rollback()
            except Exception:
                pass
            messagebox.showerror("修改失败", str(e))

    # ============================================================
    #                    删除选中记录
    # ============================================================
    def _delete_selected_rows(self):
        sel = self.tree.selection()
        if not sel:
            if self._right_click_row_id:
                sel = (self._right_click_row_id,)
            else:
                messagebox.showinfo("提示", "请先选中要删除的记录")
                return

        rows_to_delete = []
        for row_id in sel:
            row = self._get_row_by_id(row_id)
            if row:
                rows_to_delete.append(row)

        if not rows_to_delete:
            messagebox.showinfo("提示", "无可删除的记录")
            return

        n = len(rows_to_delete)
        preview_lines = [f"  · {r.get('onlymulu', '')[:60]}"
                         for r in rows_to_delete[:10]]
        if n > 10:
            preview_lines.append(f"  ... 还有 {n - 10} 条")
        preview_text = "\n".join(preview_lines)

        if not messagebox.askyesno(
            "确认删除",
            f"⚠️ 将从数据库中永久删除 {n:,} 条记录\n\n"
            f"{preview_text}\n\n"
            f"此操作不可撤销（但会自动备份数据库）。\n\n确定继续?"):
            return

        db_path = Path(self.db_path_var.get().strip())
        backup = db_path.parent / (
            f"{db_path.stem}_predelete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        try:
            if self._conn:
                self._conn.commit()
            shutil.copy2(db_path, backup)
            print(f"[F] 数据库已备份: {backup.name}")
        except Exception as e:
            print(f"[F] ⚠️ 备份失败: {e}")
            if not messagebox.askyesno("备份失败",
                                       f"无法备份数据库:\n{e}\n\n仍要继续删除?"):
                return

        cur = self._conn.cursor()
        deleted = 0
        errors = []
        try:
            cur.execute("BEGIN")
            for r in rows_to_delete:
                rid = r.get("id")
                om = r.get("onlymulu")
                try:
                    if rid is not None:
                        cur.execute("DELETE FROM products WHERE id = ?", (rid,))
                    elif om:
                        cur.execute("DELETE FROM products WHERE onlymulu = ?", (om,))
                    deleted += cur.rowcount
                except Exception as e:
                    errors.append(f"ID {rid}: {str(e)[:60]}")
            self._conn.commit()

            delete_ids = set()
            delete_onlymulu = set()
            for r in rows_to_delete:
                if r.get("id") is not None:
                    delete_ids.add(r["id"])
                if r.get("onlymulu"):
                    delete_onlymulu.add(r["onlymulu"])

            self._all_rows = [
                row for row in self._all_rows
                if row.get("id") not in delete_ids
                and row.get("onlymulu") not in delete_onlymulu
            ]
            self._current_page = 1
            self._render_page()
            self._update_edit_scope()
            self._update_retrans_scope()

            msg = f"✅ 已成功删除 {deleted} 条记录"
            if errors:
                msg += f"\n\n⚠️ {len(errors)} 条删除失败:\n"
                msg += "\n".join(errors[:5])
            msg += f"\n\n备份: {backup.name}"

            messagebox.showinfo("删除完成", msg)
            self.set_status(f"✅ 已删除 {deleted} 条")
        except Exception as e:
            try:
                self._conn.rollback()
            except Exception:
                pass
            messagebox.showerror("删除失败", str(e))