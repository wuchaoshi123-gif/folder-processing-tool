# core/data_exporter.py
"""生成 xxx-本地图片url.txt"""
from pathlib import Path


def export_local_url_txt(output_path, folder_name, local_paths):
    """
    生成 "目录名-本地图片url.txt"
    每行一个本地路径
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for p in local_paths:
            f.write(str(p) + "\n")
    return output_path


def make_output_filename(base_dir_name):
    """生成文件名: AP10089image-本地图片url.txt"""
    return f"{base_dir_name}-本地图片url.txt"