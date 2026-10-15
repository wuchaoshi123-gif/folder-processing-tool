# core/logger.py
"""操作日志 & Markdown 报告生成"""
import json
from datetime import datetime
from pathlib import Path


class OperationLogger:
    def __init__(self, target_dir):
        self.target_dir = Path(target_dir)
        self.log_dir = self.target_dir / "_logs"
        self.log_dir.mkdir(exist_ok=True)
        self.entries = []
        self.start_time = datetime.now()

    def log(self, task):
        self.entries.append({
            "module": task.type.split("-")[0],
            "step": task.type,
            "old_name": task.old,
            "new_name": task.new,
            "status": task.status,
            "message": task.message,
            "timestamp": datetime.now().isoformat(),
        })

    def save(self, module_name):
        if not self.entries:
            return None, None
        ts = self.start_time.strftime("%Y%m%d_%H%M%S")
        json_path = self.log_dir / f"{ts}_{module_name}_operations.json"
        md_path = self.log_dir / f"{ts}_{module_name}_report.md"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({
                "module": module_name,
                "target_dir": str(self.target_dir),
                "start_time": self.start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "entries": self.entries,
            }, f, ensure_ascii=False, indent=2)

        self._write_markdown(md_path, module_name)
        return json_path, md_path

    def _write_markdown(self, path, module_name):
        stats = {}
        for e in self.entries:
            key = e["step"]
            if key not in stats:
                stats[key] = {"success": 0, "skip": 0, "error": 0}
            stats[key][e["status"]] = stats[key].get(e["status"], 0) + 1

        lines = [
            "# 文件夹批量化处理报告\n",
            f"**处理时间**: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}"
            f" ~ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**目标目录**: `{self.target_dir}`",
            f"**执行模块**: {module_name}\n",
            "## 统计摘要\n",
            "| 步骤 | 成功 | 跳过 | 失败 |",
            "|------|------|------|------|",
        ]
        for k, v in stats.items():
            lines.append(f"| {k} | {v['success']} | {v['skip']} | {v['error']} |")
        lines.append("\n## 详细记录\n")
        current = None
        for e in self.entries:
            if e["step"] != current:
                current = e["step"]
                lines.append(f"\n### {e['step']}\n")
            icon = {"success": "✅", "skip": "⏭️",
                    "error": "❌", "info": "ℹ️"}.get(e["status"], "•")
            msg = f"  ({e['message']})" if e["message"] else ""
            if e["new_name"]:
                lines.append(f"- {icon} `{e['old_name']}` → `{e['new_name']}`{msg}")
            else:
                lines.append(f"- {icon} `{e['old_name']}`{msg}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))