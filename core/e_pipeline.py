# core/e_pipeline.py
"""
E 模块 OCR 流水线（完整修复版 v6）
  · 修复 _log 递归 bug
  · 删除重复的 _get_temp_dir_for
  · parse_sizes 支持紧凑数字串
  · 中下区域放大拼接重试
"""
# ============================================================
#  屏蔽警告
# ============================================================
from PIL import ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

import os
os.environ["PYTHONWARNINGS"] = "ignore"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["OPENCV_LOG_LEVEL"] = "ERROR"

import logging
logging.getLogger("PIL").setLevel(logging.ERROR)
logging.getLogger("PIL.JpegImagePlugin").setLevel(logging.ERROR)
logging.getLogger("torch").setLevel(logging.ERROR)

# ============================================================
#  依赖
# ============================================================
import re
import uuid
import shutil
import tempfile
import threading
from pathlib import Path

# ============================================================
#  静默日志
# ============================================================
SILENT_MODE = True


def _log(*args, **kwargs):
    """内部日志函数（修复: 原版递归调用自己）"""
    if not SILENT_MODE:
        print(*args, **kwargs)


# ============================================================
#  引擎状态
# ============================================================
_OCR_BACKEND = None
_OCR_ENGINE = None


# ============================================================
#  临时目录
# ============================================================
_TEMP_DIRS = {}
_TEMP_LOCK = threading.Lock()


def _get_temp_dir_for(src_path):
    """获取临时目录（同盘优先，只保留这一份定义）"""
    src = Path(src_path)
    drive = src.drive
    cache_key = drive or "__sys__"

    d = _TEMP_DIRS.get(cache_key)
    if d and d.exists():
        return d

    with _TEMP_LOCK:
        d = _TEMP_DIRS.get(cache_key)
        if d and d.exists():
            return d

        if drive:
            same_disk = Path(drive + "\\_pyturboocr_tmp")
            try:
                same_disk.mkdir(exist_ok=True)
                _TEMP_DIRS[cache_key] = same_disk
                _log(f"[OCR] 临时目录(同盘): {same_disk}")
                return same_disk
            except Exception as e:
                _log(f"[OCR] 同盘临时目录不可用 ({e})，回退系统目录")

        sys_tmp = Path(tempfile.gettempdir()) / "pyturboocr_tmp"
        sys_tmp.mkdir(exist_ok=True)
        _TEMP_DIRS[cache_key] = sys_tmp
        _log(f"[OCR] 临时目录(系统): {sys_tmp}")
        return sys_tmp


# ============================================================
#  引擎初始化
# ============================================================
def _detect_backend():
    global _OCR_BACKEND, _OCR_ENGINE
    if _OCR_BACKEND is not None:
        return _OCR_BACKEND

    try:
        from pyturboocr import OCR

        cache_dir = r"C:\Users\Newkuangren\.cache\tensorrt_engine_cache"
        os.makedirs(cache_dir, exist_ok=True)

        trt_options = {
            'device_id': 0,
            'trt_fp16_enable': False,
            'trt_engine_cache_enable': True,
            'trt_engine_cache_path': cache_dir,
            'trt_timing_cache_enable': True,
            'trt_timing_cache_path': cache_dir,
            'trt_force_sequential_engine_build': True,
        }

        providers = [
            ('TensorrtExecutionProvider', trt_options),
            'CUDAExecutionProvider',
            'CPUExecutionProvider',
        ]

        _OCR_ENGINE = OCR(tier="small", providers=providers)
        _OCR_BACKEND = "pyturboocr"
        print("✅ OCR 引擎: pyturboocr (TensorRT)")
        return _OCR_BACKEND
    except Exception as e:
        print(f"⚠️ pyturboocr 初始化失败: {e}")

    try:
        from rapidocr_onnxruntime import RapidOCR
        _OCR_ENGINE = RapidOCR()
        _OCR_BACKEND = "rapidocr"
        print("✅ OCR 引擎: RapidOCR (CPU)")
        return _OCR_BACKEND
    except Exception as e:
        print(f"⚠️ RapidOCR 初始化失败: {e}")

    _OCR_BACKEND = "none"
    return _OCR_BACKEND


