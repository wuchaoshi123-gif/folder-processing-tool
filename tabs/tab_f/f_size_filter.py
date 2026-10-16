# tabs/tab_f/f_size_filter.py
"""
F 整理数据 —— 尺码派生字段筛选（B2 Python 层实现）

虚拟字段:
  size_first     尺码首值
  size_last      尺码末值
  size_span      尺码差值（末值 - 首值）
  size_count     尺码个数
  size_has_half  含半码（1/0）

规则:
  - 分隔符: | , ， 、 ; ； 空格（多分隔符兼容）
  - 空值(shoessize 为空 / 无有效数字): 不参与数值比较 → 不命中
  - size_count 特殊: 空值返回 0，可被 "= 0" 命中
  - 差值保留 1 位小数
  - 兼容老操作符 "尺码跨度大于" / "含半码"
"""

import re

# ---------------------------------------------------------------
# 字段注册表
# ---------------------------------------------------------------
SIZE_DERIVED_FIELDS = {
    "size_first":    "尺码首值",
    "size_last":     "尺码末值",
    "size_span":     "尺码差值",
    "size_count":    "尺码个数",
    "size_has_half": "含半码",
}

# 老操作符（向后兼容，走 legacy 逻辑）
LEGACY_SIZE_OPS = ("尺码跨度大于", "含半码")

# 数值操作符别名
_NUM_OPS = {
    ">":  "gt", "大于":   "gt",
    "<":  "lt", "小于":   "lt",
    ">=": "ge", "大于等于": "ge",
    "<=": "le", "小于等于": "le",
    "=":  "eq", "==": "eq", "等于": "eq",
    "!=": "ne", "<>": "ne", "不等于": "ne",
}

_SIZE_SEP_RE = re.compile(r"[|,，、;；\s]+")


# ---------------------------------------------------------------
# 核心工具
# ---------------------------------------------------------------
def split_sizes(raw):
    """把 shoessize 字段拆成 float 列表；无法解析的片段丢弃。"""
    if raw is None:
        return []
    s = str(raw).strip()
    if not s:
        return []
    out = []
    for p in _SIZE_SEP_RE.split(s):
        p = p.strip()
        if not p:
            continue
        try:
            out.append(float(p))
        except ValueError:
            continue
    return out


def compute_derived(raw, field):
    """
    计算单个虚拟字段值。
    返回 float / int；无法计算时返回 None（表示"空值"）。
    """
    sizes = split_sizes(raw)

    if field == "size_count":
        return len(sizes)  # 空值 → 0（可被 "= 0" 命中）

    if not sizes:
        return None

    if field == "size_first":
        return sizes[0]
    if field == "size_last":
        return sizes[-1]
    if field == "size_span":
        return round(sizes[-1] - sizes[0], 1)
    if field == "size_has_half":
        return 1 if any(abs(s - int(s) - 0.5) < 1e-6 for s in sizes) else 0
    return None


def is_size_field(field):
    """判断是否为尺码派生字段（新虚拟字段）。"""
    return field in SIZE_DERIVED_FIELDS


# ---------------------------------------------------------------
# 新虚拟字段的单条评估
# ---------------------------------------------------------------
def match_condition(raw, field, op, value):
    """
    单条记录是否满足条件。
    raw:   shoessize 原始字符串
    field: 虚拟字段 key
    op:    > < >= <= = != 及中文别名；为空 / 不为空
    value: 用户输入
    """
    if op in ("为空", "is_null"):
        return compute_derived(raw, field) is None
    if op in ("不为空", "not_null"):
        return compute_derived(raw, field) is not None

    cur = compute_derived(raw, field)
    if cur is None:
        return False  # 空值不命中（已确认）

    try:
        v = float(value)
    except (ValueError, TypeError):
        return False

    kind = _NUM_OPS.get(op)
    if kind == "gt": return cur >  v
    if kind == "lt": return cur <  v
    if kind == "ge": return cur >= v
    if kind == "le": return cur <= v
    if kind == "eq": return abs(cur - v) < 1e-6
    if kind == "ne": return abs(cur - v) >= 1e-6
    return False


