# core/brand_manager.py
"""品牌识别与归类（v2）
文档格式:
  allbands.txt         每行一个关键词
  allbandsduiying.txt  关键词=映射值          (等号两侧可有空格)
  bandsizechart.txt    关键词 = URL
  banma.txt            品牌名 尺码1,尺码2,...

★ v2 修复:
  - mapping.keys() 也参与关键词匹配（samba / adios 等别名不再漏识别）
  - 关键词按长度降序，避免 ad 抢 adidas
  - 子串匹配改为词边界正则，避免 ad 误伤 adxxx
"""
import re
from pathlib import Path


class BrandManager:

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.allbands = self._load_allbands()
        self.mapping = self._load_mapping("allbandsduiying.txt")
        self.sizechart = self._load_mapping("bandsizechart.txt")
        self.banma = self._load_banma()

        # ★ 合并 allbands + 映射表 key，去重后按长度降序
        merged = list(dict.fromkeys(
            self.allbands + list(self.mapping.keys())
        ))
        self.match_keywords = sorted(merged, key=len, reverse=True)
        # 预编译词边界正则
        self._kw_re = {
            kw: re.compile(r"\b" + re.escape(kw) + r"\b")
            for kw in self.match_keywords
        }

    # ==========================================================
    #                    文件解析
    # ==========================================================
    def _load_allbands(self):
        p = self.data_dir / "allbands.txt"
        if not p.exists():
            return []
        result = []
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip().lower()
                if not line or line.startswith("#"):
                    continue
                result.append(line)
        return result

    def _load_mapping(self, filename):
        """通用 key=value 解析，等号两侧可有空格"""
        p = self.data_dir / filename
        if not p.exists():
            return {}
        result = {}
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                result[k.strip().lower()] = v.strip()
        return result

    def _load_banma(self):
        """
        解析 banma.txt:
          new balance 36,37,37.5,...
          vans 36,36.5,37,...
        """
        p = self.data_dir / "banma.txt"
        if not p.exists():
            return {}
        result = {}
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"^(.+?)\s+(\d[\d.,\s]*)$", line)
                if not m:
                    continue
                brand = m.group(1).strip().lower()
                sizes_raw = m.group(2).strip()
                sizes = [s.strip() for s in sizes_raw.split(",") if s.strip()]
                result[brand] = sizes
        return result

    # ==========================================================
    #                    品牌识别
    # ==========================================================
    @staticmethod
    def _normalize_brand(brand):
        if not brand:
            return ""
        return brand.strip().lower()

    def _match_keyword(self, parts, part_set):
        """按长词优先顺序找第一个匹配的关键词"""
        for keyword in self.match_keywords:
            # (a) 精确匹配某个 part
            if keyword in part_set:
                return keyword
            # (b) 词边界子串匹配
            pat = self._kw_re.get(keyword)
            if pat is None:
                continue
            for p in parts:
                if pat.search(p):
                    return keyword
        return None

    def identify(self, folder_name):
        """
        返回 (品牌名, sizechart_url, 匹配关键词)
        """
        lower = folder_name.lower()
        parts = [p for p in re.split(r"[-_]+", lower) if p.strip()]
        part_set = set(parts)

        matched_keyword = self._match_keyword(parts, part_set)

        # ---------- 未匹配到 ----------
        if matched_keyword is None:
            chart = self.sizechart.get("allall", "")
            return "allall", chart, ""

        # ---------- 通过映射表转换 ----------
        brand = self.mapping.get(matched_keyword, matched_keyword)

        # ---------- 查尺码表 ----------
        chart = (
            self.sizechart.get(brand.lower(), "")
            or self.sizechart.get(matched_keyword, "")
            or self.sizechart.get("allall", "")
        )

        return brand, chart, matched_keyword

    # ==========================================================
    def get_banma(self, brand):
        """获取品牌半码列表"""
        if not brand:
            return []
        return self.banma.get(brand.lower(), [])

    def debug_info(self):
        return {
            "allbands": len(self.allbands),
            "mapping": len(self.mapping),
            "sizechart": len(self.sizechart),
            "banma": len(self.banma),
            "match_keywords": len(self.match_keywords),
        }