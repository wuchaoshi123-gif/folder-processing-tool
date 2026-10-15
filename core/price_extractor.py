# core/price_extractor.py
"""价格提取 — 从文件夹名/路径提取初始价格"""
import re


def extract_price(folder_name):
    """
    从文件夹名提取初始价格
    规则: 数字前缀 (如 "100-A-Bathing-..." → 100)

    返回: int 或 None
    """
    if not folder_name:
        return None
    m = re.match(r"^(\d+)", folder_name.strip())
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def extract_price_from_path(path):
    """
    从完整路径中的子文件夹提取价格
    例如: ...\AP10089image\100-A-Bathing-Ape-...\1.jpg  →  100
    """
    if not path:
        return None
    parts = path.replace("\\", "/").split("/")
    for p in reversed(parts):
        m = re.match(r"^(\d+)-", p)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None