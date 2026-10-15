# core/concurrent.py
"""多线程并发执行工具"""
from concurrent.futures import ThreadPoolExecutor, as_completed


def run_concurrent(indexed_tasks, executor_fn,
                   max_workers=8, progress_cb=None):
    """
    并发执行任务列表
    indexed_tasks: [(idx, task), ...]
    executor_fn:   callable(task) -> (status, message)
    progress_cb:   callable(done, total)
    返回:          [(idx, task, status, message), ...]  按 idx 排序
    """
    if not indexed_tasks:
        return []

    results = []
    total = len(indexed_tasks)
    done = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(executor_fn, t): (i, t) for i, t in indexed_tasks}
        for fut in as_completed(futures):
            i, t = futures[fut]
            try:
                status, msg = fut.result()
            except Exception as e:
                status, msg = "error", str(e)
            results.append((i, t, status, msg))
            done += 1
            if progress_cb:
                try:
                    progress_cb(done, total)
                except Exception:
                    pass

    results.sort(key=lambda x: x[0])
    return results