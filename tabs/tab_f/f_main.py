# tabs/tab_f/f_main.py
"""F 菜单主类 — 常量 + UI 构建 + 数据库连接"""
import os
import json
import tkinter as tk
from pathlib import Path
from datetime import datetime
from tkinter import ttk, messagebox, filedialog
import sqlite3
from ..base_tab import BaseTab

# ★ 尺码派生字段（用于筛选，不进入表格）
from .f_size_filter import SIZE_DERIVED_FIELDS  # noqa: F401

# ★ 列宽配置文件（用户 APPDATA）
APP_NAME = "FolderProcessingTool"
AUTO_CFG_DIR = Path(os.getenv("APPDATA", Path.home())) / APP_NAME
AUTO_CFG_DIR.mkdir(parents=True, exist_ok=True)
COL_WIDTH_PATH = AUTO_CFG_DIR / "tab_f_col_widths.json"

# xlsx 支持
try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.utils import get_column_letter
    _XLSX_OK = True
except ImportError:
    _XLSX_OK = False

# 导入所有 Mixin
from .f_xlsx import FXlsxMixin
from .f_query import FQueryMixin
from .f_edit import FEditMixin
from .f_retrans import FRetransMixin
from .f_context import FContextMixin


class TabF(FXlsxMixin, FQueryMixin, FEditMixin, FRetransMixin,
           FContextMixin, BaseTab):
    TAB_NAME = "F 整理数据"
    TAB_KEY = "F"

    # ============================================================
    #   常量
    # ============================================================
    DEFAULT_COL_WIDTHS = {
        "id":            15,
        "nums":          15,
        "onlymulu":      35,
        "englishname":   45,
        "bands":         15,
        "shoessize":     25,
        "chuprice":      12,
        "images":        12,
        "rufanyi":       30,
        "web_url":       35,
        "bandsizechart": 30,
        "created_at":    20,
    }
    COL_WIDTH_UNIT = 8

    XLSX_COLUMNS = [
        "nums", "onlymulu", "englishname", "local_url", "web_url", "rufanyi",
        "shoessize", "chuprice", "images", "bands",
        "bandsizechart", "source_dir", "created_at",
    ]
    XLSX_HEADERS = [
        "编号", "唯一目录", "英文名称", "本地URL", "网络URL", "俄语翻译",
        "尺码", "价格", "图片数", "品牌",
        "尺码表", "源目录", "入库时间",
    ]

    # ★ 表格列（真实字段）
    FIELDS = [
        ("id", "ID", "int"),
        ("nums", "编号", "int"),
        ("onlymulu", "唯一目录", "text"),
        ("englishname", "英文名称", "text"),
        ("bands", "品牌", "text"),
        ("shoessize", "尺码", "text"),
        ("chuprice", "价格", "int"),
        ("images", "图片数", "int"),
        ("rufanyi", "俄语翻译", "text"),
        ("web_url", "网络URL", "text"),
        ("bandsizechart", "尺码表", "text"),
        ("created_at", "入库时间", "text"),

    ]
    
    FIELD_SEP = "----------"
    # ★ 筛选字段（真实字段 + 尺码派生字段）
    #   注意：派生字段仅用于筛选，不进入表格渲染
    FILTER_FIELDS = FIELDS + [
        ("size_first",    "尺码首值", "float"),
        ("size_last",     "尺码末值", "float"),
        ("size_span",     "尺码差值", "float"),
        ("size_count",    "尺码个数", "int"),
        ("size_has_half", "含半码",  "int"),
    ]

    EDITABLE_FIELDS = [
        ("bands", "品牌"),
        ("shoessize", "尺码"),
        ("chuprice", "价格"),
        ("images", "图片数"),
        ("rufanyi", "俄语翻译"),
        ("englishname", "英文名称"),
        ("web_url", "网络URL"),
        ("local_url", "本地URL"),
        ("bandsizechart", "尺码表"),
        ("onlymulu", "唯一目录"),
        ("nums", "编号"),
    ]

    OPERATORS = [
        "包含", "等于", "不包含", "不等于",
        "大于", "小于", "大于等于", "小于等于",
        "为空", "不为空",
        "值个数小于", "值个数等于", "值个数大于",
        "值个数小于等于", "值个数大于等于",
        "尺码跨度大于", "含半码",
        "字符长度小于", "字符长度等于", "字符长度大于",
        "字符长度小于等于", "字符长度大于等于",
    ]

    REPLACE_MODES = [
        "包含替换", "精确匹配", "正则替换", "前缀匹配", "后缀匹配",
    ]

    PAGE_SIZES = [50, 100, 200, 500, 1000, 2000]

    TABLE_SCHEMA = """
        CREATE TABLE IF NOT EXISTS products (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nums            INTEGER,
            onlymulu        TEXT NOT NULL,
            local_url       TEXT,
            web_url         TEXT,
            rufanyi         TEXT,
            shoessize       TEXT,
            chuprice        INTEGER,
            images          INTEGER,
            bands           TEXT,
            bandsizechart   TEXT,
            source_dir      TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_onlymulu ON products(onlymulu);
        CREATE INDEX IF NOT EXISTS idx_bands ON products(bands);
        CREATE INDEX IF NOT EXISTS idx_chuprice ON products(chuprice);
        CREATE INDEX IF NOT EXISTS idx_created ON products(created_at);

        CREATE TABLE IF NOT EXISTS failed_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            onlymulu        TEXT,
            reason          TEXT,
            detail          TEXT,
            created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_failed_om ON failed_items(onlymulu);
    """

    # ============================================================
    #                    UI 构建
    # ============================================================
    def _build_ui(self):
        self._load_col_widths()
        self._build_section_data_source()
        self._build_section_xlsx_io()

        grid_frame = ttk.Frame(self)
        grid_frame.pack(fill="x", padx=6, pady=(0, 4))
        grid_frame.columnconfigure(0, weight=1, uniform="f_col")
        grid_frame.columnconfigure(1, weight=1, uniform="f_col")

        self._build_section_filter(grid_frame, row=0, column=0)
        self._build_section_batch_edit(grid_frame, row=0, column=1)
        self._build_section_similarity(grid_frame, row=1, column=0)
        self._build_section_retranslate(grid_frame, row=1, column=1)

        self._build_section_result_table()
        self._build_section_pagination()
        self._build_section_status_bar()

        self._conn = None
        self._all_rows = []
        self._sort_column = None
        self._sort_reverse = False
        self._current_page = 1

        self.app.root.after(800, self._auto_load_db)

    def _build_section_data_source(self):
        """数据源 + xlsx 导入导出"""
        top = ttk.LabelFrame(self, text=" 数据源 & xlsx ", padding=6)
        top.pack(fill="x", padx=6, pady=(6, 4))

        top.columnconfigure(1, weight=2)
        top.columnconfigure(5, weight=1)

        ttk.Label(top, text="数据库:").grid(row=0, column=0, sticky="w")

        self.db_path_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.db_path_var).grid(
            row=0, column=1, sticky="ew", padx=4)

        ttk.Button(top, text="浏览...", width=8,
                   command=self._choose_db).grid(row=0, column=2, padx=2)
        ttk.Button(top, text="🔄 刷新", width=8,
                   command=self._refresh_db).grid(row=0, column=3, padx=2)

        self.db_info_var = tk.StringVar(value="未加载")
        ttk.Label(top, textvariable=self.db_info_var,
                  foreground="#004080",
                  font=("Consolas", 9)).grid(
            row=0, column=4, padx=(6, 8))

        ttk.Frame(top, width=1).grid(row=0, column=5, sticky="ew")

        ttk.Separator(top, orient="vertical").grid(
            row=0, column=6, sticky="ns", padx=6)

        ttk.Label(top, text="导出:").grid(row=0, column=7, sticky="w")
        ttk.Button(top, text="📤 完整数据库", width=13,
                   command=self._export_full_xlsx).grid(
            row=0, column=8, padx=2)
        ttk.Button(top, text="📤 当前筛选", width=11,
                   command=self._export_filtered_xlsx).grid(
            row=0, column=9, padx=2)

        ttk.Label(top, text="导入:").grid(
            row=0, column=10, sticky="w", padx=(10, 0))
        ttk.Button(top, text="📥 导入 xlsx", width=11,
                   command=self._import_xlsx).grid(
            row=0, column=11, padx=2)

        if not _XLSX_OK:
            ttk.Label(top, text="⚠️ 未安装 openpyxl",
                      foreground="#C00000",
                      font=("Consolas", 8)).grid(
                row=0, column=12, padx=6)

    def _build_section_xlsx_io(self):
        """已合并到 _build_section_data_source"""
        pass

    def _build_section_filter(self, parent, row=0, column=0):
        """筛选条件面板（2×2 田字格 · 上左）"""
        filter_frame = ttk.LabelFrame(parent, text=" 筛选条件 ", padding=6)
        filter_frame.grid(row=row, column=column,
                          sticky="nsew", padx=(0, 4), pady=(0, 4))

        logic_bar = ttk.Frame(filter_frame)
        logic_bar.pack(fill="x", pady=(0, 4))
        ttk.Label(logic_bar, text="逻辑:").pack(side="left")
        self.logic_var = tk.StringVar(value="AND")
        ttk.Radiobutton(logic_bar, text="AND (全部满足)",
                        variable=self.logic_var,
                        value="AND").pack(side="left", padx=4)
        ttk.Radiobutton(logic_bar, text="OR (任一满足)",
                        variable=self.logic_var,
                        value="OR").pack(side="left", padx=4)

        self.conditions_frame = ttk.Frame(filter_frame)
        self.conditions_frame.pack(fill="x")
        self.conditions = []

        btn_bar = ttk.Frame(filter_frame)
        btn_bar.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_bar, text="+ 添加条件",
                   command=self._add_condition).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="🔍 查询",
                   command=self._do_query).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="✖ 清空条件",
                   command=self._clear_conditions).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="📋 显示全部",
                   command=self._show_all).pack(side="left", padx=2)

    def _build_section_batch_edit(self, parent, row=0, column=1):
        """批量修改面板（2×2 田字格 · 上右）"""
        edit_frame = ttk.LabelFrame(
            parent, text=" 批量修改（对当前查询结果） ", padding=6)
        edit_frame.grid(row=row, column=column,
                        sticky="nsew", padx=(4, 0), pady=(0, 4))

        row1 = ttk.Frame(edit_frame)
        row1.pack(fill="x", pady=2)

        ttk.Label(row1, text="目标字段:").pack(side="left")
        self.edit_field_var = tk.StringVar(value="bands")
        ttk.Combobox(
            row1, textvariable=self.edit_field_var, width=18,
            state="readonly",
            values=[f"{f[1]}({f[0]})" for f in self.EDITABLE_FIELDS],
        ).pack(side="left", padx=4)

        ttk.Label(row1, text="匹配模式:").pack(side="left", padx=(15, 0))
        self.edit_mode_var = tk.StringVar(value="包含替换")
        ttk.Combobox(
            row1, textvariable=self.edit_mode_var, width=14,
            state="readonly",
            values=self.REPLACE_MODES,
        ).pack(side="left", padx=4)

        row2 = ttk.Frame(edit_frame)
        row2.pack(fill="x", pady=2)

        ttk.Label(row2, text="查找内容:").pack(side="left")
        self.edit_find_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.edit_find_var,
                  width=22).pack(side="left", padx=4, fill="x", expand=True)

        ttk.Label(row2, text="替换为:").pack(side="left", padx=(8, 0))
        self.edit_replace_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.edit_replace_var,
                  width=22).pack(side="left", padx=4, fill="x", expand=True)

        row3 = ttk.Frame(edit_frame)
        row3.pack(fill="x", pady=(4, 0))

        self.edit_scope_var = tk.StringVar(value="影响范围: 0 条 (请先查询)")
        ttk.Label(row3, textvariable=self.edit_scope_var,
                  foreground="#804000",
                  font=("Consolas", 9, "bold")).pack(side="left")

        ttk.Button(row3, text="✏️ 执行修改", width=14,
                   command=self._execute_batch_edit).pack(side="right", padx=4)
        ttk.Button(row3, text="👁 预览修改", width=14,
                   command=self._preview_batch_edit).pack(side="right", padx=4)

    def _build_section_retranslate(self, parent, row=1, column=1):
        """二次翻译面板（2×2 田字格 · 下右）"""
        retrans_frame = ttk.LabelFrame(
            parent,
            text=" 二次翻译（英文→俄语） ",
            padding=6)
        retrans_frame.grid(row=row, column=column,
                           sticky="nsew", padx=(4, 0), pady=(4, 0))

        ttk.Label(retrans_frame,
                  text="用途: 提取筛选结果的【英文名】，重新翻译成俄语，"
                       "覆盖原有【俄语翻译】字段。",
                  foreground="#666",
                  font=("", 9),
                  wraplength=500,
                  justify="left").pack(anchor="w", pady=(0, 4))

        r1 = ttk.Frame(retrans_frame)
        r1.pack(fill="x", pady=2)

        ttk.Label(r1, text="翻译模式:").pack(side="left")
        self.retrans_mode_var = tk.StringVar(value="sentence")
        ttk.Radiobutton(r1, text="整句翻译",
                        variable=self.retrans_mode_var,
                        value="sentence").pack(side="left", padx=4)
        ttk.Radiobutton(r1, text="逐词翻译(保留品牌)",
                        variable=self.retrans_mode_var,
                        value="word").pack(side="left", padx=4)

        r1b = ttk.Frame(retrans_frame)
        r1b.pack(fill="x", pady=2)

        ttk.Label(r1b, text="并发:").pack(side="left")
        self.retrans_workers_var = tk.StringVar(value="8")
        ttk.Spinbox(r1b, from_=1, to=32,
                    textvariable=self.retrans_workers_var,
                    width=5).pack(side="left", padx=4)

        ttk.Label(r1b, text="批次:").pack(side="left", padx=(8, 0))
        self.retrans_batch_var = tk.StringVar(value="20")
        ttk.Spinbox(r1b, from_=5, to=50,
                    textvariable=self.retrans_batch_var,
                    width=5).pack(side="left", padx=4)

        self.retrans_save_report_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(r1b, text="保存翻译对照报告 (xlsx)",
                        variable=self.retrans_save_report_var).pack(
            side="left", padx=(12, 0))

        r2 = ttk.Frame(retrans_frame)
        r2.pack(fill="x", pady=(6, 0))

        self.retrans_scope_var = tk.StringVar(value="影响范围: 0 条 (请先查询)")
        ttk.Label(r2, textvariable=self.retrans_scope_var,
                  foreground="#804000",
                  font=("Consolas", 9, "bold")).pack(side="left")

        ttk.Button(r2, text="🌐 预览二次翻译", width=20,
                   command=self._preview_retranslate).pack(side="right", padx=4)

    def _build_section_similarity(self, parent, row=1, column=0):
        """相似度筛选面板（2×2 田字格 · 下左）"""
        sim_frame = ttk.LabelFrame(
            parent,
            text=" 相似度筛选（英文名 vs 俄语翻译） ",
            padding=6)
        sim_frame.grid(row=row, column=column,
                       sticky="nsew", padx=(0, 4), pady=(4, 0))

        ttk.Label(sim_frame,
                  text="用途: 找出【俄语翻译】与【英文名】过于相似的记录"
                       "（说明翻译未生效，仍是英文）",
                  foreground="#666",
                  font=("", 9),
                  wraplength=500,
                  justify="left").pack(anchor="w", pady=(0, 4))

        sr1 = ttk.Frame(sim_frame)
        sr1.pack(fill="x", pady=2)

        ttk.Label(sr1, text="相似度阈值:").pack(side="left")
        self.sim_threshold_var = tk.StringVar(value="80")
        ttk.Spinbox(sr1, from_=0, to=100,
                    textvariable=self.sim_threshold_var,
                    width=6).pack(side="left", padx=4)
        ttk.Label(sr1, text="%").pack(side="left")

        sr2 = ttk.Frame(sim_frame)
        sr2.pack(fill="x", pady=2)

        ttk.Label(sr2, text="算法:").pack(side="left")
        self.sim_algorithm_var = tk.StringVar(value="difflib")
        ttk.Radiobutton(sr2, text="字符相似",
                        variable=self.sim_algorithm_var,
                        value="difflib").pack(side="left", padx=2)
        ttk.Radiobutton(sr2, text="拉丁字母占比",
                        variable=self.sim_algorithm_var,
                        value="latin").pack(side="left", padx=2)

        ttk.Label(sim_frame,
                  text="数值越高，越接近英文（翻译失败）。建议 70~95",
                  foreground="#804000",
                  font=("", 8)).pack(anchor="w", pady=(2, 0))

        sr3 = ttk.Frame(sim_frame)
        sr3.pack(fill="x", pady=(6, 0))

        self.sim_scope_var = tk.StringVar(value="未筛选")
        ttk.Label(sr3, textvariable=self.sim_scope_var,
                  foreground="#804000",
                  font=("Consolas", 9, "bold")).pack(side="left")

        ttk.Button(sr3, text="🔍 相似度筛选", width=16,
                   command=self._filter_by_similarity).pack(side="right", padx=4)
        ttk.Button(sr3, text="📋 恢复全部", width=12,
                   command=self._show_all).pack(side="right", padx=4)

    def _build_section_result_table(self):
        """查询结果表格"""
        result_frame = ttk.LabelFrame(self, text=" 查询结果 ", padding=6)
        result_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))

        res_bar = ttk.Frame(result_frame)
        res_bar.pack(fill="x", pady=(0, 4))

        self.result_info_var = tk.StringVar(value="无结果")
        ttk.Label(res_bar, textvariable=self.result_info_var,
                  foreground="#804000",
                  font=("Consolas", 9, "bold")).pack(side="left")

        ttk.Label(res_bar,
                  text="  💡 Ctrl+A 全选当前页 | Ctrl/Shift+点击 多选",
                  foreground="#666", font=("", 8)).pack(side="left", padx=10)

        self.checked_info_var = tk.StringVar(value="已选: 0")
        ttk.Label(res_bar, textvariable=self.checked_info_var,
                  foreground="#008000",
                  font=("Consolas", 9, "bold")).pack(side="right", padx=10)

        table_frame = ttk.Frame(result_frame)
        table_frame.pack(fill="both", expand=True)

        columns = [f[0] for f in self.FIELDS]
        headings = {f[0]: f[1] for f in self.FIELDS}

        self.tree = ttk.Treeview(table_frame, columns=columns,
                                 show="headings", selectmode="extended")

        for col in columns:
            self.tree.heading(col, text=headings[col],
                              command=lambda c=col: self._sort_by_column(c))
            char_w = self._col_widths.get(col, 20)
            pixel_w = int(char_w * self.COL_WIDTH_UNIT)
            self.tree.column(col, width=pixel_w, anchor="w",
                             stretch=False)

        self.tree.bind("<ButtonRelease-1>", self._on_col_release, add="+")

        vsb = ttk.Scrollbar(table_frame, orient="vertical",
                            command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal",
                            command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._on_selection_changed)

        self.tree.bind("<Control-a>", self._on_ctrl_a)
        self.tree.bind("<Control-A>", self._on_ctrl_a)

        self._setup_context_menu()

    def _load_col_widths(self):
        widths = dict(self.DEFAULT_COL_WIDTHS)
        if COL_WIDTH_PATH.exists():
            try:
                data = json.loads(
                    COL_WIDTH_PATH.read_text(encoding="utf-8"))
                for col, w in data.items():
                    if col in widths and isinstance(w, (int, float)):
                        widths[col] = w
                print(f"[F] ✅ 已加载列宽配置: {COL_WIDTH_PATH}")
            except Exception as e:
                print(f"[F] ⚠️ 列宽配置加载失败: {e}")
        self._col_widths = widths

    def _save_col_widths(self):
        try:
            COL_WIDTH_PATH.write_text(
                json.dumps(self._col_widths, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as e:
            print(f"[F] ⚠️ 列宽保存失败: {e}")

    def _on_col_release(self, event):
        region = self.tree.identify("region", event.x, event.y)
        changed = False
        for col in self._col_widths:
            try:
                pixel_w = self.tree.column(col, "width")
                char_w = round(pixel_w / self.COL_WIDTH_UNIT)
                if char_w != self._col_widths[col]:
                    self._col_widths[col] = char_w
                    changed = True
            except Exception:
                pass
        if changed:
            self._save_col_widths()

    def _reset_col_widths(self):
        if not messagebox.askyesno(
                "恢复默认",
                "将把所有列宽恢复为默认值。\n\n确定继续?"):
            return
        self._col_widths = dict(self.DEFAULT_COL_WIDTHS)
        for col, char_w in self._col_widths.items():
            try:
                self.tree.column(col, width=int(char_w * self.COL_WIDTH_UNIT))
            except Exception:
                pass
        self._save_col_widths()
        self.set_status("✅ 已恢复默认列宽")

    def _build_section_pagination(self):
        page_bar = ttk.Frame(self)
        page_bar.pack(fill="x", padx=6, pady=(0, 4))

        ttk.Label(page_bar, text="每页:").pack(side="left")
        self.page_size_var = tk.StringVar(value="500")
        page_size_combo = ttk.Combobox(page_bar, textvariable=self.page_size_var,
                                       values=[str(s) for s in self.PAGE_SIZES],
                                       width=6, state="readonly")
        page_size_combo.pack(side="left", padx=4)
        page_size_combo.bind("<<ComboboxSelected>>",
                             lambda e: self._reset_page())

        ttk.Button(page_bar, text="◀ 上一页", width=10,
                   command=self._prev_page).pack(side="left", padx=2)
        self.page_info_var = tk.StringVar(value="0 / 0")
        ttk.Label(page_bar, textvariable=self.page_info_var,
                  width=12).pack(side="left", padx=4)
        ttk.Button(page_bar, text="下一页 ▶", width=10,
                   command=self._next_page).pack(side="left", padx=2)

    def _build_section_status_bar(self):
        self.status_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status_var,
                  foreground="#804000", font=("Consolas", 9),
                  anchor="w").pack(fill="x", padx=8, pady=(0, 4))

    # ============================================================
    #                    数据库连接
    # ============================================================
    def _auto_load_db(self):
        try:
            from config_manager import load_config
            cfg = load_config()
            db = cfg.get("DB_PATH", "")
            if db and Path(db).exists():
                self.db_path_var.set(db)
                self._refresh_db()
            else:
                default = Path.cwd() / "data" / "products.db"
                if default.exists():
                    self.db_path_var.set(str(default))
                    self._refresh_db()
        except Exception as e:
            print(f"[F] 自动加载数据库失败: {e}")

    def _choose_db(self):
        p = filedialog.askopenfilename(
            title="选择数据库",
            filetypes=[("SQLite DB", "*.db"), ("All", "*.*")])
        if p:
            self.db_path_var.set(p)
            self._refresh_db()

    def _connect(self):
        db_path = self.db_path_var.get().strip()
        if not db_path or not Path(db_path).exists():
            return False
        try:
            if self._conn:
                self._conn.close()
            self._conn = sqlite3.connect(db_path)
            self._conn.row_factory = sqlite3.Row
            return True
        except Exception as e:
            messagebox.showerror("连接失败", str(e))
            return False

    def _refresh_db(self):
        if not self._connect():
            messagebox.showerror("错误", "数据库不存在或无法打开")
            return
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT COUNT(*) FROM products")
            total = cur.fetchone()[0]
            self.db_info_var.set(f"✅ 总记录: {total:,}")
            print(f"[F] 已连接: {self.db_path_var.get()}, 共 {total} 条")
            self._show_all()
        except Exception as e:
            self.db_info_var.set(f"❌ 错误: {str(e)[:40]}")
            messagebox.showerror("错误", str(e))

    # ============================================================
    def _execute_one(self, task):
        return "skip", "F 模块无单任务执行"