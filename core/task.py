# core/task.py
"""Task 数据模型"""


class Task:
    STATUS_TEXT = {
        "pending": "待执行",
        "success": "✔ 成功",
        "skip":    "⏭ 跳过",
        "error":   "✖ 失败",
    }

    def __init__(self, task_type, old, new="", extra=None):
        self.type = task_type
        self.old = old
        self.new = new
        self.extra = extra or {}
        self.checked = True
        self.status = "pending"
        self.message = ""

    def display_new(self):
        if self.type == "A-1":
            return f"000000集合/{self.new}"
        if self.type == "C-5":
            return f"{self.extra.get('category','')}/{self.old}"
        if self.type in ("C-2", "C-4"):
            return "(删除)"
        return self.new

    def status_text(self):
        txt = self.STATUS_TEXT.get(self.status, self.status)
        if self.message:
            txt += f"  ({self.message})"
        return txt