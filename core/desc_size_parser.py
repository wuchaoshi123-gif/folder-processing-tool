# core/desc_size_parser.py
"""
从 描述.txt 提取尺码信息

处理流程:
  1. 按行扫描，找含 尺码/码数/尺寸/Size 等关键词的行
  2. 提取关键词后的内容（或整行 fallback）
  3. 规范化符号（+ → ,  x65去掉  括号转空格等）
  4. 送 e_pipeline.parse_sizes 走完整规则（半码展开、缺口补全等）
"""
import re


# ★ 尺码关键词（不区分大小写）
SIZE_KEYWORDS = (
    "尺码", "码数", "尺寸", "号码", "号数", "码号",
    "size", "sizes",
)

# 尾部的无用标记
TAIL_NOISE_RE = re.compile(r'\s*(?:如图|[xX×]\s*\d+)\s*$')

# 分数符号
FRACTION_RE_2_3 = re.compile(r'(\d+)\s*⅔')
FRACTION_RE_2_3_BARE = re.compile(r'⅔')
FRACTION_RE_1_3 = re.compile(r'(\d+)\s*⅓')
FRACTION_RE_1_3_BARE = re.compile(r'⅓')
FRACTION_RE_1_2 = re.compile(r'(\d+)\s*½')
FRACTION_RE_1_2_BARE = re.compile(r'½')

# 括号
BRACKETS_RE = re.compile(r'[（）()【】\[\]｛｝{}]')


def _clean_line(line):
    """去掉 emoji、零宽字符、方括号前缀"""
    line = re.sub(r'[\u200b-\u200d\ufeff]', '', line)
    line = re.sub(
        r'[\U0001F000-\U0001FAFF\u2600-\u27BF\u2705\u203C\u2049'
        r'\u2753\u2755\u2757\u2763\u2764\uFE0F]+',
        ' ', line)
    line = re.sub(r'^[【\[][^】\]]*[】\]]\s*', '', line)
    line = line.strip()
    return line


def extract_size_text(desc_text):
    """
    从描述全文提取尺码文本片段。三级搜索：

    ① 关键词行  →  提取关键词后内容（如 "尺码：36-45"）
    ② 整段范围  →  搜 \d{2}[-～~到至]\d{2} 这种范围（如 "男女鞋36-45码"）
    ③ 纯尺码串  →  至少 3 个连续尺码数字（如 "36 36.5 37 38"）
    """
    if not desc_text:
        return None

    # 预处理：把零宽字符、emoji 去掉（但保留换行结构）
    lines_raw = []
    for raw_line in desc_text.split("\n"):
        line = _clean_line(raw_line)
        lines_raw.append(line)

    # ============================================================
    # ① 优先找含关键词的行
    # ============================================================
    for line in lines_raw:
        if not line:
            continue
        for kw in SIZE_KEYWORDS:
            m = re.search(
                rf'{re.escape(kw)}\s*[:：]?\s*(.+)$',
                line, re.IGNORECASE)
            if m:
                size_part = m.group(1).strip()
                size_part = TAIL_NOISE_RE.sub('', size_part).strip()
                # 提取到的部分要至少有 2 个数字
                if size_part and len(re.findall(r'\d', size_part)) >= 2:
                    return size_part

    # ============================================================
    # ② 关键词行里没找到 → 整段搜"范围形式"
    #    形如: 36-45、36～45、36~45、36到45、36至45
    # ============================================================
    full_text = " ".join(lines_raw)
    range_pat = re.compile(
        r'(?<!\d)(\d{2}(?:\.\d)?)\s*[-～~到至]\s*(\d{2}(?:\.\d)?)(?!\d)')
    for m in range_pat.finditer(full_text):
        lo, hi = float(m.group(1)), float(m.group(2))
        # 都必须在 20~50 之间（尺码范围）
        if 20 <= lo <= 50 and 20 <= hi <= 50 and lo <= hi:
            # 返回 "36-45"
            return f"{m.group(1)}-{m.group(2)}"

    # ============================================================
    # ③ 整段搜"纯尺码串"：至少 3 个连续数字，全部在 20~50
    #    形如: 36 36.5 37 38 ... 或 36,36.5,37,...
    # ============================================================
    # 找所有 20~50 之间的数字
    nums = []
    for m in re.finditer(r'(?<!\d)(\d{2}(?:\.\d)?)(?!\d)', full_text):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if 20 <= v <= 50:
            nums.append(m.group(1))
    # 至少 3 个才算"尺码串"
    if len(nums) >= 3:
        # 去重保序
        seen = set()
        uniq = []
        for n in nums:
            if n not in seen:
                seen.add(n)
                uniq.append(n)
        return " ".join(uniq)

    return None


