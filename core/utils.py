# core/utils.py
"""通用工具函数（性能优化版：全部使用 os.scandir）"""
import os
import re
import shutil
from pathlib import Path

ARCHIVE_DIRS = {"9image", "6image", "Z000image", "_logs"}


def list_target_folders(target_dir, verbose=False):
    """
    列出目标目录下的子文件夹（排除归档目录）
    ★ 使用 os.scandir 加速，数万文件夹场景下比 os.listdir + is_dir 快 10~50 倍
    """
    target_dir = Path(target_dir)
    if not target_dir.exists():
        return []

    result, skipped = [], []
    try:
        with os.scandir(target_dir) as it:
            for entry in it:
                try:
                    # DirEntry.is_dir() 通常从缓存读取，避免额外 stat
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue

                name = entry.name
                if name in ARCHIVE_DIRS:
                    skipped.append((name, "归档/日志目录"))
                    continue
                result.append(name)
    except OSError as e:
        if verbose:
            print(f"⚠️ 扫描目录失败: {e}")
        return []

    if verbose:
        print(f"🔍 扫描目录: {target_dir}")
        print(f"   可用子文件夹 {len(result)} 个，跳过 {len(skipped)} 个")
        for name, why in skipped:
            print(f"     跳过: {name}  ({why})")
    return result


def scan_files(sub_path, extensions=None):
    """
    高效扫描子文件夹内的文件
    extensions: 例如 ('.jpg', '.jpeg')，None 表示全部文件
    返回: [文件名, ...]
    """
    sub_path = Path(sub_path)
    if not sub_path.exists():
        return []

    result = []
    try:
        with os.scandir(sub_path) as it:
            for entry in it:
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                name = entry.name
                if extensions is None:
                    result.append(name)
                elif name.lower().endswith(extensions):
                    result.append(name)
    except OSError:
        return []
    return result


def clean_folder_name(name):
    """A-4 数据清洗：只保留中文/英文/数字/空格"""
    cleaned = re.sub(r"[^\u4e00-\u9fffa-zA-Z0-9 ]", "", name)
    return re.sub(r" +", " ", cleaned).strip()


def strip_underscore_prefix(name):
    """A-3 去掉第一个 _ 及其之前的内容"""
    if "_" not in name:
        return None
    return name.split("_", 1)[1].strip()


def replace_space_with_dash(name):
    """C-6 空格转横线，多横线合一，去首尾横线"""
    new = name.replace(" ", "-")
    new = re.sub(r"-+", "-", new)
    return new.strip("-")


# ---------- 文件操作（返回 (status, msg)） ----------
def move_folder(src, dst):
    src, dst = Path(src), Path(dst)
    if not src.exists():
        return "error", "源不存在"
    if dst.exists():
        return "skip", "目标已存在"
    try:
        shutil.move(str(src), str(dst))
        return "success", ""
    except Exception as e:
        return "error", str(e)


def rename_item(src, dst):
    src, dst = Path(src), Path(dst)
    if not src.exists():
        return "error", "源不存在"
    if dst.exists():
        return "skip", "目标已存在"
    try:
        os.rename(str(src), str(dst))
        return "success", ""
    except Exception as e:
        return "error", str(e)


def delete_file(fp):
    fp = Path(fp)
    if not fp.exists():
        return "error", "文件不存在"
    try:
        os.remove(str(fp))
        return "success", ""
    except Exception as e:
        return "error", str(e)

def extract_name_parts(name):
    """
    提取文件夹名三个部分: (数字前缀, 4字母后缀, 中间部分)
    例: "100-Adidas-2026-TERREX-abcD" → ("100", "abcD", "Adidas-2026-TERREX")
    返回: (number, suffix, middle)，若无数字前缀返回 (None, None, None)
    """
    import re
    if not name:
        return None, None, None
    num_match = re.match(r'^(\d+)\s*(.*)', name)
    if not num_match:
        return None, None, None
    number = num_match.group(1)
    rest = num_match.group(2).strip()
    letter_match = re.search(r'([a-zA-Z]{4})$', rest)
    if letter_match:
        suffix = letter_match.group(1)
        middle = rest[:letter_match.start()].strip()
    else:
        suffix = ""
        middle = rest
    return number, suffix, middle