# core/e_pipeline_mp.py
"""
OCR 多进程执行器
  · 每个子进程独立 pyturboocr 实例（独立 GPU session）
  · 分块提交，减少 IPC 开销
  · 支持 Windows spawn 模式
"""
import os
import threading



# ============================================================
#  子进程全局状态
# ============================================================
_MP_ENGINE = None
_MP_BACKEND = None
_MP_INIT_LOCK = threading.Lock()


def init_ocr_worker():
    """子进程初始化 OCR（含 TensorRT 缓存配置）"""
    global _MP_ENGINE, _MP_BACKEND

    with _MP_INIT_LOCK:
        if _MP_ENGINE is not None:
            return True

        try:
            from pyturboocr import OCR
            import os

            # ★ 1. 缓存目录
            cache_dir = r"C:\Users\Newkuangren\.cache\tensorrt_engine_cache"
            os.makedirs(cache_dir, exist_ok=True)

            # ★ 2. TensorRT 选项
            trt_options = {
                'device_id': 0,
                'trt_fp16_enable': False,  # ★ 关闭 FP16，用 FP32
                'trt_engine_cache_enable': True,
                'trt_engine_cache_path': cache_dir,
                'trt_timing_cache_enable': True,
                'trt_timing_cache_path': cache_dir,
                'trt_force_sequential_engine_build': True,
            }                                    # ← ★ 别漏这个闭合括号

            # ★ 3. providers 元组形式
            providers = [
                ('TensorrtExecutionProvider', trt_options),
                'CUDAExecutionProvider',
                'CPUExecutionProvider',
            ]

            # ★ 4. 创建引擎
            _MP_ENGINE = OCR(tier="small", providers=providers)
            _MP_BACKEND = "pyturboocr"
            print(f"[MP-OCR] 子进程初始化成功 (PID={os.getpid()})")
            return True
        except Exception as e:
            print(f"[MP-OCR] 子进程初始化失败: {e}")
            _MP_BACKEND = "none"
            _MP_ENGINE = None
            return False

def ocr_batch_chunk(items):
    """
    子进程批量处理一批产品

    参数:
      items: [(idx, onlymulu, img_path, banma), ...]

    返回:
      [(idx, sizes, has_ban, text, reason), ...]

    说明:
      · 复用 core.e_pipeline 的 _read_text / parse_sizes
      · 但 _read_text 会调用全局 _OCR_ENGINE，
        所以子进程里需要覆盖它
    """
    global _MP_ENGINE

    # 确保引擎已加载
    if _MP_ENGINE is None:
        init_ocr_worker()

    # ★ 关键: 把子进程的引擎注册到 e_pipeline 模块的全局变量
    import core.e_pipeline as ep
    if _MP_ENGINE is not None:
        ep._OCR_ENGINE = _MP_ENGINE
        ep._OCR_BACKEND = "pyturboocr"

    results = []
    for idx, onlymulu, img_path, banma in items:
        try:
            text, err = ep._read_text(img_path)
            if err:
                results.append((idx, None, False, "", err))
                continue
            if not text or not text.strip():
                results.append((idx, None, False, "", "OCR 未识别到文字"))
                continue
            sizes, has_ban, reason = ep.parse_sizes(text, banma)
            results.append((idx, sizes, has_ban, text, reason))
        except Exception as e:
            results.append((idx, None, False, "",
                            f"异常: {str(e)[:80]}"))
    return results

def ocr_retry_chunk(items):
    """批量重试（中下拼接）"""
    global _MP_ENGINE

    if _MP_ENGINE is None:
        init_ocr_worker()

    import core.e_pipeline as ep
    if _MP_ENGINE is not None:
        ep._OCR_ENGINE = _MP_ENGINE
        ep._OCR_BACKEND = "pyturboocr"

    results = []
    for idx, onlymulu, img_path, banma, text_full in items:
        try:
            # 中下拼接 OCR
            text_retry, err = ep._read_text_retry(img_path)

            combined = text_full or ""
            if text_retry and text_retry.strip():
                combined = (combined + "\n" + text_retry).strip()

            if not combined:
                results.append((idx, None, False, "",
                                f"重试无文本: {err}"))
                continue

            sizes, has_ban, reason = ep.parse_sizes(combined, banma)
            results.append((idx, sizes, has_ban, combined, reason))
        except Exception as e:
            results.append((idx, None, False, "",
                            f"重试异常: {str(e)[:80]}"))
    return results