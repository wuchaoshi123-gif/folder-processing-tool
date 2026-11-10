# core/g2_generator.py
"""
G2 欧众ozon专属多进程生成器
基于 G1 修改：
  - 单文件限制改为按 xlsx 行数计算
  - A 组图片字段去掉了 Image 2~5，改为一个包含所有副图的 附加图片链接
  - 新增 词汇过滤（不区分大小写，全词匹配替换 NAME_RU）
"""
import random
import re
import math
import os
import time
from pathlib import Path
from datetime import datetime
import concurrent.futures as cf

try:
    from openpyxl import load_workbook

    _XLSX_OK = True
except ImportError:
    _XLSX_OK = False

# ============================================================
#  默认配置 (G2 专属)
# ============================================================
DEFAULT_G2_CONFIG = {
    "template_dir": "",
    "output_dir": "",
    "header_row": 1,
    "data_start_row": 2,
    "max_lines_per_file": 1000,  # 限制行数
    "replace_file": "",  # ★ 词汇过滤表路径

    "img_suffix": "",
    "first_img": "1.jpg",

    "keyword_file": "关键词.txt",
    "keyword_pos": "random",
    "name_max_len_ru": 255,
    "name_max_len_en": 128,

    "profit_rate": 1.10,
    "discount": 0.75,
    "platform_fee": 0.17,
    "freight_min": 66,
    "freight_max": 99,

    "desc_html_prefix": """<h1><strong>Заметка</strong></h1>
<h3><em>Наша посылка будет отправлена в почтовое отделение в России через почтовую
системуПосылка прибудет в ваше местное российское почтовое
отделениеПожалуйста свяжитесь с местным почтовым отделением чтобы получить
вашу посылку.</em></h3>
<h3><em>Пожалуйста не выбирайте отдельно &quot;ящик для обуви&quot;.Это не
правильный размер обуви и наша фабрика не может отправить его отдельноЕсли
вам нужна пара обуви с коробкойВы можете выбрать &quot;ящик для обуви&quot;
+ правильный размерЭто правильный способ совершить покупку</em></h3>""",

    "fields_a": [
        ["Model (seller SPU ID)*", "GROUP"],
        ["Product name (Russian)", "NAME_RU"],
        ["Product name (English)*", "NAME_EN"],
        ["Main image*", "MAIN_IMAGE"],
        ["附加图片链接", "EXTRA_IMAGES + ('\\n' + IMAGE_6 if IMAGE_6 else '')"],
        ["Description (Russian)", "DESC_HTML"],
        ["Discounted price, CNY", "calc_price(CHUPRICE)"],
        ["Price, CNY*", "Discounted_price_CNY*3"],
        ["组成", "brand_or_empty(BANDS)"],
    ],
    "fields_b": [
        ["SKU ID", "SKU_ID"],
        ["Size", "SIZE"],
    ],
    "fields_c": [
        ["物品", "板鞋"],
        ["说明书", "Для защиты обуви Наша упаковка удалила коробку для обуви"],
        ["颜色", "Multi"],
        ["每包装数量", "1"],
    ],
}


# ============================================================
#  词典加载与替换工具
# ============================================================
def load_replace_dict(file_path):
    """读取 ozonbandchange.txt 格式：adidas=AD"""
    d = {}
    if not file_path or not os.path.exists(file_path):
        return d
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    k, v = line.split('=', 1)
                    d[k.strip().lower()] = v.strip()
    except Exception as e:
        print(f"[G2] 词典读取失败: {e}")
    return d


def apply_replace(text, replace_dict):
    """
    对文本进行全词匹配替换（不区分大小写）
    使用前后断言 (?<![a-zA-Z0-9]) 和 (?![a-zA-Z0-9])，避免使用 \b 导致中文环境匹配失败
    """
    if not text or not replace_dict:
        return text

    # 按长度从大到小排序，确保先匹配长词（如 new balance 优先于 balance）
    keys = sorted(replace_dict.keys(), key=len, reverse=True)
    if not keys:
        return text

    # 转义特殊字符，拼接成正则
    escaped_keys = [re.escape(k) for k in keys]
    pattern = re.compile(r'(?<![a-zA-Z0-9])(' + '|'.join(escaped_keys) + r')(?![a-zA-Z0-9])', re.IGNORECASE)

    def repl(m):
        word = m.group(1).lower()
        return replace_dict.get(word, m.group(1))

    return pattern.sub(repl, text)