def init_ocr_worker():
    _detect_backend()


# ============================================================
#  OCR 辅助
# ============================================================
def _ocr_path_or_image(target):
    try:
        result = _OCR_ENGINE.recognize_image(str(target))
        if result is None:
            return ""
        return getattr(result, "text", "") or ""
    except Exception as e:
        _log(f"   [OCR 失败: {e}]")
        return ""


def cleanup_temp_files():
    """清理所有临时文件"""
    count = 0
    for key, d in list(_TEMP_DIRS.items()):
        if not d or not d.exists():
            continue
        try:
            for f in d.iterdir():
                try:
                    f.unlink()
                    count += 1
                except Exception:
                    pass
        except Exception:
            pass
    return count




def _read_text(image_path):
    """
    ★ 极简版：不做任何图片预处理，直接 OCR
      · 纯英文路径 → 直接读
      · 中文路径 → 硬链接到临时目录（秒级）
    """
    backend = _detect_backend()
    if backend == "none":
        return "", "OCR 引擎未安装"

    if backend == "pyturboocr":
        temp_path = None
        try:
            src = Path(image_path)
            if not src.exists():
                return "", "图片不存在"

            try:
                if src.stat().st_size < 1000:
                    return "", "图片文件异常小"
            except Exception:
                pass

            # 判断路径是否含中文
            try:
                str(src).encode("ascii")
                is_ascii = True
            except UnicodeEncodeError:
                is_ascii = False

            # ★ 纯英文路径 → 直接读
            if is_ascii:
                return _ocr_path_or_image(src), ""

            # ★ 中文路径 → 硬链接到临时目录（不复制字节）
            temp_dir = _get_temp_dir_for(src)
            temp_path = temp_dir / f"{uuid.uuid4().hex}.jpg"

            try:
                os.link(str(src), str(temp_path))       # 硬链接（秒级）
            except (OSError, AttributeError):
                try:
                    shutil.copy2(str(src), str(temp_path))   # 回退复制
                except Exception as e:
                    return "", f"临时文件失败: {str(e)[:80]}"

            return _ocr_path_or_image(temp_path), ""

        except Exception as e:
            return "", f"pyturboocr 失败: {str(e)[:120]}"
        finally:
            if temp_path:
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    elif backend == "rapidocr":
        try:
            from PIL import Image
            import numpy as np
            with Image.open(image_path) as img:
                arr = np.array(img.convert("RGB"))
            result, _ = _OCR_ENGINE(
                arr, use_det=True, use_cls=False, use_rec=True)
            if not result:
                return "", ""
            return " ".join([item[1] for item in result]), ""
        except Exception as e:
            return "", f"RapidOCR 失败: {str(e)[:120]}"

    return "", "未知引擎"

# ============================================================
#  阶段 2: 中下区域放大拼接重试
# ============================================================
MIDDLE_BOTTOM_REGION = (0.10, 0.60, 0.90, 1.00)
MIDDLE_BOTTOM_UPSCALE = 6.0         # ★ 3.0 → 6.0
MIDDLE_BOTTOM_MIN_SIDE = 1200       # ★ 900 → 1200