# ---------------------------------------------------------------
# 老操作符兼容逻辑（从 f_query.py 迁移）
# ---------------------------------------------------------------
def _check_size_span_legacy(value, kw):
    """老逻辑：找相邻尺码差值 > 阈值的行（任意相邻对）"""
    if not value or not kw:
        return False
    try:
        threshold = float(kw)
    except ValueError:
        return False

    nums = sorted(set(split_sizes(value)))
    if len(nums) < 2:
        return False

    for i in range(len(nums) - 1):
        if nums[i + 1] - nums[i] > threshold + 0.01:
            return True
    return False


def _check_has_half_legacy(value, kw):
    """
    老逻辑：是否含半码
    kw: "否"/"no"/"n"/"0"/"没有" → 找不含的；否则找含的
    """
    sizes = split_sizes(value)
    has_half = any(abs(s - int(s) - 0.5) < 1e-6 for s in sizes)
    if kw in ("否", "no", "n", "0", "没有"):
        return not has_half
    return has_half


# ---------------------------------------------------------------
# 统一评估入口（供 f_query.py 调用）
# ---------------------------------------------------------------
def evaluate_row_condition(row, field, op, kw):
    """
    评估单行记录是否满足条件。
    row: dict（含 shoessize）
    field / op / kw: 条件三要素
    """
    raw = ""
    if hasattr(row, "get"):
        raw = row.get("shoessize") or ""

    # 老兼容操作符
    if op == "尺码跨度大于":
        return _check_size_span_legacy(raw, kw)
    if op == "含半码":
        return _check_has_half_legacy(raw, kw)

    # 新虚拟字段
    return match_condition(raw, field, op, kw)


# ---------------------------------------------------------------
# 自测（python -m tabs.tab_f.f_size_filter）
# ---------------------------------------------------------------
if __name__ == "__main__":
    samples = [
        ("36|37|38|39|40|41|42|43|44|45", 36, 45, 9, 10, 0),
        ("29|30|31|32|33|34",             29, 34, 5, 6,  0),
        ("28|29|30",                      28, 30, 2, 3,  0),
        ("25|26|27",                      25, 27, 2, 3,  0),
        ("36.5|37|38|39",                 36.5, 39, 2.5, 4, 1),
        ("35|36|37|38",                   35, 38, 3, 4,  0),
        ("40|41|42|43|44|45|46|47",       40, 47, 7, 8,  0),
        ("36",                            36, 36, 0, 1,  0),
        ("36|45",                         36, 45, 9, 2,  0),
        ("",                              None, None, None, 0, None),
    ]
    print(f"{'样本':<35}{'首':>6}{'末':>6}{'差':>6}{'数':>5}{'半':>4}")
    for raw, f, l, s, c, h in samples:
        first = compute_derived(raw, "size_first")
        last  = compute_derived(raw, "size_last")
        span  = compute_derived(raw, "size_span")
        cnt   = compute_derived(raw, "size_count")
        half  = compute_derived(raw, "size_has_half")
        ok = (first == f and last == l and span == s
              and cnt == c and half == h)
        flag = "OK" if ok else "NG"
        print(f"[{flag}] {repr(raw):<30}{str(first):>6}{str(last):>6}"
              f"{str(span):>6}{str(cnt):>5}{str(half):>4}")

    print("\n--- 用例 ---")
    assert match_condition("28|29|30", "size_first", "<", 29) is True
    assert match_condition("29|30|31", "size_first", "<", 29) is False
    assert match_condition("", "size_first", "<", 29) is False
    assert match_condition("36|45", "size_span", ">", 4) is True
    assert match_condition("36|38", "size_span", ">", 4) is False
    assert match_condition("", "size_count", "=", 0) is True
    assert match_condition("36.5|37", "size_has_half", "=", 1) is True
    assert _check_size_span_legacy("36,38,40", "1") is True
    assert _check_has_half_legacy("36.5,37", "") is True
    print("全部用例通过")