# ============================================================
#  表达式求值
# ============================================================
def _make_eval_context():
    return {
        "int": int, "float": float, "str": str, "len": len,
        "abs": abs, "round": round, "min": min, "max": max,
        "random": random,
        "rand": lambda a, b: random.randint(int(a), int(b)),
        "rand11": lambda: (datetime.now().strftime("%y%m%d")
                           + "".join(random.choices("0123456789", k=11))),
        "rand_date_prefix": lambda: datetime.now().strftime("%y%m%d"),
        "choice": lambda seq: random.choice(list(seq)),
        "join": lambda sep, items: str(sep).join(str(x) for x in items),
        "brand_or_empty": lambda b: ("" if (not b or str(b).strip().lower() == "allall") else b),
    }


def _eval_with_scope(expr, scope, on_error=None):
    if expr is None: return ""
    expr = str(expr).strip()
    if not expr: return ""
    try:
        ctx = _make_eval_context()
        ctx.update(scope)
        return eval(expr, {"__builtins__": {}}, ctx)
    except Exception as e:
        if on_error: on_error(f"表达式 {expr!r} 求值失败: {e}")
        return ""


def _add_safe_aliases(scope):
    for k, v in list(scope.items()):
        safe_k = str(k).replace(' ', '_').replace(',', '').replace('，', '')
        if safe_k != k:
            scope[safe_k] = v
    return scope


# ============================================================
#  工具函数
# ============================================================
def _is_number(s):
    try:
        float(s); return True
    except:
        return False


def split_sizes(shoessize):
    if not shoessize: return []
    parts = re.split(r"[,，、\s]+", str(shoessize).strip())
    return [p.strip() for p in parts if p.strip()]


def _truncate_by_word(text, max_len):
    if not text or len(text) <= max_len: return text
    words = text.split()
    result, cur_len = [], 0
    for w in words:
        add = len(w) + (1 if result else 0)
        if cur_len + add > max_len: break
        result.append(w);
        cur_len += add
    return " ".join(result) if result else text[:max_len]


KEY_TERMS = ("обувь", "кроссовки")


def _ensure_key_terms(rufanyi):
    if not rufanyi: return rufanyi
    lower = rufanyi.lower()
    prefix = [term for term in KEY_TERMS if term not in lower]
    return " ".join(prefix) + " " + rufanyi if prefix else rufanyi


def build_names(rufanyi, englishname, keyword, position, max_len_ru, max_len_en):
    ru = _ensure_key_terms((rufanyi or "").strip())
    kw = (keyword or "").strip()
    if kw:
        kw_space = len(kw) + 1
        ru_max = max_len_ru - kw_space if max_len_ru > kw_space else max_len_ru
        use_before = random.random() < 0.5 if position == "random" else (position == "before")
        if len(ru) > ru_max: ru = _truncate_by_word(ru, ru_max)
        ru_name = f"{kw} {ru}".strip() if use_before else f"{ru} {kw}".strip()
    else:
        ru_name = ru
    if max_len_ru and len(ru_name) > max_len_ru: ru_name = _truncate_by_word(ru_name, max_len_ru)

    en_name = (englishname or "").strip()
    if max_len_en and len(en_name) > max_len_en: en_name = _truncate_by_word(en_name, max_len_en)
    return " ".join(ru_name.split()), " ".join(en_name.split())


def load_keywords(path):
    p = Path(path)
    if not p.exists(): return []
    return [line.strip() for line in open(p, "r", encoding="utf-8-sig", errors="ignore") if
            line.strip() and not line.startswith("#")]


def make_price_calculator(profit_rate, discount, platform_fee, freight_min, freight_max):
    denom = discount * (1 - platform_fee)
    if denom <= 0: denom = 1e-9

    def calc_price(cost, freight=None):
        try:
            c = float(cost)
        except:
            return 0
        f = random.randint(int(freight_min), int(freight_max)) if freight is None else float(freight)
        return round((c * (1 + float(profit_rate)) + f) / denom)

    return calc_price