def _crop_middle_bottom_and_merge(src_path):
    """
    ★ 中下拼接版（JPEG 保存，避免大 PNG 拖慢）
    """
    temp_path = None
    try:
        from PIL import Image, ImageEnhance

        src = Path(src_path)
        if not src.exists():
            return None

        with Image.open(str(src)) as img:
            img = img.convert("RGB")
            W, H = img.size

            # 中下区域（45%）
            x1 = int(W * 0.05)
            y1 = int(H * 0.55)
            x2 = int(W * 0.95)
            y2 = H
            crop = img.crop((x1, y1, x2, y2))

            # ★ 放大 4 → 3 倍（更小更快）
            cw, ch = crop.size
            new_w = int(cw * 3.0)
            new_h = int(ch * 3.0)
            crop = crop.resize((new_w, new_h), Image.LANCZOS)

            # 对比度增强
            crop = ImageEnhance.Contrast(crop).enhance(1.4)

            # ★★ 保存为 JPEG（quality 85）—— 关键修复
            temp_dir = _get_temp_dir_for(src)
            temp_path = temp_dir / f"{uuid.uuid4().hex}_mb.jpg"
            crop.save(str(temp_path), "JPEG", quality=85)

        return temp_path
    except Exception as e:
        _log(f"[重试-裁剪失败] {e}")
        if temp_path and Path(str(temp_path)).exists():
            try:
                Path(str(temp_path)).unlink()
            except Exception:
                pass
        return None

# ============================================================
#   ★ 底部正中窄条超放大（针对小字体尺码）
# ============================================================
BOTTOM_CENTER_REGION = (0.15, 0.90, 0.85, 1.00)   # 底部 10% 高，中间 70% 宽
BOTTOM_CENTER_UPSCALE = 5.0                        # 放大 5 倍
BOTTOM_CENTER_MAX_SIDE = 4000                      # 最大边限制
BOTTOM_CENTER_MIN_HEIGHT = 250                     # 放大后最小高度


def _crop_bottom_center_and_upscale(src_path):
    """
    ★ 裁剪底部正中窄条 + 高倍放大
    专门针对底部的水平尺码行（如 "36 36.5 37.5 ... 45"）
    返回: 临时文件 Path 或 None
    """
    temp_path = None
    try:
        from PIL import Image

        src = Path(src_path)
        if not src.exists():
            return None

        with Image.open(str(src)) as img:
            img = img.convert("RGB")
            W, H = img.size

            # 底部正中窄条
            x1 = int(W * BOTTOM_CENTER_REGION[0])
            y1 = int(H * BOTTOM_CENTER_REGION[1])
            x2 = int(W * BOTTOM_CENTER_REGION[2])
            y2 = int(H * BOTTOM_CENTER_REGION[3])
            crop = img.crop((x1, y1, x2, y2))

            cw, ch = crop.size

            # 按倍数放大
            new_w = int(cw * BOTTOM_CENTER_UPSCALE)
            new_h = int(ch * BOTTOM_CENTER_UPSCALE)

            # 保证最小高度（OCR 检测需要）
            if new_h < BOTTOM_CENTER_MIN_HEIGHT:
                factor = BOTTOM_CENTER_MIN_HEIGHT / new_h
                new_w = int(new_w * factor)
                new_h = int(new_h * factor)

            # 限制最大边
            max_side = max(new_w, new_h)
            if max_side > BOTTOM_CENTER_MAX_SIDE:
                factor = BOTTOM_CENTER_MAX_SIDE / max_side
                new_w = int(new_w * factor)
                new_h = int(new_h * factor)

            crop = crop.resize((new_w, new_h), Image.LANCZOS)

            # 上下各加 30px 白边（OCR 不贴边）
            padded = Image.new("RGB", (new_w, new_h + 60), (255, 255, 255))
            padded.paste(crop, (0, 30))

            temp_dir = _get_temp_dir_for(src)
            temp_path = temp_dir / f"{uuid.uuid4().hex}_bc.jpg"
            padded.save(str(temp_path), "JPEG", quality=95)

        return temp_path
    except Exception as e:
        _log(f"[底部正中-裁剪失败] {e}")
        if temp_path and Path(str(temp_path)).exists():
            try:
                Path(str(temp_path)).unlink()
            except Exception:
                pass
        return None

