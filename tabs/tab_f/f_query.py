# tabs/tab_f/f_query.py
"""F 菜单 — 查询、筛选、排序、渲染、分页、相似度筛选"""
import re
import tkinter as tk
from tkinter import ttk, messagebox

# ★ 尺码派生字段工具
from .f_size_filter import (
    is_size_field,
    LEGACY_SIZE_OPS,
    evaluate_row_condition,
)


class FQueryMixin:
    """查询/排序/渲染/分页/相似度"""

    # ============================================================
    #                    筛选条件
    # ============================================================
    def _add_condition(self):
        row = ttk.Frame(self.conditions_frame)
        row.pack(fill="x", pady=2)

        # ★ 字段下拉：真实字段 + 分隔线 + 尺码派生字段
        SEP = self.FIELD_SEP  # 见 f_main.py 新增常量
        real_items = [f"{f[1]}({f[0]})" for f in self.FIELDS]
        derived_items = [
            f"{f[1]}({f[0]})"
            for f in self.FILTER_FIELDS[len(self.FIELDS):]
        ]
        field_values = real_items + [SEP] + derived_items

        field_var = tk.StringVar(value=self.FIELDS[0][0])
        ttk.Combobox(
            row, textvariable=field_var, width=22, state="readonly",
            values=field_values, height=25,  # ★ 一次显示 25 行
        ).pack(side="left", padx=2)

        op_var = tk.StringVar(value="包含")
        ttk.Combobox(
            row, textvariable=op_var, width=12, state="readonly",
            values=self.OPERATORS,
        ).pack(side="left", padx=2)

        kw_var = tk.StringVar()
        ttk.Entry(row, textvariable=kw_var, width=30).pack(
            side="left", padx=2, fill="x", expand=True)

        def remove():
            for i, it in enumerate(self.conditions):
                if it[3] is row:
                    self.conditions.pop(i)
                    break
            row.destroy()

        ttk.Button(row, text="✖", width=3, command=remove).pack(
            side="left", padx=2)

        self.conditions.append((field_var, op_var, kw_var, row))

    def _clear_conditions(self):
        for item in self.conditions:
            item[3].destroy()
        self.conditions = []

    def _collect_conditions(self):
        """对外接口（保持兼容）"""
        return self._collect_conditions_from_list(self.conditions)

    def _collect_conditions_from_list(self, conditions):
        """把条件列表转为 SQL WHERE（只处理 SQL 可处理的条件）"""
        where_parts = []
        params = []

        for field_var, op_var, kw_var in conditions:
            field_str = field_var.get()
            if field_str == "──────────────":  # ★ 跳过分隔线
                continue
            field = (field_str.split("(")[-1].rstrip(")")
                     if "(" in field_str else field_str)
            op = op_var.get()
            kw = kw_var.get().strip()

            # 值个数比较
            if op.startswith("值个数"):
                if not kw:
                    continue
                try:
                    num = int(kw)
                except ValueError:
                    continue

                count_expr = (
                    f"(CASE WHEN {field} IS NULL OR {field} = '' THEN 0 "
                    f"ELSE LENGTH({field}) - LENGTH(REPLACE({field}, ',', '')) + 1 "
                    f"END)"
                )

                if op == "值个数小于":
                    where_parts.append(f"{count_expr} < ?")
                    params.append(num)
                elif op == "值个数等于":
                    where_parts.append(f"{count_expr} = ?")
                    params.append(num)
                elif op == "值个数大于":
                    where_parts.append(f"{count_expr} > ?")
                    params.append(num)
                elif op == "值个数小于等于":
                    where_parts.append(f"{count_expr} <= ?")
                    params.append(num)
                elif op == "值个数大于等于":
                    where_parts.append(f"{count_expr} >= ?")
                    params.append(num)
                continue

            # 字符长度比较
            if op.startswith("字符长度"):
                if not kw:
                    continue
                try:
                    num = int(kw)
                except ValueError:
                    continue

                if op == "字符长度小于":
                    where_parts.append(f"LENGTH({field}) < ?")
                    params.append(num)
                elif op == "字符长度等于":
                    where_parts.append(f"LENGTH({field}) = ?")
                    params.append(num)
                elif op == "字符长度大于":
                    where_parts.append(f"LENGTH({field}) > ?")
                    params.append(num)
                elif op == "字符长度小于等于":
                    where_parts.append(f"LENGTH({field}) <= ?")
                    params.append(num)
                elif op == "字符长度大于等于":
                    where_parts.append(f"LENGTH({field}) >= ?")
                    params.append(num)
                continue

            # 空判断
            if op == "为空":
                where_parts.append(f"({field} IS NULL OR {field} = '')")
                continue
            if op == "不为空":
                where_parts.append(f"({field} IS NOT NULL AND {field} != '')")
                continue
            if not kw:
                continue

            # 比较操作
            if op == "包含":
                where_parts.append(f"{field} LIKE ?")
                params.append(f"%{kw}%")
            elif op == "等于":
                where_parts.append(f"{field} = ?")
                params.append(kw)
            elif op == "不包含":
                where_parts.append(f"{field} NOT LIKE ?")
                params.append(f"%{kw}%")
            elif op == "不等于":
                where_parts.append(f"{field} != ?")
                params.append(kw)
            elif op == "大于":
                where_parts.append(f"{field} > ?")
                params.append(kw)
            elif op == "小于":
                where_parts.append(f"{field} < ?")
                params.append(kw)
            elif op == "大于等于":
                where_parts.append(f"{field} >= ?")
                params.append(kw)
            elif op == "小于等于":
                where_parts.append(f"{field} <= ?")
                params.append(kw)

        return where_parts, params

    # ============================================================
    #                    查询
    # ============================================================
    def _do_query(self):
        if not self._conn:
            self._refresh_db()
            if not self._conn:
                return

        # ★ 分离条件
        py_filters = []       # [(field, op, kw), ...] 尺码派生字段 / 老操作符
        sql_conditions = []   # [(field_var, op_var, kw_var), ...]

        for field_var, op_var, kw_var, _ in self.conditions:
            field_str = field_var.get()
            if field_str == "──────────────":
                continue
            field = (field_str.split("(")[-1].rstrip(")")
                     if "(" in field_str else field_str)
            op = op_var.get()
            kw = kw_var.get().strip()

            # 新的尺码虚拟字段 或 老的兼容操作符 → Python 端过滤
            if is_size_field(field) or op in LEGACY_SIZE_OPS:
                py_filters.append((field, op, kw))
            else:
                sql_conditions.append((field_var, op_var, kw_var))

        # ---------- 1. SQL 查询 ----------
        where_parts, params = self._collect_conditions_from_list(sql_conditions)
        logic = self.logic_var.get() or "AND"

        sql = "SELECT * FROM products"
        if where_parts:
            sql += " WHERE " + f" {logic} ".join(where_parts)
        sql += " ORDER BY id DESC"

        try:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            self._all_rows = [dict(r) for r in rows]
        except Exception as e:
            messagebox.showerror("查询失败", str(e))
            return

        # ---------- 2. Python 端过滤 ----------
        warn = ""
        if py_filters:
            has_sql = bool(sql_conditions)
            if logic == "OR" and has_sql:
                warn = " ⚠️ OR 混合筛选(PY端按AND)"
            self._all_rows = self._apply_python_filters(
                self._all_rows, py_filters,
                logic=logic, has_sql_conditions=has_sql)

        # ---------- 3. 更新界面 ----------
        self._sort_column = None
        self._sort_reverse = False
        self._current_page = 1

        note = f" (含 {len(py_filters)} 个尺码筛选)" if py_filters else ""
        self.status_var.set(
            f"查询完成: {len(self._all_rows):,} 条{note}{warn}")
        self._update_edit_scope()
        self._render_page()

    # ============================================================
    #   ★ Python 端过滤（尺码派生字段）
    # ============================================================
    def _apply_python_filters(self, rows, py_filters,
                              logic="AND", has_sql_conditions=False):
        """
        rows:         list[dict]
        py_filters:   [(field, op, kw), ...]
        logic:        "AND" / "OR"
        has_sql_conditions: 是否同时存在 SQL 条件（用于 OR 降级）
        返回过滤后的 list[dict]
        """
        if not py_filters:
            return rows

        # 只有纯 Python 条件时才按用户逻辑 OR；混合场景下 PY 端统一 AND
        # （混合 OR 已在状态栏提示）
        use_or = (logic == "OR" and not has_sql_conditions)

        result = []
        for row in rows:
            flags = [evaluate_row_condition(row, f, o, k)
                     for f, o, k in py_filters]
            ok = any(flags) if use_or else all(flags)
            if ok:
                result.append(row)
        return result

    def _show_all(self):
        if not self._conn:
            return
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM products ORDER BY id DESC")
            rows = cur.fetchall()
            self._all_rows = [dict(r) for r in rows]

            self._sort_column = None
            self._sort_reverse = False
            self._current_page = 1
            self.status_var.set(f"已加载全部: {len(self._all_rows):,} 条")
            self._update_edit_scope()
            self._render_page()
        except Exception as e:
            messagebox.showerror("错误", str(e))

    # ============================================================
    #                    排序
    # ============================================================
    def _sort_by_column(self, column):
        if not self._all_rows:
            return

        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False

        field_type = "text"
        for fname, _, ftype in self.FIELDS:
            if fname == column:
                field_type = ftype
                break

        def sort_key(row):
            val = row.get(column)
            if val is None or val == "":
                return (1, "") if field_type == "text" else (1, 0)
            if field_type == "int":
                try:
                    return (0, int(val))
                except (ValueError, TypeError):
                    return (1, 0)
            return (0, str(val).lower())

        self._all_rows.sort(key=sort_key, reverse=self._sort_reverse)

        for fname, fdisp, _ in self.FIELDS:
            arrow = ""
            if fname == column:
                arrow = " ▼" if self._sort_reverse else " ▲"
            self.tree.heading(fname, text=fdisp + arrow)

        self._current_page = 1
        self._render_page()

    # ============================================================
    #                    渲染
    # ============================================================
    def _render_page(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self._all_rows:
            self.result_info_var.set("无结果")
            self.page_info_var.set("0 / 0")
            self.checked_info_var.set("已选: 0")
            return

        try:
            page_size = int(self.page_size_var.get())
        except ValueError:
            page_size = 100

        total_pages = max(1, (len(self._all_rows) + page_size - 1) // page_size)
        if self._current_page < 1:
            self._current_page = 1
        if self._current_page > total_pages:
            self._current_page = total_pages

        start = (self._current_page - 1) * page_size
        end = start + page_size
        page_rows = self._all_rows[start:end]

        for row in page_rows:
            values = []
            for fname, _, _ in self.FIELDS:
                v = row.get(fname, "")
                if v is None:
                    v = ""
                if fname in ("local_url", "web_url"):
                    v = str(v).replace("\n", " ")[:100]
                elif fname == "englishname":
                    v = str(v)[:150]
                elif fname == "rufanyi":
                    v = str(v)[:100]
                elif fname == "bandsizechart":
                    v = str(v)[:80]
                values.append(str(v))
            self.tree.insert("", "end", values=values)

        self.result_info_var.set(f"共 {len(self._all_rows):,} 条记录")
        self.page_info_var.set(f"{self._current_page} / {total_pages}")
        self._update_checked_info()

    # ============================================================
    #   ★ 选中管理（去重，保留原生 selection 版本）
    # ============================================================
    def _on_ctrl_a(self, event):
        """Ctrl+A: 全选当前页所有行"""
        children = self.tree.get_children()
        if not children:
            return "break"

        self.tree.selection_set(children)
        self._update_checked_info()

        self.set_status(
            f"✅ 已选中当前页 {len(children)} 行")

        return "break"

    def _on_selection_changed(self, event):
        """选中变化时更新数量"""
        self._update_checked_info()

    def _update_checked_info(self):
        """更新已选数量（基于原生 selection）"""
        n = len(self.tree.selection())
        total = len(self.tree.get_children())
        self.checked_info_var.set(f"已选: {n} / {total}")

    def _get_selected_rows(self):
        """获取当前选中的行（返回 _all_rows 里的 dict 列表）"""
        sel = self.tree.selection()
        if not sel:
            return []

        try:
            page_size = int(self.page_size_var.get())
        except ValueError:
            page_size = 100

        start = (self._current_page - 1) * page_size

        result = []
        for iid in sel:
            idx = self.tree.index(iid)
            real_idx = start + idx
            if 0 <= real_idx < len(self._all_rows):
                result.append(self._all_rows[real_idx])

        return result

    def _reset_page(self):
        self._current_page = 1
        self._render_page()

    def _prev_page(self):
        if self._current_page > 1:
            self._current_page -= 1
            self._render_page()

    def _next_page(self):
        try:
            page_size = int(self.page_size_var.get())
        except ValueError:
            page_size = 100
        total_pages = max(1, (len(self._all_rows) + page_size - 1) // page_size)
        if self._current_page < total_pages:
            self._current_page += 1
            self._render_page()

    # ============================================================
    #                    相似度筛选
    # ============================================================
    def _filter_by_similarity(self):
        if not self._all_rows:
            messagebox.showinfo("提示", "请先查询出结果")
            return

        try:
            threshold = float(self.sim_threshold_var.get())
        except ValueError:
            messagebox.showwarning("提示", "请输入有效的数字 (0-100)")
            return
        if not (0 <= threshold <= 100):
            messagebox.showwarning("提示", "阈值必须在 0-100 之间")
            return

        algorithm = self.sim_algorithm_var.get()
        import difflib

        def latin_ratio(text):
            letters = re.findall(r'[a-zA-Z\u0400-\u04FF]', text)
            if not letters:
                return 0.0
            latin = sum(1 for c in letters if c.isascii())
            return latin / len(letters) * 100

        def char_similarity(a, b):
            if not a or not b:
                return 0.0
            a_norm = " ".join(a.lower().split())
            b_norm = " ".join(b.lower().split())
            return difflib.SequenceMatcher(None, a_norm, b_norm).ratio() * 100

        matched = []
        all_with_sim = []
        for row in self._all_rows:
            en = (row.get("englishname") or "").strip()
            ru = (row.get("rufanyi") or "").strip()
            if not en or not ru:
                row["_similarity"] = 0.0
                continue
            sim = (latin_ratio(ru) if algorithm == "latin"
                   else char_similarity(en, ru))
            sim = round(sim, 2)
            row["_similarity"] = sim
            all_with_sim.append(sim)
            if sim >= threshold:
                matched.append(row)

        self._all_rows = matched
        self._current_page = 1
        self._sort_column = None
        self._sort_reverse = False
        self._render_page()

        algo_label = "拉丁占比" if algorithm == "latin" else "字符相似"
        avg_sim = sum(all_with_sim) / len(all_with_sim) if all_with_sim else 0
        self.sim_scope_var.set(
            f"已筛选: {len(matched):,} 条 (阈值≥{threshold}%, "
            f"{algo_label}, 均值 {avg_sim:.1f}%)")
        self.status_var.set(
            f"相似度筛选: {len(matched):,} 条 (阈值≥{threshold}%)")
        self._update_edit_scope()
        self._update_retrans_scope()

        if matched:
            messagebox.showinfo(
                "筛选完成",
                f"找到 {len(matched):,} 条相似度 ≥ {threshold}% 的记录\n\n"
                f"这些记录的俄语翻译可能未生效。")
        else:
            messagebox.showinfo(
                "无结果",
                f"没有相似度 ≥ {threshold}% 的记录")