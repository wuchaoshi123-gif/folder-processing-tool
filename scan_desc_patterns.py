# scan_desc_patterns.py
"""统计所有 描述.txt 的格式特征"""
import os
import re
from pathlib import Path
from collections import Counter
from tkinter import filedialog, Tk

root = Tk();
root.withdraw()
target = filedialog.askdirectory(title="选择目录")
if not target:
    exit()

descs = []
for e in os.scandir(target):
    if e.is_dir():
        p = Path(e.path) / "描述.txt"
        if p.exists():
            try:
                descs.append(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                pass

print(f"共 {len(descs)} 个描述.txt\n")

# 特征统计
first_line_prefix = Counter()
line_count = Counter()
has_price = 0
has_size = 0
has_huohao = 0
has_bianma = 0
has_emoji = 0
has_english_brand = 0

EMOJI_RE = re.compile(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\u2705]')

for d in descs:
    lines = [l for l in d.split("\n") if l.strip()]
    line_count[len(lines)] += 1

    if EMOJI_RE.search(d): has_emoji += 1
    if re.search(r'(?:Size|尺码|码数|尺寸)', d, re.I): has_size += 1
    if re.search(r'货号', d): has_huohao += 1
    if re.search(r'(?:编码|编号|sku|id)', d, re.I): has_bianma += 1
    if re.search(r'[A-Za-z]{3,}', d): has_english_brand += 1

    # 首行前 5 个字
    if lines:
        first = lines[0].strip()[:5]
        first_line_prefix[first] += 1

print(f"含 emoji:      {has_emoji}/{len(descs)}")
print(f"含 尺码/Size:  {has_size}/{len(descs)}")
print(f"含 货号:       {has_huohao}/{len(descs)}")
print(f"含 编码/id:    {has_bianma}/{len(descs)}")
print(f"含英文品牌:    {has_english_brand}/{len(descs)}")
print()
print("行数分布:")
for n, c in sorted(line_count.items())[:10]:
    print(f"  {n} 行: {c} 个")
print()
print("首行前5字 TOP20:")
for k, v in first_line_prefix.most_common(20):
    print(f"  {repr(k):<15} {v}")