def _read_text_retry(image_path):
    """
    ★ 3B 重试识别 —— 用"挖空中间 + 上下拼接"
    """
    temp_path = _crop_top_bottom_merge(image_path)
    if temp_path is None:
        return "", "拼接失败"

    try:
        backend = _detect_backend()

        if backend == "pyturboocr" and _OCR_ENGINE is not None:
            result = _OCR_ENGINE.recognize_image(str(temp_path))
            text = getattr(result, "text", "") or "" if result else ""
            return text, ""

        if backend == "rapidocr":
            from PIL import Image
            import numpy as np
            with Image.open(str(temp_path)) as img:
                arr = np.array(img.convert("RGB"))
            result, _ = _OCR_ENGINE(
                arr, use_det=True, use_cls=False, use_rec=True)
            if not result:
                return "", ""
            return " ".join([item[1] for item in result]), ""

        return "", "无识别引擎"
    except Exception as e:
        return "", f"重试失败: {str(e)[:100]}"
    finally:
        if temp_path and Path(str(temp_path)).exists():
            try:
                Path(str(temp_path)).unlink()
            except Exception:
                pass


# ============================================================
#  尺码解析（★ v6: 支持紧凑数字串）
# ============================================================
def parse_sizes(text, banma=None):
    """
    从 OCR 文本提取尺码列表（★ v10）

    规则:
      1. 分数符号: ⅔ → .5, ⅓ → 删除
      2. 半码触发: "半"/"⅔"/"2/3"/"B 后缀"/端点 .5
      3. 端点 .5 + 有 banma: 用 banma 展开 [lo, hi] 范围
      4. 端点 .5 + 无 banma: 首 +0.5, 尾不动, 中间 +1
      5. 端点非 .5 非整数: 整条丢弃
      6. ★ 相邻差 > 1.5: 补全（不再丢弃）
         · 相邻两值有一是 .5 → 用 banma 补全
         · 都不是 .5 → 递增 1 补全
    """
    if not text:
        return None, False, "无文本"

    MAX_SIZE = 47.5
    MIN_SIZE = 25.0
    MIN_COUNT = 2

    # ==========================================================
    # 1. 分数符号处理
    # ==========================================================
    t = text
    t = re.sub(r'(\d+)⅔', r'\1.5', t)
    t = re.sub(r'⅓', '', t)
    t = re.sub(r'(\d+)\s*2/3', r'\1.5', t)
    t = re.sub(r'\s*1/3', '', t)

    # ==========================================================
    # 2. ★ has_ban 判定（增加端点 .5）
    # ==========================================================
    has_ban = (
            "半" in text or "含半" in text or "有半" in text or
            "⅔" in text or "2/3" in text or
            bool(re.search(r'\d+\s*[-~/_]\s*\d+\s*B(?![a-zA-Z])', text)) or
            bool(re.search(r'\d+\.5\s*[-~/_]', text)) or  # 首端 .5
            bool(re.search(r'[-~/_]\s*\d+\.5', text))  # 尾端 .5
    )

    # ==========================================================
    # 3. 常规预处理
    # ==========================================================
    t = t.replace("，", ",").replace("、", ",").replace("：", ":")
    t = t.replace("；", ";")
    t = t.replace("～", "~").replace("－", "-").replace("—", "-")
    t = t.replace("–", "-").replace("﹣", "-")
    t = t.replace("到", "-").replace("至", "-")
    t = re.sub(r'\b(?:to|TO|To|until|UNTIL|through|thru)\b', '-', t)
    t = re.sub(
        r'\b(?:EU|US|UK|CN|FR|EUR|JP|KR|Size|size|SIZE)\s*[:=]?\s*',
        ' ', t)
    t = t.replace("码", " ")
    t = re.sub(r'[;()\[\]{}<>《》「」【】#]', ' ', t)
    t = re.sub(r'(?<![a-zA-Z])B(?![a-zA-Z])', ' ', t)
    t = re.sub(r'\d{8,}', ' ', t)

    sizes = []
    fail = False
    fail_reason = None

    # ==========================================================
    # 4. 紧凑数字串拆分
    # ==========================================================
    def _decode_compact(s):
        s = s.replace(',', '.').replace('。', '.')
        out = []
        i = 0
        n = len(s)
        while i < n:
            if i + 4 <= n and s[i + 2] == '.' and s[i + 3].isdigit():
                try:
                    v = float(s[i:i + 4])
                    if MIN_SIZE <= v <= MAX_SIZE:
                        out.append(f"{v:.1f}".rstrip("0").rstrip("."))
                        i += 4
                        continue
                except ValueError:
                    pass
            if i + 3 <= n and s[i:i + 2].isdigit() and s[i + 2] == '5':
                base = int(s[i:i + 2])
                if MIN_SIZE <= base <= MAX_SIZE - 1:
                    out.append(f"{base}.5")
                    i += 3
                    continue
            if i + 2 <= n and s[i:i + 2].isdigit():
                v = int(s[i:i + 2])
                if MIN_SIZE <= v <= MAX_SIZE:
                    out.append(str(v))
                    i += 2
                    continue
            i += 1
        return out

    def _compact_replace(m):
        parts = _decode_compact(m.group(0))
        if len(parts) >= 3:
            sizes.extend(parts)
            return ' '
        return m.group(0)

    t = re.sub(r'(?<!\d)[\d.]{8,}(?!\d)', _compact_replace, t)

    # ==========================================================
    # 5. 范围 X-Y
    # ==========================================================
    range_pattern = re.compile(
        r"(\d{2}(?:\.\d)?)\s*[-~/_]\s*(\d{2}(?:\.\d)?)")
    consumed_spans = []

    for m in range_pattern.finditer(t):
        lo_s, hi_s = m.group(1), m.group(2)
        try:
            lo, hi = float(lo_s), float(hi_s)
        except ValueError:
            continue
        if lo > hi or lo < MIN_SIZE or hi > MAX_SIZE + 5:
            continue

        lo_is_int = (lo == int(lo))
        lo_is_half = (lo * 2 == int(lo * 2)) and not lo_is_int
        hi_is_int = (hi == int(hi))
        hi_is_half = (hi * 2 == int(hi * 2)) and not hi_is_int

        if not (lo_is_int or lo_is_half) or not (hi_is_int or hi_is_half):
            fail = True
            fail_reason = f"端点非法 [{lo_s}-{hi_s}]"
            break

        need_ban_expand = (lo_is_half or hi_is_half or has_ban)

        if need_ban_expand and banma:
            # ★ 用 banma 展开 [lo, hi] 范围
            for b in banma:
                try:
                    bv = float(b)
                    if lo <= bv <= hi:
                        if bv == int(bv):
                            sizes.append(str(int(bv)))
                        else:
                            sizes.append(
                                f"{bv:.1f}".rstrip("0").rstrip("."))
                except ValueError:
                    continue
        else:
            # ★ 无 banma: 首 .5 保留, 尾 .5 保留, 中间递增 1
            import math
            cur = lo
            while cur <= hi + 1e-9:
                if MIN_SIZE <= cur <= MAX_SIZE:
                    if cur == int(cur):
                        sizes.append(str(int(cur)))
                    else:
                        sizes.append(
                            f"{cur:.1f}".rstrip("0").rstrip("."))
                # 跳到下一个整数
                if cur == int(cur):
                    cur = cur + 1
                else:
                    cur = math.floor(cur) + 1

            # ★ 尾端 .5 追加（如果没被上面循环捕获）
            if hi_is_half and MIN_SIZE <= hi <= MAX_SIZE:
                hi_str = f"{hi:.1f}".rstrip("0").rstrip(".")
                if hi_str not in sizes:
                    sizes.append(hi_str)

        consumed_spans.append(m.span())

    if fail:
        return None, has_ban, fail_reason

    rest = t
    for start, end in reversed(consumed_spans):
        rest = rest[:start] + " " + rest[end:]

    # ==========================================================
    # 6. 4 位数字展开
    # ==========================================================
    def _split_4digit(m):
        s = m.group(0)
        a, b = int(s[:2]), int(s[2:])
        if MIN_SIZE <= a < b <= MAX_SIZE:
            for n in range(a, b + 1):
                if n <= MAX_SIZE:
                    sizes.append(str(n))
            return ' '
        return m.group(0)

    rest = re.sub(r'(?<!\d)\d{4}(?!\d)', _split_4digit, rest)

    # ==========================================================
    # 7. 孤立 2 位数字（枚举）
    # ==========================================================
    num_pattern = re.compile(r"(?<!\d)(\d{2}(?:\.\d)?)(?!\d)")
    enum_values = []
    for m in num_pattern.finditer(rest):
        val = float(m.group(1))
        if not (MIN_SIZE <= val <= MAX_SIZE):
            continue
        start, end = m.span()
        before = rest[start - 1] if start > 0 else ' '
        after = rest[end] if end < len(rest) else ' '
        if before.isalpha() and after.isalpha():
            continue
        enum_values.append(val)

    if enum_values:
        first = enum_values[0]
        last = enum_values[-1]

        first_is_int = (first == int(first))
        first_is_half = (first * 2 == int(first * 2)) and not first_is_int
        last_is_int = (last == int(last))
        last_is_half = (last * 2 == int(last * 2)) and not last_is_int

        if not (first_is_int or first_is_half) or \
                not (last_is_int or last_is_half):
            return None, has_ban, f"枚举端点非法 [{first}-{last}]"

        banma_set = set(banma) if banma else set()
        for v in enum_values:
            if v > MAX_SIZE:
                continue
            if v == int(v):
                sizes.append(str(int(v)))
                if has_ban and banma:
                    half = f"{int(v)}.5"
                    if half in banma_set and float(half) <= MAX_SIZE:
                        sizes.append(half)
            else:
                sizes.append(f"{v:.1f}".rstrip("0").rstrip("."))

    # ==========================================================
    # 8. 去重排序
    # ==========================================================
    def _key(x):
        try:
            return float(x)
        except ValueError:
            return 0

    if not sizes:
        return None, has_ban, "未识别到尺码"

    sizes = sorted(set(sizes), key=_key)

    # ==========================================================
    # 9. ★ 缺口补全（替代原来的"整条丢弃"）
    # ==========================================================
    def _is_half(v):
        """判断数值是否是 .5 结尾"""
        s = f"{v:.1f}".rstrip("0").rstrip(".")
        return ".5" in s

    def _fill_gaps(size_list, banma_list, threshold=1.5):
        """补全相邻差 > threshold 的缺口"""
        import math

        if len(size_list) < 2:
            return size_list

        floats = []
        for s in size_list:
            try:
                floats.append(float(s))
            except ValueError:
                pass
        if len(floats) < 2:
            return size_list

        floats = sorted(set(floats))
        banma_set = set()
        if banma_list:
            for b in banma_list:
                try:
                    banma_set.add(float(b))
                except ValueError:
                    continue

        result = [floats[0]]

        for i in range(1, len(floats)):
            prev = floats[i - 1]
            cur = floats[i]
            gap = cur - prev

            if gap > threshold:
                prev_is_half = _is_half(prev)
                cur_is_half = _is_half(cur)

                if (prev_is_half or cur_is_half) and banma_set:
                    # 用 banma 补全
                    for bv in sorted(banma_set):
                        if prev < bv < cur:
                            result.append(bv)
                else:
                    # ★ 递增 1 补全（从 prev 的下一个整数开始）
                    nxt = math.floor(prev) + 1.0
                    while nxt < cur - 0.01:
                        result.append(nxt)
                        nxt += 1.0

                result.append(cur)
            else:
                result.append(cur)

        out = []
        for f in result:
            if f == int(f):
                out.append(str(int(f)))
            else:
                out.append(f"{f:.1f}".rstrip("0").rstrip("."))
        return out

    sizes = _fill_gaps(sizes, banma)

    # ==========================================================
    # 10. 最终校验
    # ==========================================================
    sizes = [s for s in sizes if _key(s) <= MAX_SIZE]
    sizes = [s for s in sizes if _key(s) >= MIN_SIZE]

    if len(sizes) < MIN_COUNT:
        return None, has_ban, f"仅 {len(sizes)} 个尺码"

    return sizes, has_ban, ""