# ============================================================
#  欧众图片与 HTML 拼接核心
# ============================================================
def process_ae_images(web_url, bandsizechart, config):
    suffix = (config.get("img_suffix") or "").strip()
    first_name = (config.get("first_img") or "1.jpg").strip().lower()

    urls = [u.strip() for u in (web_url or "").split("\n") if u.strip()]
    if suffix: urls = [(u if "?" in u else u + suffix) for u in urls]

    size_chart = (bandsizechart or "").strip()
    if size_chart and suffix:
        size_chart = size_chart if "?" in size_chart else size_chart + suffix

    main_img, others = None, []
    for u in urls:
        fname = u.split("?")[0].split("/")[-1].lower()
        if fname == first_name and main_img is None:
            main_img = u
        else:
            others.append(u)

    if main_img is None and others:
        def _num(u):
            s = u.split("?")[0].split("/")[-1].rsplit(".", 1)[0]
            return int(s) if s.isdigit() else 999999

        others.sort(key=_num)
        main_img = others.pop(0)

    # 将剩余所有图片和尺码表用换行符连接（作为备用变量）
    others_for_extra = list(others)
    if size_chart:
        others_for_extra.append(size_chart)
    extra_images_default = "\n".join(others_for_extra)

    img6 = size_chart

    all_imgs_for_html = list(urls)
    random.shuffle(all_imgs_for_html)
    if size_chart: all_imgs_for_html.append(size_chart)

    images_html = ""
    for u in all_imgs_for_html:
        images_html += f'\n<p><img src="{u}"></p>'

    html_prefix = config.get("desc_html_prefix", "")
    desc_html = html_prefix + images_html

    return main_img or "", extra_images_default, img6, desc_html, images_html


# ============================================================
#  生成产品行 (包含词汇替换逻辑)
# ============================================================
def generate_product_rows(p, config, keywords, replace_dict, errors=None):
    on_error = (errors.append if errors is not None else None)

    rufanyi = p.get("rufanyi", "") or ""
    englishname = p.get("englishname", "") or ""
    chuprice = p.get("chuprice") or 0
    web_url = p.get("web_url", "") or ""
    bandsizechart = p.get("bandsizechart", "") or ""
    shoessize = p.get("shoessize", "") or ""
    bands = p.get("bands", "") or ""

    # ★ 关键修改 1：在生成名称之前，先对原始 rufanyi 进行词典替换
    if replace_dict:
        rufanyi = apply_replace(rufanyi, replace_dict)

    calc_price = make_price_calculator(
        float(config.get("profit_rate", 1.10)), float(config.get("discount", 0.75)),
        float(config.get("platform_fee", 0.17)), int(config.get("freight_min", 66)),
        int(config.get("freight_max", 99))
    )

    main_img, extra_images_default, img6, desc_html, images_html = process_ae_images(web_url, bandsizechart, config)

    keyword = random.choice(keywords) if keywords else ""
    # 生成名称（基于已经替换过的 rufanyi）
    name_ru, name_en = build_names(rufanyi, englishname, keyword, config.get("keyword_pos", "random"),
                                   int(config.get("name_max_len_ru") or 255), int(config.get("name_max_len_en") or 128))

    # ★ 关键修改 2：为了防范关键词里混入品牌词，再对最终生成的 name_ru 替换一次
    if replace_dict:
        name_ru = apply_replace(name_ru, replace_dict)

    group_id = (datetime.now().strftime("%y%m%d") + "".join(random.choices("0123456789", k=11)))

    a_scope = {
        # 这里的 RUFANYI 和 NAME_RU 都已经过替换
        "RUFANYI": rufanyi,
        "ENGLISHNAME": englishname,
        "CHUPRICE": chuprice,
        "WEBURL": web_url,
        "BANDSIZECHART": bandsizechart,
        "SHOESSIZE": shoessize,
        "BANDS": bands,
        "KEYWORD": keyword,
        "GROUP": group_id,
        "NAME_RU": name_ru,
        "NAME_EN": name_en,
        "MAIN_IMAGE": main_img,
        "EXTRA_IMAGES": extra_images_default,
        "IMAGE_6": img6,
        "DESC_HTML": desc_html,
        "HTML_PREFIX": config.get("desc_html_prefix", ""),
        "IMAGES_HTML": images_html,
        "calc_price": calc_price,
    }

    a_fields = {}
    for col, expr in config.get("fields_a", []):
        scope = _add_safe_aliases({**a_scope, **a_fields})
        a_fields[col] = _eval_with_scope(expr, scope, on_error)

    sizes = split_sizes(shoessize) or [""]
    rows = []
    for idx, size in enumerate(sizes, start=1):
        size_int = int(float(size)) if _is_number(size) and float(size).is_integer() else (
            float(size) if _is_number(size) else None)
        b_scope = {
            **a_scope, **a_fields, "SIZE": size, "SIZE_INT": size_int,
            "SKU_ID": f"{group_id}-{idx}",
        }

        b_fields = {}
        for col, expr in config.get("fields_b", []):
            scope = _add_safe_aliases({**b_scope, **b_fields})
            b_fields[col] = _eval_with_scope(expr, scope, on_error)

        row = {**a_fields, **b_fields}
        for col, val in config.get("fields_c", []):
            row[col] = val
        rows.append(row)

    return rows

