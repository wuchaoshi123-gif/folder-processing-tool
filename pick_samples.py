# pick_samples.py
"""按特征自动抽取 10 个代表性 描述.txt 样本"""
import os
import re
from pathlib import Path
from tkinter import filedialog, Tk

root = Tk(); root.withdraw()
target = filedialog.askdirectory(title="选择目录")
if not target:
    exit()

# 收集所有 描述.txt
all_descs = []
for e in os.scandir(target):
    if e.is_dir():
        p = Path(e.path) / "描述.txt"
        if p.exists():
            try:
                all_descs.append((e.name, p.read_text(encoding="utf-8", errors="ignore")))
            except Exception:
                pass

print(f"共 {len(all_descs)} 个")

EMOJI_RE = re.compile(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\u2705]')

def has(pred, d):
    return bool(pred(d))

def lines_of(d):
    return [l.strip() for l in d.split("\n") if l.strip()]

# 分类池
buckets = {
    "1行":        [],
    "2行_有货号":  [],
    "2行_无货号":  [],
    "3行":        [],
    "4行":        [],
    "5行_有编码":  [],
    "5行_无编码":  [],
    "6行以上":     [],
    "无emoji":    [],
    "特殊_非💰开头": [],
}

for name, d in all_descs:
    ln = len(lines_of(d))
    has_hh = "货号" in d
    has_bm = bool(re.search(r'(?:编码|编号|sku|id)', d, re.I))
    no_emoji = not EMOJI_RE.search(d)
    first = lines_of(d)[0] if lines_of(d) else ""
    not_price = not first.startswith("💰")

    if ln == 1 and len(buckets["1行"]) < 1:
        buckets["1行"].append((name, d))
    elif ln == 2 and has_hh and len(buckets["2行_有货号"]) < 1:
        buckets["2行_有货号"].append((name, d))
    elif ln == 2 and not has_hh and len(buckets["2行_无货号"]) < 1:
        buckets["2行_无货号"].append((name, d))
    elif ln == 3 and len(buckets["3行"]) < 1:
        buckets["3行"].append((name, d))
    elif ln == 4 and len(buckets["4行"]) < 1:
        buckets["4行"].append((name, d))
    elif ln == 5 and has_bm and len(buckets["5行_有编码"]) < 1:
        buckets["5行_有编码"].append((name, d))
    elif ln == 5 and not has_bm and len(buckets["5行_无编码"]) < 1:
        buckets["5行_无编码"].append((name, d))
    elif ln >= 6 and len(buckets["6行以上"]) < 1:
        buckets["6行以上"].append((name, d))
    elif no_emoji and len(buckets["无emoji"]) < 1:
        buckets["无emoji"].append((name, d))
    elif not_price and len(buckets["特殊_非💰开头"]) < 1:
        buckets["特殊_非💰开头"].append((name, d))

# 拼装输出
parts = []
total_picked = 0
for label, items in buckets.items():
    if not items:
        continue
    name, d = items[0]
    parts.append(
        f"【样本 · {label}】\n"
        f"【文件夹】{name}\n"
        f"【内容】\n"
        f"{d.strip()}\n"
    )
    total_picked += 1

output = ("\n\n" + "=" * 60 + "\n\n").join(parts)

out_path = Path.home() / "Desktop" / "描述样本10条.txt"
out_path.write_text(output, encoding="utf-8")

print(f"\n✅ 已抽取 {total_picked} 个样本")
print(f"📁 保存到: {out_path}")
print(f"\n请用记事本打开该文件，全选复制，粘贴给我")