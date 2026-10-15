# tabs/tab_f/f_query.py
"""F 菜单 — 查询、筛选、排序、渲染、分页、相似度筛选"""
import re
import tkinter as tk
from tkinter import ttk, messagebox


class FQueryMixin:
    """查询/排序/渲染/分页/相似度"""

    # ============================================================
    #                    筛选条件
    # ============================================================
    def _add_condition(self):
        row = ttk.Frame(self.conditions_frame)
        row.pack(fill="x", pady=2)

        field_var = tk.StringVar(value=self.FIELDS[0][0])
        ttk.Combobox(
            row, textvariable=field_var, width=15, state="readonly",
            values=[f"{f[1]}({f[0]})" for f in self.FIELDS],
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
        """
        把条件列表转为 SQL WHERE
        """
        where_parts = []
        params = []

        for field_var, op_var, kw_var in conditions:
            field_str = field_var.get()
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

            # ============================================================
            # ★ 字符长度比较
            # ============================================================
            if op.startswith("字符长度"):
                if not kw:
                    continue
                try:
                    num = int(kw)
                except ValueError:
                    continue

                # SQL: LENGTH(field)
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

        # ★ 分离出需要 Python 过滤的条件
        py_filters = []  # [(field, op, kw), ...]
        sql_conditions = []  # 只保留 SQL 能处理的条件

        for field_var, op_var, kw_var, _ in self.conditions:
            field_str = field_var.get()
            field = (field_str.split("(")[-1].rstrip(")")
                     if "(" in field_str else field_str)
            op = op_var.get()
            kw = kw_var.get().strip()

            # ★ 需要 Python 端过滤的操作符
            if op in ("尺码跨度大于", "含半码"):
                py_filters.append((field, op, kw))
            else:
                sql_conditions.append((field_var, op_var, kw_var))

        # ---------- 1. SQL 查询（其他条件） ----------
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

        # ---------- 2. Python 端过滤（尺码跨度、含半码） ----------
        if py_filters:
            self._all_rows = self._apply_python_filters(
                self._all_rows, py_filters)

        # ---------- 3. 更新界面 ----------
        self._sort_column = None
        self._sort_reverse = False
        self._current_page = 1

        filter_note = ""
        if py_filters:
            filter_note = f" (含 {len(py_filters)} 个特殊筛选)"

        self.status_var.set(
            f"查询完成: {len(self._all_rows):,} 条{filter_note}")
        self._update_edit_scope()
        self._render_page()

    # ============================================================
    #   ★ Python 端过滤（尺码跨度、含半码）
    # ============================================================
    def _apply_python_filters(self, rows, py_filters):
        """对查询结果做 Python 端过滤"""
        result = rows

        for field, op, kw in py_filters:
            filtered = []

            for row in result:
                value = row.get(field, "") or ""

                if op == "尺码跨度大于":
                    if self._check_size_span(value, kw):
                        filtered.append(row)

                elif op == "含半码":
                    if self._check_has_half(value, kw):
                        filtered.append(row)

            result = filtered

        return result

    @staticmethod
    def _check_size_span(value, kw):
        """
        检查尺码跨度（相邻尺码差值）
        kw: 阈值，如 "1" 表示找差值 > 1 的
        """
        if not value or not kw:
            return False

        try:
            threshold = float(kw)
        except ValueError:
            return False

        # 解析尺码列表
        parts = [s.strip() for s in str(value).split(",") if s.strip()]
        if len(parts) < 2:
            return False

        nums = []
        for p in parts:
            try:
                nums.append(float(p))
            except ValueError:
                continue

        if len(nums) < 2:
            return False

        nums = sorted(set(nums))
        # 检查相邻差值
        for i in range(len(nums) - 1):
            diff = nums[i + 1] - nums[i]
            if diff > threshold + 0.01:  # 浮点容差
                return True

        return False

    @staticmethod
    def _check_has_half(value, kw):
        """
        检查是否含半码
        kw: "是" 或 "否" 或 留空（默认找有半码的）
        """
        if not value:
            has_half = False
        else:
            # 检查是否有 .5
            has_half = any(
                ".5" in s.strip()
                for s in str(value).split(",")
            )

        if kw in ("否", "no", "n", "0", "没有"):
            return not has_half
        else:
            # 默认找"含半码"的
            return has_half

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
        """渲染当前页（无 check 列）"""
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


    def _on_ctrl_a(self, event):
        """
        Ctrl+A：全选**当前页面**的复选框
        （不影响其他页面的勾选状态）
        """
        children = self.tree.get_children()
        if not children:
            return "break"

        try:
            page_size = int(self.page_size_var.get())
        except ValueError:
            page_size = 100

        start = (self._current_page - 1) * page_size

        for i, iid in enumerate(children):
            real_idx = start + i
            if 0 <= real_idx < len(self._all_rows):
                self._all_rows[real_idx]["_checked"] = True
                # 更新当前行显示
                values = list(self.tree.item(iid, "values"))
                if values:
                    values[0] = "☑"
                    self.tree.item(iid, values=values)

        self._update_checked_info()
        self.set_status(
            f"✅ 已全选当前页 ({len(children)} 行)")

        # ★ 阻止 Treeview 默认的全选行行为
        return "break"

    # ============================================================
    #   ★ 选中管理
    # ============================================================
    def _on_selection_changed(self, event):
        """选中变化时更新数量"""
        self._update_checked_info()

    def _on_ctrl_a(self, event):
        """Ctrl+A: 全选当前页所有行"""
        children = self.tree.get_children()
        if not children:
            return "break"

        self.tree.selection_set(children)
        self._update_checked_info()

        self.set_status(
            f"✅ 已选中当前页 {len(children)} 行")

        # 阻止 Treeview 默认行为
        return "break"

    def _update_checked_info(self):
        """更新"已选"数量（基于原生 selection）"""
        n = len(self.tree.selection())
        total = len(self.tree.get_children())
        self.checked_info_var.set(f"已选: {n} / {total}")

    def _get_selected_rows(self):
        """
        获取当前选中的行（返回 _all_rows 里的 dict 列表）
        供后续批量处理使用
        """
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

    def _update_checked_info(self):
        """更新已选数量"""
        n = sum(1 for r in self._all_rows if r.get("_checked", True))
        self.checked_info_var.set(f"已选: {n:,} / {len(self._all_rows):,}")

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