# ============================================================
#  多进程任务与分发（按行数切分）
# ============================================================
def _worker_generate_file(args):
    template_path, output_path, products, config, keywords = args
    try:
        # 确保多进程环境下的随机性
        random.seed(os.getpid() + int(time.time() * 1000))

        # 子进程内加载词典
        replace_dict = load_replace_dict(config.get("replace_file", ""))

        errors, all_rows = [], []
        for p in products:
            all_rows.extend(generate_product_rows(p, config, keywords, replace_dict, errors))

        # ==========================================
        # 1. 生成主数据表 (oo03_1.xlsx)
        # ==========================================
        wb = load_workbook(str(template_path))
        ws = wb.active
        header_row, start_row = int(config.get("header_row") or 1), int(config.get("data_start_row") or 2)

        col_map = {str(cell.value).strip(): col_idx for col_idx, cell in enumerate(ws[header_row], 1) if cell.value}
        if ws.max_row >= start_row: ws.delete_rows(start_row, ws.max_row - start_row + 1)

        missing = set()
        for i, row_data in enumerate(all_rows):
            r_idx = start_row + i
            for c_name, val in row_data.items():
                c_idx = col_map.get(c_name)
                if not c_idx:
                    missing.add(c_name);
                    continue
                ws.cell(row=r_idx, column=c_idx, value=val)

        wb.save(str(output_path))

        # ==========================================
        # 2. 生成同步库存表 (oo03_1-库存.xlsx)
        # ==========================================
        inv_tpl_dir = config.get("inv_tpl_dir", "")
        if inv_tpl_dir and os.path.isdir(inv_tpl_dir):
            tpl_stem = Path(template_path).stem  # 获取 oo03
            # 寻找库存模板（包含 oo03 且包含 库存 的 xlsx）
            inv_tpl_path = None
            for f in Path(inv_tpl_dir).glob("*.xlsx"):
                if tpl_stem in f.stem and "库存" in f.stem:
                    inv_tpl_path = f
                    break

            if inv_tpl_path:
                inv_wb = load_workbook(str(inv_tpl_path))
                # 判断有没有 "仓库库存" 页
                if "仓库库存" in inv_wb.sheetnames:
                    inv_ws = inv_wb["仓库库存"]

                    # 获取第一行数据作为下拉复制的基准值
                    base_warehouse = "PT (1020005037016190)"
                    base_stock = 9
                    if inv_ws.max_row >= 2:
                        val_a = inv_ws.cell(row=2, column=1).value
                        val_d = inv_ws.cell(row=2, column=4).value
                        if val_a is not None: base_warehouse = val_a
                        if val_d is not None: base_stock = val_d

                    # 清空原来的数据（保留第一行表头）
                    if inv_ws.max_row >= 2:
                        inv_ws.delete_rows(2, inv_ws.max_row - 1)

                    # 将当前的 SKU_ID 填入库存表
                    for i, row_data in enumerate(all_rows):
                        r_idx = 2 + i
                        # A列：仓库名称
                        inv_ws.cell(row=r_idx, column=1, value=base_warehouse)
                        # B列：货号 (从我们生成的数据中提取 货号* 或 SKU_ID)
                        sku_val = row_data.get("货号*", row_data.get("SKU ID", ""))
                        inv_ws.cell(row=r_idx, column=2, value=sku_val)

                        # ★ C列：商品名称 留空
                        inv_ws.cell(row=r_idx, column=3, value="")

                        # D列：有现货
                        inv_ws.cell(row=r_idx, column=4, value=base_stock)

                    # 保存为 oo03_1-库存.xlsx
                    inv_out_name = f"{Path(output_path).stem}-库存.xlsx"
                    inv_out_path = Path(output_path).parent / inv_out_name
                    inv_wb.save(str(inv_out_path))
                else:
                    print(f"[G2] ⚠️ 库存模板 {inv_tpl_path.name} 中未找到 '仓库库存' 工作表")
            else:
                print(f"[G2] ⚠️ 未找到与 {tpl_stem} 匹配的库存模板")

        return True, str(output_path), list(missing), errors[:5]
    except Exception as e:
        return False, str(output_path), [], [str(e)]


