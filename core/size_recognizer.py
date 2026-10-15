# core/size_recognizer.py
"""
从 1.jpg 识别尺码信息

支持格式:
  36-45  36~45  36～45  36到45  36至45    (范围)
  36,37,38,39                             (逗号)
  36 37 38 39 40 41                       (空格)
  36、37、38                              (顿号)
  36.5 37.5 38.5                          (小数)
  36-45, 48-50                            (多段)

★ 丢弃规则:
  解析出的尺码列表若以小数开头（半码开头）, 该记录丢弃, 不入库
"""
import re
from pathlib import Path


class SizeRecognizer:
    def __init__(self):
        self.engine = None
        self._init_engine()

    def _init_engine(self):
        try:
            import easyocr
            self.engine = ("easyocr",
                           easyocr.Reader(["ch_sim", "en"], gpu=False))
            return
        except Exception:
            pass
        try:
            import pytesseract
            from PIL import Image  # noqa
            self.engine = ("tesseract", pytesseract)
            return
        except Exception:
            self.engine = None

    def is_available(self):
        return self.engine is not None

    # ==========================================================
    #                     OCR 读取
    # ==========================================================
    def read_text(self, image_path):
        if not self.engine:
            return ""
        try:
            if self.engine[0] == "easyocr":
                reader = self.engine[1]
                results = reader.readtext(str(image_path),
                                          detail=0, paragraph=True)
                return " ".join(results)
            elif self.engine[0] == "tesseract":
                from PIL import Image
                tess = self.engine[1]
                img = Image.open(image_path)
                return tess.image_to_string(img, lang="chi_sim+eng")
        except Exception:
            return ""
        return ""

    # ==========================================================
    #                  尺码解析（核心）
    # ==========================================================
    @staticmethod
    def parse_sizes(text, banma=None):
        """
        从 OCR 文本里提取尺码列表。

        返回: (sizes_list | None, has_ban, reason)
          - sizes_list: 列表或 None
          - has_ban:    文本是否包含"半"
          - reason:     成功时为 "", 失败时为原因字符串
        """
        if not text:
            return None, False, "无文本"

        # 判断是否包含"半"标记
        has_ban = ("半" in text) or ("含半" in text) or ("有半" in text)

        # 规范化文本
        t = text.replace("，", ",").replace("、", ",")
        t = t.replace("～", "~").replace("－", "-").replace("—", "-")
        t = t.replace("到", "-").replace("至", "-")

        sizes = []

        # ---------- 1. 找所有 X-Y 范围 ----------
        range_pattern = re.compile(r"(\d{2}(?:\.\d)?)\s*-\s*(\d{2}(?:\.\d)?)")
        consumed_spans = []
        for m in range_pattern.finditer(t):
            lo_s, hi_s = m.group(1), m.group(2)
            try:
                lo, hi = float(lo_s), float(hi_s)
            except ValueError:
                continue
            if lo > hi or lo < 20 or hi > 60:
                continue

            # 步长由端点是否有小数决定
            step = 0.5 if ("." in lo_s or "." in hi_s) else 1.0

            cur = lo
            while cur <= hi + 1e-9:
                if cur.is_integer():
                    sizes.append(str(int(cur)))
                else:
                    sizes.append(f"{cur:.1f}".rstrip("0").rstrip("."))
                cur = round(cur + step, 1)
            consumed_spans.append(m.span())

        # ---------- 2. 移除已处理的"范围"文本 ----------
        rest = t
        for start, end in reversed(consumed_spans):
            rest = rest[:start] + " " + rest[end:]

        # ---------- 3. 从剩余文本找孤立数字 ----------
        num_pattern = re.compile(r"(?<!\d)(\d{2}(?:\.\d)?)(?!\d)")
        for m in num_pattern.finditer(rest):
            val = float(m.group(1))
            if 20 <= val <= 60:
                if val.is_integer():
                    sizes.append(str(int(val)))
                else:
                    sizes.append(f"{val:.1f}".rstrip("0").rstrip("."))

        if not sizes:
            return None, has_ban, "未识别到尺码"

        # ---------- 4. 去重 + 排序 ----------
        def _key(x):
            try:
                return float(x)
            except ValueError:
                return 0

        sizes = sorted(set(sizes), key=_key)

        # ---------- 5. ★ 半码开头 → 丢弃 ----------
        if "." in sizes[0]:
            return None, has_ban, f"半码开头 [{sizes[0]}] 已丢弃"

        # ---------- 6. 有"半"字 AND banma 非空 → 插半码 ----------
        if has_ban and banma:
            sizes = SizeRecognizer._insert_banma(sizes, banma)

        return sizes, has_ban, ""

    @staticmethod
    def _insert_banma(sizes, banma):
        """按 banma 表在半码位置插入对应值"""
        banma_set = set(banma)
        result = []
        for s in sizes:
            result.append(s)
            try:
                f = float(s)
            except ValueError:
                continue
            if f.is_integer():
                half = f"{int(f)}.5"
                if half in banma_set:
                    result.append(half)
        # 去重保序
        seen = set()
        final = []
        for x in result:
            if x not in seen:
                seen.add(x)
                final.append(x)
        return final

    # ==========================================================
    #                   对外主接口
    # ==========================================================
    def recognize(self, image_path, banma=None):
        """
        识别尺码。
        返回: (sizes_list | None, has_ban, raw_text, reason)
          - sizes_list: 成功时为列表, 失败时为 None
          - has_ban:    是否出现"半"
          - raw_text:   OCR 原始文本
          - reason:     成功为空, 失败为原因
        """
        text = self.read_text(image_path)
        if not text:
            return None, False, "", "OCR 未识别到文字"

        sizes, has_ban, reason = self.parse_sizes(text, banma)
        return sizes, has_ban, text, reason