# ============================================================
#  单任务接口
# ============================================================
def ocr_one(args):
    idx, onlymulu, img_path, banma = args
    text, err = _read_text(img_path)
    if err:
        return (idx, None, False, "", err)
    if not text or not text.strip():
        return (idx, None, False, "", "OCR 未识别到文字")
    sizes, has_ban, reason = parse_sizes(text, banma)
    return (idx, sizes, has_ban, text, reason)


def get_backend_info():
    backend = _detect_backend()
    if backend == "pyturboocr":
        return "pyturboocr (GPU)"
    elif backend == "rapidocr":
        return "RapidOCR (CPU)"
    return "未安装任何 OCR 引擎"
# ============================================================
#   ★ 挖空中间：保留顶部 + 底部，放大后拼接
# ============================================================
TOP_BOTTOM_CONFIG = {
    "top_ratio": 0.15,
    "bot_ratio": 0.15,
    "gap": 20,
    "scale": 4.0,           # ★ 放大 4 倍
    "contrast": 1.5,
}


def _crop_top_bottom_merge(src_path, config=None):
    """
    ★ 挖空中间 + 顶部/底部放大 + 拼接
    """
    cfg = config or TOP_BOTTOM_CONFIG
    temp_path = None
    try:
        from PIL import Image, ImageEnhance

        src = Path(src_path)
        if not src.exists():
            return None

        with Image.open(str(src)) as img:
            img = img.convert("RGB")
            W, H = img.size

            # 1. 裁剪顶部
            top_h = int(H * cfg["top_ratio"])
            top = img.crop((0, 0, W, top_h))

            # 2. 裁剪底部
            bot_h = int(H * cfg["bot_ratio"])
            bot = img.crop((0, H - bot_h, W, H))

            # 3. ★ 放大（关键！）
            scale = cfg.get("scale", 1.0)
            if scale != 1.0:
                top = top.resize(
                    (max(1, int(top.width * scale)),
                     max(1, int(top.height * scale))),
                    Image.LANCZOS,
                )
                bot = bot.resize(
                    (max(1, int(bot.width * scale)),
                     max(1, int(bot.height * scale))),
                    Image.LANCZOS,
                )

            # 4. 对比度增强
            contrast = cfg.get("contrast", 1.0)
            if contrast != 1.0:
                top = ImageEnhance.Contrast(top).enhance(contrast)
                bot = ImageEnhance.Contrast(bot).enhance(contrast)

            # 5. 上下拼接
            gap = cfg.get("gap", 20)
            total_w = max(top.width, bot.width)
            total_h = top.height + bot.height + gap

            merged = Image.new("RGB", (total_w, total_h), (255, 255, 255))
            merged.paste(top, (0, 0))
            merged.paste(bot, (0, top.height + gap))

            # 6. 保存
            temp_dir = _get_temp_dir_for(src)
            temp_path = temp_dir / f"{uuid.uuid4().hex}_tb.jpg"
            merged.save(str(temp_path), "JPEG", quality=92)

        return temp_path
    except Exception as e:
        _log(f"[上下拼接失败] {e}")
        if temp_path and Path(str(temp_path)).exists():
            try:
                Path(str(temp_path)).unlink()
            except Exception:
                pass
        return None