# deduplicate_db.py
"""
数据库去重脚本
  · 以 onlymulu 为唯一键
  · 每个 onlymulu 保留 id 最小的记录
  · 删除其他重复记录
  · 显示去重前后对比

用法:
  python deduplicate_db.py
  python deduplicate_db.py --db "L:\path\to\products.db"
"""
import argparse
import sqlite3
from pathlib import Path


def deduplicate(db_path):
    print(f"\n{'='*70}")
    print(f"数据库去重工具")
    print(f"{'='*70}")
    print(f"数据库: {db_path}")

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # 清理前的统计
    cur.execute("SELECT COUNT(*) FROM products")
    before_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT onlymulu) FROM products")
    distinct_count = cur.fetchone()[0]

    dup_count = before_total - distinct_count

    print(f"\n【清理前】")
    print(f"  总记录数:        {before_total:,}")
    print(f"  唯一 onlymulu:   {distinct_count:,}")
    print(f"  重复记录数:      {dup_count:,}")

    if dup_count == 0:
        print(f"\n✅ 无重复，无需清理")
        conn.close()
        return

    # 找出重复的 onlymulu 样本
    print(f"\n【重复样本（前 10 个 onlymulu）】")
    cur.execute("""
        SELECT onlymulu, COUNT(*) as cnt
        FROM products
        GROUP BY onlymulu
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 10
    """)
    for om, cnt in cur.fetchall():
        print(f"  {cnt} 次  {om[:70]}")

    # 确认
    print(f"\n⚠️ 将删除 {dup_count:,} 条重复记录（每个 onlymulu 保留 id 最小的一条）")
    ans = input("确认执行? (y/N): ").strip().lower()
    if ans != "y":
        print("已取消")
        conn.close()
        return

    # 执行删除
    cur.execute("""
        DELETE FROM products
        WHERE id NOT IN (
            SELECT MIN(id) FROM products GROUP BY onlymulu
        )
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM products")
    after_total = cur.fetchone()[0]

    print(f"\n【清理后】")
    print(f"  总记录数:        {after_total:,}")
    print(f"  实际删除:        {before_total - after_total:,}")

    # 清理孤儿 failed_items（可选）
    cur.execute("SELECT COUNT(*) FROM failed_items")
    failed_count = cur.fetchone()[0]
    if failed_count > 0:
        ans = input(f"\n是否清理 failed_items 表（{failed_count} 条）? (y/N): ").strip().lower()
        if ans == "y":
            cur.execute("DELETE FROM failed_items")
            conn.commit()
            print(f"  ✅ 已清理 {failed_count} 条失败记录")

    # 优化（重建索引 + 压缩）
    print(f"\n正在优化数据库...")
    cur.execute("VACUUM")
    cur.execute("ANALYZE")
    conn.commit()

    conn.close()
    print(f"\n🎉 去重完成!")


def main():
    parser = argparse.ArgumentParser(description="数据库去重")
    parser.add_argument("--db", default=r"L:\PythonProject1\Folder_processing_tool\data\products.db",
                        help="数据库路径")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}")
        return

    deduplicate(db_path)


if __name__ == "__main__":
    main()