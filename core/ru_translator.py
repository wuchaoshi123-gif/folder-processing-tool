# core/ru_translator.py
"""
【E 菜单专用】产品名俄语翻译器（v2）
  · 英 → 俄
  · 预处理: 去价格前缀、去4字母后缀、连字符转空格
  · 多线程并发 + 指数退避重试 + JSON 模式

★ v2 修复:
  - Token 统计加锁（多线程不丢更新）
  - 网络请求指数退避重试
  - 使用 response_format=json_object
  - clean_text 保留 - ' & 避免破坏品牌名
"""
import re
import ast
import json
import time
import threading

import requests

try:
    from .utils import extract_name_parts
except ImportError:
    from core.utils import extract_name_parts


API_URL = "https://api.deepseek.com/v1/chat/completions"


class EnToRuTranslator:

    def __init__(self, api_key, model="deepseek-chat",
                 retry_times=3, timeout=90):
        self.api_key = api_key
        self.model = model
        self.retry_times = max(1, int(retry_times))
        self.timeout = timeout

        # 计费统计
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.request_count = 0
        self._stats_lock = threading.Lock()

        # 最近一次并发翻译的异常
        self.last_errors = []

        self.session = requests.Session()

    # ============================================================
    #               ★ 核心: 英文名预处理
    # ============================================================
    @staticmethod
    def clean_english_name(product_name):
        """
        从原始产品名中提取干净的英文名:
          "100-A-Bathing-Ape-Classic-Clog-shqk" → "A Bathing Ape Classic Clog"
        """
        if not product_name:
            return ""
        _, _, middle = extract_name_parts(product_name)
        if middle is None:
            middle = product_name
        cleaned = middle.replace("-", " ").replace("_", " ")
        return " ".join(cleaned.split())

    # ============================================================
    #                    文本清洗
    # ============================================================
    @staticmethod
    def clean_text(text):
        """保留: 西里尔 + 拉丁 + 数字 + 空格 + - ' &"""
        cleaned = re.sub(r"[^a-zA-Z0-9\u0400-\u04FF\s\-'&]", " ", text)
        return " ".join(cleaned.split())

    @staticmethod
    def extract_json_from_text(text):
        """从 API 返回中提取 JSON"""
        block_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        blocks = re.findall(block_pattern, text)
        if blocks:
            text = blocks[0].strip()
        else:
            brace_pattern = r"(\{[\s\S]*\})"
            matches = re.findall(brace_pattern, text)
            if matches:
                text = matches[0].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        try:
            return ast.literal_eval(text)
        except (SyntaxError, ValueError):
            pass
        pattern = r'["\']?(\d+)["\']?\s*:\s*["\']([^"\']*)["\']'
        matches = re.findall(pattern, text)
        if matches:
            return {k: v for k, v in matches}
        return None

    # ============================================================
    #                    网络请求
    # ============================================================
    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _post_with_retry(self, payload):
        """POST + 指数退避重试"""
        last_exc = None
        for attempt in range(self.retry_times):
            try:
                resp = self.session.post(
                    API_URL, headers=self._headers(),
                    json=payload, timeout=self.timeout)
                # 明确可重试的状态码
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(
                        f"HTTP {resp.status_code}: {resp.text[:120]}")
                resp.raise_for_status()
                return resp
            except Exception as e:
                last_exc = e
                if attempt < self.retry_times - 1:
                    time.sleep(1.5 ** attempt)
        raise last_exc

    def _add_stats(self, usage):
        """线程安全地累加统计"""
        with self._stats_lock:
            self.total_prompt_tokens += usage.get("prompt_tokens", 0)
            self.total_completion_tokens += usage.get("completion_tokens", 0)
            self.total_tokens += usage.get("total_tokens", 0)
            self.request_count += 1

    def reset_stats(self):
        with self._stats_lock:
            self.total_prompt_tokens = 0
            self.total_completion_tokens = 0
            self.total_tokens = 0
            self.request_count = 0

    # ============================================================
    #              ★ 批量翻译: 英文 → 俄语
    # ============================================================
    def _do_batch_translate(self, texts):
        """
        一次翻译多条: 英文 → 俄语
        texts: 已经清理过的英文名（无价格无后缀，空格分隔）
        """
        valid_indices = [i for i, t in enumerate(texts) if t.strip()]
        if not valid_indices:
            return [""] * len(texts)

        tasks = [f"{i}: {texts[i]}" for i in valid_indices]
        tasks_text = "\n".join(tasks)

        prompt = (
            "你是一个专业翻译助手。请将以下多个【英文】产品名称分别翻译为【俄语】。\n"
            "要求：\n"
            "1. 翻译结果必须使用俄语（西里尔字母）\n"
            "2. 品牌名、型号等专有名词可保留原文（拉丁字母）\n"
            "3. 保留原文所有信息，不要删除任何词汇，完整翻译\n"
            "4. 只保留字母、数字和空格，不要标点或特殊字符\n"
            "5. 返回一个合法的 JSON 对象，键为原始序号（数字字符串），"
            "值为翻译后的俄语字符串\n"
            "只返回 JSON，不要附加其他内容。\n\n"
            f"待翻译的文本（序号: 英文名）：\n{tasks_text}"
        )

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 4000,
            "response_format": {"type": "json_object"},
        }

        resp = self._post_with_retry(payload)
        data = resp.json()

        self._add_stats(data.get("usage", {}))

        content = data["choices"][0]["message"]["content"].strip()
        result_dict = self.extract_json_from_text(content)
        if result_dict is None:
            raise RuntimeError("无法解析返回内容中的 JSON")

        results = [""] * len(texts)
        for key, value in result_dict.items():
            try:
                idx = int(key)
                if 0 <= idx < len(results):
                    results[idx] = self.clean_text(str(value))
            except (ValueError, TypeError):
                continue

        # 兜底: 空结果保留原文
        for idx in valid_indices:
            if not results[idx]:
                results[idx] = self.clean_text(texts[idx])

        return results

    def _do_batch_translate_parallel(self, texts,
                                     max_workers=4, batch_size=20):
        """多线程分批翻译"""
        self.last_errors = []
        if not texts:
            return []

        from concurrent.futures import ThreadPoolExecutor, as_completed

        indexed = list(enumerate(texts))
        batches = [indexed[i:i + batch_size]
                   for i in range(0, len(indexed), batch_size)]
        results = [""] * len(texts)

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {}
            for batch in batches:
                sub_texts = [t for _, t in batch]
                fut = ex.submit(self._do_batch_translate, sub_texts)
                futures[fut] = batch

            for fut in as_completed(futures):
                batch = futures[fut]
                try:
                    sub_results = fut.result()
                except Exception as e:
                    err = f"batch[{batch[0][0]}~{batch[-1][0]}]: {str(e)[:120]}"
                    with self._stats_lock:
                        self.last_errors.append(err)
                    print(f"[RU] {err}")
                    sub_results = [""] * len(batch)
                for j, (orig_idx, _) in enumerate(batch):
                    if j < len(sub_results):
                        results[orig_idx] = sub_results[j]
        return results

    # ============================================================
    #          ★ E 菜单主接口: 批量翻译原始产品名
    # ============================================================
    def translate_products(self, product_names, progress_cb=None,
                           max_workers=4):
        """
        返回: [{
            "original": 原始名,
            "englishname": 清洗后的英文名,
            "rufanyi": 俄语翻译,
            "error": None 或 错误信息,
        }, ...]
        """
        if not product_names:
            return []

        cleaned_list = [self.clean_english_name(p) for p in product_names]

        if progress_cb:
            progress_cb(f"翻译 {len(product_names)} 条 (英→俄, "
                        f"{max_workers} 线程)...")

        results = self._do_batch_translate_parallel(
            cleaned_list, max_workers=max_workers, batch_size=20)

        output = []
        for i, orig in enumerate(product_names):
            english = cleaned_list[i] if i < len(cleaned_list) else ""
            russian = results[i] if i < len(results) else ""
            error = None if russian else "翻译失败"
            output.append({
                "original": orig,
                "englishname": english,
                "rufanyi": russian,
                "error": error,
            })
        return output

    # 兼容旧接口
    def translate_texts(self, texts, progress_cb=None, max_workers=4):
        if not texts:
            return []
        if progress_cb:
            progress_cb(f"翻译 {len(texts)} 条 (英→俄, {max_workers} 线程)...")
        results = self._do_batch_translate_parallel(
            texts, max_workers=max_workers, batch_size=20)
        output = []
        for i, text in enumerate(texts):
            trans = results[i] if i < len(results) else ""
            output.append((text, trans, None if trans else "翻译失败"))
        return output

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass