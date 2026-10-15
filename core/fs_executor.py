# core/fs_executor.py
"""
文件系统批处理执行器（子进程专用，无 tkinter 依赖）
所有函数必须模块级，可被 ProcessPoolExecutor pickle。

★ v2:
  - stem.replace("0","") → stem.lstrip("0")  （只去前导 0）
  - rename_archive_sub 加 Windows 非法字符清洗
  - 增加 helper: _archive_dir / _safe_remove
"""
import os
import re
import shutil

# 归档目录
ARCHIVES = ("9image", "6image", "Z000image")

# 0010~0090.jpg 直接删
PREDELETE = {f"00{i}0.jpg" for i in range(1, 10)}

# Windows 文件名非法字符
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _archive_dir(target_dir, category):
    return os.path.join(target_dir, category)


def _safe_remove(path):
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return None       # skip
    except OSError:
        return False      # err


def process_folder(args):
    """
    ★ 一次遍历完成: 图片处理 + 归档移动
    返回: (sub, ok, skip, err, final_count, category)
    """
    target_dir, sub = args
    sub_path = os.path.join(target_dir, sub)

    if not os.path.isdir(sub_path):
        return sub, 0, 0, 1, 0, "Z000image"

    to_rename = []
    to_delete = []
    final_nums = set()

    # ========== 1. 扫描目录 ==========
    try:
        with os.scandir(sub_path) as it:
            for entry in it:
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue

                name = entry.name
                lower = name.lower()

                if lower.endswith(".jpeg"):
                    stem = name[:-5]
                elif lower.endswith(".jpg"):
                    stem = name[:-4]
                else:
                    continue

                # 规则: 0010~0090.jpg 直接删
                if name in PREDELETE:
                    to_delete.append(name)
                    continue

                # ★ 只去前导 0
                new_stem = stem.lstrip("0") or "0"
                new_name = new_stem + ".jpg"

                # 只保留 1-9
                try:
                    n = int(new_stem)
                except ValueError:
                    to_delete.append(name)
                    continue

                if 1 <= n <= 9:
                    if name != new_name:
                        to_rename.append((name, new_name))
                    final_nums.add(n)
                else:
                    to_delete.append(name)
    except OSError:
        return sub, 0, 0, 1, 0, "Z000image"

    # ========== 2. 执行删除 ==========
    ok = skip = err = 0
    for name in to_delete:
        r = _safe_remove(os.path.join(sub_path, name))
        if r is True:
            ok += 1
        elif r is None:
            skip += 1
        else:
            err += 1

    # ========== 3. 执行改名 ==========
    for old, new in to_rename:
        old_p = os.path.join(sub_path, old)
        new_p = os.path.join(sub_path, new)
        if os.path.exists(new_p):
            try:
                os.remove(new_p)
            except OSError:
                pass
        try:
            os.rename(old_p, new_p)
            ok += 1
        except FileNotFoundError:
            skip += 1
        except OSError:
            err += 1

    # ========== 4. 分类 ==========
    final_count = len(final_nums)
    if final_count == 9:
        category = "9image"
    elif final_count in (6, 7, 8):
        category = "6image"
    else:
        category = "Z000image"

    # ========== 5. 立即归档移动 ==========
    cat_dir = _archive_dir(target_dir, category)
    try:
        os.makedirs(cat_dir, exist_ok=True)
    except OSError:
        pass

    dst = os.path.join(cat_dir, sub)
    if not os.path.exists(dst) and os.path.exists(sub_path):
        try:
            shutil.move(sub_path, dst)
        except Exception:
            err += 1

    return sub, ok, skip, err, final_count, category


def rename_archive_sub(args):
    """C-6: 归档目录内子文件夹名 空格→-"""
    target_dir, arch, sub = args
    arch_path = os.path.join(target_dir, arch)
    src = os.path.join(arch_path, sub)

    new_sub = sub.replace(" ", "-")
    while "--" in new_sub:
        new_sub = new_sub.replace("--", "-")
    new_sub = new_sub.strip("-")
    # ★ 清洗 Windows 非法字符
    new_sub = _ILLEGAL.sub("-", new_sub)
    while "--" in new_sub:
        new_sub = new_sub.replace("--", "-")
    new_sub = new_sub.strip("-.")

    if not new_sub or new_sub == sub:
        return sub, "skip", "无需修改"

    dst = os.path.join(arch_path, new_sub)
    if os.path.exists(dst):
        return sub, "skip", "目标已存在"

    try:
        os.rename(src, dst)
        return sub, "success", ""
    except Exception as e:
        return sub, "error", str(e)[:120]