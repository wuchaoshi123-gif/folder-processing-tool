# core/db_manager.py
"""数据库管理器（含 englishname 字段）
★ v2 修复:
  - isolation_level=None 关闭隐式事务，修复 "BEGIN within a transaction" 崩溃
  - 支持 with 上下文管理器
  - row_factory = sqlite3.Row
  - 新增 bulk_upsert_auto 便捷批量接口
"""
import sqlite3
from pathlib import Path


class DBManager:

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self._connect()

    # ==========================================================
    #                  连接 & 初始化
    # ==========================================================
    def _connect(self):
        # ★ 关键: isolation_level=None 关闭 Python sqlite3 的隐式事务
        #   这样 cur.execute("BEGIN") 才是合法操作
        self.conn = sqlite3.connect(
            str(self.db_path),
            timeout=30,
            check_same_thread=False,
            isolation_level=None,
        )
        self.conn.row_factory = sqlite3.Row

        # 持久设置: journal_mode 写进数据库文件头，只需第一次成功
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        # 每连接设置
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-64000")
        self.conn.execute("PRAGMA temp_store=MEMORY")
        self.conn.execute("PRAGMA mmap_size=268435456")
        self.conn.execute("PRAGMA foreign_keys=ON")

        self._create_tables()

    def _create_tables(self):
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nums            INTEGER,
                onlymulu        TEXT NOT NULL,
                englishname     TEXT,
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
            CREATE INDEX IF NOT EXISTS idx_bands    ON products(bands);
            CREATE INDEX IF NOT EXISTS idx_chuprice ON products(chuprice);
            CREATE INDEX IF NOT EXISTS idx_created  ON products(created_at);

            CREATE TABLE IF NOT EXISTS failed_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                onlymulu    TEXT,
                reason      TEXT,
                detail      TEXT,
                image_path  TEXT,
                ocr_text    TEXT,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_failed_om     ON failed_items(onlymulu);
            CREATE INDEX IF NOT EXISTS idx_failed_reason ON failed_items(reason);
        """)

        # ---- 自动迁移 ----
        self._migrate_columns("failed_items", {
            "image_path": "TEXT",
            "ocr_text":   "TEXT",
        })
        self._migrate_columns("products", {
            "englishname": "TEXT",
        })

    def _migrate_columns(self, table, columns):
        """给旧表补列"""
        try:
            cur = self.conn.cursor()
            cur.execute(f"PRAGMA table_info({table})")
            existing = {r[1] for r in cur.fetchall()}
            for col, ctype in columns.items():
                if col not in existing:
                    cur.execute(
                        f"ALTER TABLE {table} ADD COLUMN {col} {ctype}")
                    print(f"[DB] ✅ {table} 已添加 {col} 字段")
        except Exception as e:
            print(f"[DB] ⚠️ {table} 迁移失败: {e}")

    # ==========================================================
    #                   上下文管理
    # ==========================================================
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ==========================================================
    #                   单条写入
    # ==========================================================
    def upsert_product(self, data):
        """
        以 onlymulu 为唯一键, 重复则跳过（不覆盖）
        ★ 品牌自动转大写
        """
        cur = self.conn.cursor()
        bands = (data.get("bands") or "").strip().upper()
        try:
            cur.execute("""
                INSERT OR IGNORE INTO products
                    (nums, onlymulu, englishname, local_url, web_url, rufanyi,
                     shoessize, chuprice, images, bands,
                     bandsizechart, source_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("nums"),
                data.get("onlymulu"),
                data.get("englishname", ""),
                data.get("local_url"),
                data.get("web_url"),
                data.get("rufanyi"),
                data.get("shoessize"),
                data.get("chuprice"),
                data.get("images"),
                bands,
                data.get("bandsizechart"),
                data.get("source_dir"),
            ))
            return "inserted" if cur.rowcount > 0 else "duplicate"
        except Exception as e:
            return f"error:{str(e)[:100]}"

    def update_product_full(self, data):
        """按 onlymulu 全字段更新"""
        cur = self.conn.cursor()
        bands = (data.get("bands") or "").strip().upper()
        try:
            cur.execute("""
                UPDATE products SET
                    nums = ?, englishname = ?, local_url = ?, web_url = ?,
                    rufanyi = ?, shoessize = ?, chuprice = ?, images = ?,
                    bands = ?, bandsizechart = ?, source_dir = ?
                WHERE onlymulu = ?
            """, (
                data.get("nums"),
                data.get("englishname", ""),
                data.get("local_url"),
                data.get("web_url"),
                data.get("rufanyi"),
                data.get("shoessize"),
                data.get("chuprice"),
                data.get("images"),
                bands,
                data.get("bandsizechart"),
                data.get("source_dir"),
                data.get("onlymulu"),
            ))
            return "updated" if cur.rowcount > 0 else "not_found"
        except Exception as e:
            return f"error:{str(e)[:100]}"

    def update_product(self, onlymulu, data):
        """按 onlymulu 局部更新指定字段"""
        allowed = ("rufanyi", "englishname", "shoessize", "bands")
        fields, params = [], []
        for k in allowed:
            if k in data:
                fields.append(f"{k} = ?")
                params.append(data[k])
        if not fields:
            return False
        params.append(onlymulu)
        try:
            cur = self.conn.cursor()
            cur.execute(
                f"UPDATE products SET {', '.join(fields)} WHERE onlymulu = ?",
                params)
            return cur.rowcount > 0
        except Exception as e:
            print(f"[DB] 更新失败: {e}")
            return False

    # ==========================================================
    #                   批量查询 / 写入
    # ==========================================================
    def get_existing_onlymulu(self, onlymulu_set):
        """批量查询已存在的 onlymulu"""
        if not onlymulu_set:
            return set()
        cur = self.conn.cursor()
        result = set()
        lst = list(onlymulu_set)
        for i in range(0, len(lst), 900):
            batch = lst[i:i + 900]
            ph = ",".join("?" * len(batch))
            cur.execute(
                f"SELECT onlymulu FROM products WHERE onlymulu IN ({ph})",
                batch)
            for r in cur.fetchall():
                result.add(r[0])
        return result

    def bulk_write_with_action(self, new_items, dup_items, dup_action):
        """
        ★ 事务批量写入
          new_items:   [(idx, onlymulu, data_dict), ...]
          dup_items:   [(idx, onlymulu, data_dict), ...]
          dup_action:  "skip" | "overwrite"
        返回: (ok_cnt, dup_cnt, errors)
        """
        ok_cnt = 0
        dup_cnt = 0
        errors = []
        cur = self.conn.cursor()
        try:
            cur.execute("BEGIN")   # isolation_level=None 下合法

            # ---------- 新记录 ----------
            for idx, om, data in new_items:
                try:
                    bands = (data.get("bands") or "").strip().upper()
                    cur.execute("""
                        INSERT OR IGNORE INTO products
                            (nums, onlymulu, englishname, local_url, web_url,
                             rufanyi, shoessize, chuprice, images, bands,
                             bandsizechart, source_dir)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data.get("nums"), om,
                        data.get("englishname", ""),
                        data.get("local_url"), data.get("web_url"),
                        data.get("rufanyi"), data.get("shoessize"),
                        data.get("chuprice"), data.get("images"),
                        bands, data.get("bandsizechart"),
                        data.get("source_dir"),
                    ))
                    if cur.rowcount > 0:
                        ok_cnt += 1
                    else:
                        dup_cnt += 1
                except Exception as e:
                    errors.append(f"ins {om[:40]}: {str(e)[:60]}")

            # ---------- 重复记录 ----------
            if dup_action == "overwrite":
                for idx, om, data in dup_items:
                    try:
                        bands = (data.get("bands") or "").strip().upper()
                        cur.execute("""
                            UPDATE products SET
                                nums = ?, englishname = ?, local_url = ?,
                                web_url = ?, rufanyi = ?, shoessize = ?,
                                chuprice = ?, images = ?, bands = ?,
                                bandsizechart = ?, source_dir = ?
                            WHERE onlymulu = ?
                        """, (
                            data.get("nums"),
                            data.get("englishname", ""),
                            data.get("local_url"), data.get("web_url"),
                            data.get("rufanyi"), data.get("shoessize"),
                            data.get("chuprice"), data.get("images"),
                            bands, data.get("bandsizechart"),
                            data.get("source_dir"), om,
                        ))
                        if cur.rowcount > 0:
                            dup_cnt += 1
                    except Exception as e:
                        errors.append(f"upd {om[:40]}: {str(e)[:60]}")
            else:
                dup_cnt = len(dup_items)

            self.conn.commit()
        except Exception as e:
            try:
                self.conn.rollback()
            except Exception:
                pass
            errors.append(f"事务失败: {str(e)[:100]}")
        return ok_cnt, dup_cnt, errors

    def bulk_upsert_auto(self, items, dup_action="skip"):
        """
        ★ 便捷接口: 自动查询重复并分流
          items: [(idx, onlymulu, data_dict), ...]
        返回: (ok_cnt, dup_cnt, errors)
        """
        if not items:
            return 0, 0, []
        om_set = {om for _, om, _ in items}
        existing = self.get_existing_onlymulu(om_set)
        new_items = [(i, om, d) for i, om, d in items if om not in existing]
        dup_items = [(i, om, d) for i, om, d in items if om in existing]
        return self.bulk_write_with_action(new_items, dup_items, dup_action)

    # ==========================================================
    #                   失败记录 & 统计
    # ==========================================================
    def add_failed(self, onlymulu, reason, detail="",
                   image_path="", ocr_text=""):
        try:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT INTO failed_items
                    (onlymulu, reason, detail, image_path, ocr_text)
                VALUES (?, ?, ?, ?, ?)
            """, (
                onlymulu,
                reason,
                (detail or "")[:500],
                (image_path or "")[:500],
                (ocr_text or "")[:2000],
            ))
        except Exception as e:
            print(f"[DB] add_failed 失败: {e}")

    def uppercase_all_bands(self):
        """把 products 表所有 bands 字段转大写"""
        try:
            cur = self.conn.cursor()
            cur.execute("""
                UPDATE products
                SET bands = UPPER(bands)
                WHERE bands IS NOT NULL
                  AND bands != ''
                  AND bands != UPPER(bands)
            """)
            return cur.rowcount
        except Exception as e:
            print(f"[DB] 品牌大写失败: {e}")
            return 0

    def count(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM products")
        return cur.fetchone()[0]

    # ==========================================================
    def close(self):
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None