def normalize_size_symbols(text):
    """
    规范化尺码符号:
      · ⅔ → .5    ⅓ → 删    ½ → .5
      · 全角～ 中文到/至 → -
      · + → ,      （列举如 36.5+37.5+39.5）
      · 括号 → 空格
      · 去掉 x65 / 如图
    """
    if not text:
        return text
    t = text

    # 分数符号
    t = FRACTION_RE_2_3.sub(r'\1.5', t)
    t = FRACTION_RE_2_3_BARE.sub('.5', t)
    t = FRACTION_RE_1_3.sub(r'\1', t)
    t = FRACTION_RE_1_3_BARE.sub('', t)
    t = FRACTION_RE_1_2.sub(r'\1.5', t)
    t = FRACTION_RE_1_2_BARE.sub('.5', t)

    # 全角/中文标点
    t = t.replace('，', ',').replace('、', ',').replace('：', ':')
    t = t.replace('～', '~').replace('－', '-').replace('—', '-')
    t = t.replace('–', '-').replace('﹣', '-')
    t = t.replace('到', '-').replace('至', '-')

    # + → ,
    t = t.replace('＋', ',').replace('+', ',')

    # 括号 → 空格
    t = BRACKETS_RE.sub(' ', t)

    # 去掉 x65 / 如图
    t = re.sub(r'\s*[xX×]\s*\d+\s*', ' ', t)
    t = t.replace('如图', ' ')

    # 去"含半码""半码"（has_ban 会在外层另行判断）
    t = t.replace('含半码', ' ').replace('半码', ' ')

    # 去孤立的 B 后缀
    t = re.sub(r'(?<![a-zA-Z])B(?![a-zA-Z])', ' ', t)

    return ' '.join(t.split())


def parse_sizes_from_desc(desc_text, banma=None):
    """
    从 描述.txt 提取尺码列表（复用 e_pipeline 完整规则引擎）

    ★ 修复: has_ban 用【全文】判断，而不是只看 raw 片段
            （"带半码" 可能出现在 raw 之外，如 "男女鞋36-45码（带半码）"）
    """
    if not desc_text:
        return None, False, "", "描述为空"

    raw = extract_size_text(desc_text)
    if not raw:
        return None, False, "", "未找到尺码信息"

    # ★ has_ban 用全文判断
    has_ban = bool(re.search(r'(?:带|含|有)?半码|[⅔½⅓]', desc_text))

    # 规范化符号
    normalized = normalize_size_symbols(raw)
    if not normalized:
        return None, has_ban, raw, "规范化后为空"

    # ★ 如果 has_ban=True 但 normalized 里丢了"半"标记，补回去
    #   让 e_pipeline.parse_sizes 能识别到 → 触发半码展开
    if has_ban and '半' not in normalized:
        normalized = normalized + ' 半'

    # 兼容两种运行方式导入 parse_sizes
    try:
        from core.e_pipeline import parse_sizes
    except ImportError:
        try:
            from e_pipeline import parse_sizes
        except ImportError:
            return None, has_ban, raw, "无法导入 e_pipeline"

    try:
        sizes, hb, reason = parse_sizes(normalized, banma)
        return sizes, (hb or has_ban), raw, reason
    except Exception as e:
        return None, has_ban, raw, f"解析异常: {str(e)[:80]}"


# ============================================================
#  本地测试
# ============================================================
if __name__ == "__main__":
    samples = [
        "货号:JS1460 尺码：36-45（半）",
        "黑红漆皮码数36-45 半码",
        "尺码：36-47 半码",
        "SIZE：36 37 37.5 38 39 39.5 40 40.5 41.5 42 42.5 43.5 44 45",
        "尺码:36 36.5 37 38 38.5 39 40 40.5 41 42 42.5 43 44 45",
        " 36-44含半码（36.5+37.5+39.5+41.5+42.5）",
        "SIZE:36 36⅔ 37⅓ 38 38⅔ 39⅓ 40 40⅔ 41⅓ 42 42⅔ 43⅓ 44 45",
        "尺码:36-45 x65",
        "号码：35.5-45",
    ]
    for s in samples:
        sizes, has_ban, raw, reason = parse_sizes_from_desc(s)
        print(f"[{s}]")
        print(f"  raw={raw!r}")
        print(f"  → sizes={sizes}  has_ban={has_ban}  reason={reason!r}")
        print()