def generate_xlsx_multi(products, config, progress_cb=None):
    if not _XLSX_OK: raise RuntimeError("缺少 openpyxl")

    tpl_dir, out_dir = Path(config["template_dir"]), Path(config["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    templates = [f for f in tpl_dir.glob("*.xlsx") if not f.name.startswith("~$")]
    if not templates: raise ValueError("未找到任何模板")

    keywords = load_keywords(config.get("keyword_file") or "关键词.txt")
    max_lines = int(config.get("max_lines_per_file") or 1000)

    # 核心修改：按行数切分产品
    chunks = []
    current_chunk = []
    current_lines = 0

    for p in products:
        sizes = split_sizes(p.get("shoessize", "")) or [""]
        p_lines = len(sizes)

        if current_lines + p_lines > max_lines and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_lines = 0

        current_chunk.append(p)
        current_lines += p_lines

    if current_chunk:
        chunks.append(current_chunk)

    total_files = len(chunks)
    base_per_tpl = total_files // len(templates)
    remainder = total_files % len(templates)

    tasks = []
    c_idx = 0
    for i, tpl in enumerate(templates):
        files_this_tpl = base_per_tpl + (1 if i < remainder else 0)
        for f_idx in range(1, files_this_tpl + 1):
            chunk = chunks[c_idx]
            c_idx += 1
            tasks.append((tpl, out_dir / f"{tpl.stem}_{f_idx}.xlsx", chunk, config, keywords))

    if progress_cb: progress_cb(f"开始并发生成 {len(tasks)} 个文件...")

    success, all_missing, all_errors = 0, set(), []
    with cf.ProcessPoolExecutor(max_workers=min(os.cpu_count() or 4, 8)) as ex:
        futures = {ex.submit(_worker_generate_file, t): t for t in tasks}
        for idx, fut in enumerate(cf.as_completed(futures)):
            ok, path, miss, errs = fut.result()
            if ok:
                success += 1
            else:
                all_errors.extend(errs)
            all_missing.update(miss)
            if progress_cb: progress_cb(f"已生成 {idx + 1}/{len(tasks)} 份")

    return success, len(tasks), list(all_missing), all_errors


def format_preview(products, config, max_products=3, max_value_len=100):
    keywords = load_keywords(config.get("keyword_file") or "关键词.txt")
    replace_dict = load_replace_dict(config.get("replace_file", ""))  # 预览时也加载
    lines = []
    for i, p in enumerate(products[:max_products]):
        rows = generate_product_rows(p, config, keywords, replace_dict)
        lines.append(f"═══ 产品 {i + 1}: {p.get('onlymulu', '')} ═══")
        for j, row in enumerate(rows):
            lines.append(f"  ── 行 {j + 1} ──")
            for col, val in row.items():
                v = str(val)
                if len(v) > max_value_len: v = v[:max_value_len] + f"... (+{len(v) - max_value_len})"
                lines.append(f"    {col:<20} = {v}")
        lines.append("")
    return "\n".join(lines)