# uppercase_bands.py
"""把现有数据库所有品牌名称转为大写"""
import sqlite3
from pathlib import Path
from datetime import datetime
import shutil

DB_PATH = r"L:\PythonProject1\Folder_processing_tool\data\products.db"


def main():
    p = Path(DB_PATH)
    if not p.exists():
        print(f"❌ 数据库不存在: {p}")
        return

    # 备份
    backup = p.parent / f"{p.stem}_preupper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(p, backup)
    print(f"✅ 已备份: {backup}")

    conn = sqlite3.connect(str(p))
    cur = conn.cursor()

    # 查看修改前
    cur.execute("SELECT bands, COUNT(*) FROM products GROUP BY bands ORDER BY bands")
    print("\n【修改前】")
    for b, c in cur.fetchall()[:20]:
        print(f"  {c:>6,}  {b!r}")

    # 执行大写
    cur.execute("""
        UPDATE products
        SET bands = UPPER(bands)
        WHERE bands IS NOT NULL AND bands != '' AND bands != UPPER(bands)
    """)
    affected = cur.rowcount
    conn.commit()

    print(f"\n✅ 已更新 {affected:,} 条记录")

    # 查看修改后
    cur.execute("SELECT bands, COUNT(*) FROM products GROUP BY bands ORDER BY bands")
    print("\n【修改后】")
    for b, c in cur.fetchall()[:20]:
        print(f"  {c:>6,}  {b!r}")

    conn.close()
    print(f"\n🎉 完成! 备份: {backup.name}")


if __name__ == "__main__":
    main()