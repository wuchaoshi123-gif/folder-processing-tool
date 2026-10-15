# tabs/tab_f/f_context.py
"""F 菜单 — 右键菜单 + 复制功能"""
import json
import tkinter as tk


class FContextMixin:
    """右键菜单"""

    def _setup_context_menu(self):
        """在 _build_ui 里调用 — 初始化右键菜单"""
        self._ctx_menu = tk.Menu(self.tree, tearoff=0)
        self._ctx_menu.add_command(label="📋 复制单元格内容",
                                   command=self._copy_selected_cell)
        self._ctx_menu.add_command(label="📄 复制整行（制表符分隔）",
                                   command=self._copy_selected_row)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="📊 复制本列全部",
                                   command=self._copy_column_all)
        self._ctx_menu.add_command(label="📑 复制选中行全部",
                                   command=self._copy_selected_rows)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="📦 复制所有字段（JSON）",
                                   command=self._copy_row_json)
        self._ctx_menu.add_command(label="🔗 复制网络URL（当前行）",
                                   command=self._copy_web_url)
        self._ctx_menu.add_command(label="📁 复制本地URL（当前行）",
                                   command=self._copy_local_url)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="✔ 复制所有可见行（换行分隔）",
                                   command=self._copy_all_visible)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="🗑️ 删除选中记录",
                                   command=self._delete_selected_rows,
                                   foreground="#C00000")

        self.tree.bind("<Button-3>", self._on_tree_right_click)
        self.tree.bind("<Button-2>", self._on_tree_right_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        self._right_click_row_id = None
        self._right_click_col = None

    def _on_tree_right_click(self, event):
        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_id:
            return
        self._right_click_row_id = row_id
        try:
            self._right_click_col = int(col_id.replace("#", "")) - 1
        except ValueError:
            self._right_click_col = 0

        if row_id not in self.tree.selection():
            self.tree.selection_set(row_id)

        idx = self.tree.index(row_id)
        if 0 <= idx < len(self._all_rows):
            row_data = self._all_rows[idx]
            has_url = bool((row_data.get("web_url") or "").strip())
            self._ctx_menu.entryconfig("🔗 复制网络URL（当前行）",
                                       state="normal" if has_url else "disabled")
            self._ctx_menu.entryconfig("📁 复制本地URL（当前行）",
                                       state="normal" if has_url else "disabled")

        try:
            self._ctx_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._ctx_menu.grab_release()

    def _on_tree_double_click(self, event):
        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_id:
            return
        self._right_click_row_id = row_id
        try:
            self._right_click_col = int(col_id.replace("#", "")) - 1
        except ValueError:
            return
        self._copy_selected_cell()

    def _get_row_by_id(self, row_id):
        if not row_id:
            return None
        try:
            idx = self.tree.index(row_id)
        except Exception:
            return None
        if 0 <= idx < len(self._all_rows):
            return self._all_rows[idx]
        return None

    def _copy_to_clipboard(self, text):
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(text)

    def _copy_selected_cell(self):
        row = self._get_row_by_id(self._right_click_row_id)
        if not row:
            return
        col_idx = self._right_click_col
        if col_idx is None or col_idx < 0 or col_idx >= len(self.FIELDS):
            return
        field_name = self.FIELDS[col_idx][0]
        value = row.get(field_name, "") or ""
        self._copy_to_clipboard(str(value))
        self.set_status(f"✅ 已复制单元格 [{self.FIELDS[col_idx][1]}]")

    def _copy_selected_row(self):
        row = self._get_row_by_id(self._right_click_row_id)
        if not row:
            return
        parts = [str(row.get(f[0], "") or "") for f in self.FIELDS]
        self._copy_to_clipboard("\t".join(parts))
        self.set_status(f"✅ 已复制整行")

    def _copy_column_all(self):
        if self._right_click_col is None:
            return
        col_idx = self._right_click_col
        if col_idx < 0 or col_idx >= len(self.FIELDS):
            return
        field_name = self.FIELDS[col_idx][0]
        field_label = self.FIELDS[col_idx][1]
        values = [str(r.get(field_name, "") or "") for r in self._all_rows]
        self._copy_to_clipboard("\n".join(values))
        self.set_status(f"✅ 已复制列 [{field_label}] {len(values)} 个值")

    def _copy_selected_rows(self):
        sel = self.tree.selection()
        if not sel:
            return
        lines = ["\t".join(f[1] for f in self.FIELDS)]
        for row_id in sel:
            row = self._get_row_by_id(row_id)
            if row:
                lines.append("\t".join(str(row.get(f[0], "") or "")
                                       for f in self.FIELDS))
        self._copy_to_clipboard("\n".join(lines))
        self.set_status(f"✅ 已复制 {len(sel)} 行")

    def _copy_row_json(self):
        row = self._get_row_by_id(self._right_click_row_id)
        if not row:
            return
        clean = {k: v for k, v in row.items() if not k.startswith("_")}
        self._copy_to_clipboard(json.dumps(clean, ensure_ascii=False, indent=2))
        self.set_status(f"✅ 已复制 JSON")

    def _copy_web_url(self):
        row = self._get_row_by_id(self._right_click_row_id)
        if not row:
            return
        url = row.get("web_url") or ""
        self._copy_to_clipboard(url)
        self.set_status(f"✅ 已复制网络URL")

    def _copy_local_url(self):
        row = self._get_row_by_id(self._right_click_row_id)
        if not row:
            return
        url = row.get("local_url") or ""
        self._copy_to_clipboard(url)
        self.set_status(f"✅ 已复制本地URL")

    def _copy_all_visible(self):
        values = [str(r.get("onlymulu", "") or "") for r in self._all_rows]
        self._copy_to_clipboard("\n".join(values))
        self.set_status(f"✅ 已复制 {len(values)} 个唯一目录")