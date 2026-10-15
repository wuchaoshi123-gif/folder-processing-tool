# translator.py
"""
【B 菜单专用】文件夹名称批量翻译器
★ v7: 修复 描述.txt 提取的 6 个 bug
"""
import re
import ast
import json
import time
import requests
from pathlib import Path


def _fmt_duration(sec):
    if sec is None or sec < 0:
        return "计算中"
    sec = int(sec)
    if sec < 60:
        return f"{sec}秒"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m}分{s}秒"
    h, m = divmod(m, 60)
    return f"{h}时{m}分"


class DeepSeekBatchTranslator:
    """【B 菜单】文件夹名中译英翻译器"""

    DEFAULT_BATCH_SIZE = 40
    DEFAULT_TIMEOUT = 120
    MAX_SPLIT_DEPTH = 3
    MIN_SPLIT_SIZE = 5

    QUALITY_TERMS = (
        "原楦原纸版开发", "真标原盒", "原厂特供",
        "公司级", "E版头层", "原楦原纸版", "原楦原纸",
        "原纸版", "原楦", "原纸", "纯原", "顶级", "原厂",
        "独家", "特供", "厂货", "原单", "外贸", "超A",
        "精仿", "高仿", "真标", "原盒", "A货",
    )

    PROMO_TERMS = (
        "福利", "特价", "秒杀", "包邮", "开学季", "限时",
        "清仓", "优惠", "大促",
    )

    META_PREFIXES = (
        "类型", "款式", "适合", "风格", "用途", "属性",
        "参数", "规格", "季节", "材质", "颜色",
    )

    CALL_TO_ACTION = (
        "立即抢购", "马上抢", "加微信", "加V", "咨询", "扫码",
        "点击", "联系客服", "速来抢购", "询价",
    )

    # ★ 补充 ‼ ⁉ ❓ ❕ 等
    _EMOJI_RE = re.compile(
        "["
        "\U0001F000-\U0001FAFF"
        "\U00002600-\U000027BF"
        "\U0001F1E0-\U0001F1FF"
        "\u2705\u274C\u2764\u2B50\u2728"
        "\U0001F4B0\U0001F4B5\U0001F4B4\U0001F4B6\U0001F4B7"
        "\u203C\u2049\u2753\u2755\u2757\u2763\u2764"
        "\uFE0F"
        "]+",
        flags=re.UNICODE,
    )

    def __init__(self, api_key, model="deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
        self.request_count = 0
        self.session = requests.Session()

    # ============================================================
    @staticmethod
    def extract_parts(name):
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

    @staticmethod
    def clean_text(text):
        cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
        return ' '.join(cleaned.split())

    @staticmethod
    def extract_json_from_text(text):
        block_pattern = r'```(?:json)?\s*([\s\S]*?)\s*```'
        blocks = re.findall(block_pattern, text)
        if blocks:
            text = blocks[0].strip()
        else:
            brace_pattern = r'(\{[\s\S]*\})'
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
    #  ★ 描述.txt 提取（v7 修复版）
    # ============================================================
    @classmethod
    def extract_desc_content(cls, desc_text):
        if not desc_text:
            return None

        desc_text = re.sub(r'[\u200b-\u200d\ufeff]', '', desc_text)

        kept_lines = []
        huohao_values = []

        meta_pat = r'^(?:' + '|'.join(cls.META_PREFIXES) + r')\s*[:：]'

        for raw_line in desc_text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            # ★ Bug 1 修复: 去 emoji 前先删价格标记（含 💰 和 💰 后面的数字）
            line = re.sub(r'💰\s*\d+(?:\.\d+)?', ' ', line)
            line = re.sub(r'\d+(?:\.\d+)?\s*💰', ' ', line)

            # 1. 清理 emoji 和杂符号
            line = cls._EMOJI_RE.sub(" ", line).strip()
            line = re.sub(r'^[【\[][^】\]]*[】\]]\s*', '', line).strip()
            line = re.sub(
                r'^[\s✅☑✔✖❌●◆■□▪▫★☆♪♫→←↑↓🔺👉👊🏻🔥💯❗‼⁉]+',
                '', line).strip()
            if not line:
                continue

            # 2. 抓货号值（白名单）
            for m in re.finditer(r'(?:货号|型号)\s*[:：]?\s*(\S+)', line):
                val = m.group(1).strip('，,。.；;、:：')
                if val:
                    huohao_values.append(val)

            # 3. 整行跳过判定

            # 3.1 纯价格数字（如 "95" "100" "95得" "100💰"）
            temp = line.strip()
            temp = re.sub(r'[\d.,\s]+', '', temp)
            temp = re.sub(r'(?:得|块|元)', '', temp)
            if not temp:
                continue

            # 3.2 纯尺码行
            temp2 = re.sub(
                r'(?:尺码|码数|尺寸|SIZE|size|号码|号数|码号)\s*[:：]?\s*',
                '', line)
            temp2 = re.sub(
                r'[\d.,\s~～⅓⅔½\u2044xX×\-–—/、+（）()【】\[\]]+', '',
                temp2)
            temp2 = re.sub(
                r'(?:含半码|半码|如图|码|半|B|b|至|到|SIZE|size)',
                '', temp2)
            # ★ Bug 5 修复: 剩余无中文且无英文词 → 跳过
            if not re.search(r'[\u4e00-\u9fff]', temp2) and \
                    not re.search(r'[a-zA-Z]{2,}', temp2):
                continue

            # 3.3 纯 ID/编码 行
            temp3 = re.sub(
                r'\b(?:ID|id|lD|编码|编号|SKU|sku)\s*[:：]\s*\S+',
                '', line).strip()
            if not temp3:
                continue

            # 3.4 促销短行
            if len(line) < 30 and any(p in line for p in cls.PROMO_TERMS):
                continue

            # 3.5 营销号召
            temp5 = line
            for c in cls.CALL_TO_ACTION:
                temp5 = temp5.replace(c, '')
            temp5 = re.sub(r'[👉👊🏻→\s‼⁉❗]+', '', temp5)
            if not temp5.strip():
                continue

            # 3.6 元数据行
            if re.match(meta_pat, line):
                continue

            # 4. 行内删除

            # 4.1 货号段（删值，前面已白名单保留）
            line = re.sub(
                r'(?:货号|型号)\s*[:：]?\s*\S+\s*', ' ', line)

            # 4.2 尺码段（到行尾）
            line = re.sub(
                r'(?:尺码|码数|尺寸|SIZE|size|号码|号数|码号)'
                r'\s*[:：]?\s*[\d.,\s~～⅓⅔½\u2044xX×\-–—/、+（）()]+.*$',
                ' ', line)

            # ★ Bug 2 修复: ID 段加词边界 \b（避免 Adidas 里的 id 被吃）
            line = re.sub(
                r'\b(?:ID|id|lD|编码|编号|SKU|sku)\s*[:：]\s*\S+.*$',
                ' ', line)

            # 4.4 价格标记（备用）
            line = re.sub(r'💰\s*\d+(?:\.\d+)?', ' ', line)
            line = re.sub(r'\d+(?:\.\d+)?\s*💰', ' ', line)

            # 4.5 品质词
            for q in cls.QUALITY_TERMS:
                line = line.replace(q, ' ')

            # 4.6 行尾"带半码/含半码"
            line = re.sub(r'\s*带?含?半码\s*$', ' ', line)

            # 4.7 行尾"数字-数字"（如"白色36-45"）
            line = re.sub(
                r'\s*\d+(?:\.\d+)?[-–—~～]\d+(?:\.\d+)?\s*$',
                ' ', line)

            # ★ Bug 4 修复: 去尾部符号，保留句号
            line = line.strip('，,；;:：!！?？、-～~')
            line = " ".join(line.split())

            if not line:
                continue

            # 5. 单行 > 200
            if len(line) > 200:
                line = line[:200].rstrip()

            kept_lines.append(line)

        result = " ".join(kept_lines).strip()

        # 6. 追加货号
        if huohao_values:
            seen = set()
            uniq = []
            for v in huohao_values:
                if v not in seen:
                    seen.add(v)
                    uniq.append(v)
            result = (result + " " + " ".join(uniq)).strip()

        return result if result else None

    @staticmethod
    def read_desc_from_folder(folder_path):
        if not folder_path:
            return None
        desc_path = Path(folder_path) / "描述.txt"
        if not desc_path.exists():
            return None
        try:
            text = desc_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            try:
                text = desc_path.read_text(encoding="gbk", errors="ignore")
            except Exception:
                return None
        return text

    # ============================================================
    def _scan_descs_parallel(self, folder_names, target_dir,
                              max_workers=8, progress_cb=None):
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}
        total = len(folder_names)
        done = 0
        start_ts = time.time()
        last_report = [0.0]

        def _read_one(name):
            try:
                folder_path = Path(target_dir) / name
                raw = self.read_desc_from_folder(folder_path)
                if not raw:
                    return name, None
                desc = self.extract_desc_content(raw)
                return name, desc
            except Exception:
                return name, None

        def _report(force=False):
            now = time.time()
            if not force and (now - last_report[0]) < 0.3:
                return
            last_report[0] = now
            elapsed = now - start_ts
            speed = done / elapsed if elapsed > 0 else 0
            remain = (total - done) / speed if speed > 0 else 0
            pct = done / total * 100 if total else 0
            if progress_cb:
                try:
                    progress_cb(
                        f"扫描 描述.txt {done}/{total} ({pct:.0f}%)  |  "
                        f"{speed:.0f} 条/秒  |  剩余 {_fmt_duration(remain)}"
                    )
                except Exception:
                    pass

        _report(force=True)

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_read_one, name): name
                       for name in folder_names}
            for fut in as_completed(futures):
                name, desc = fut.result()
                if desc:
                    results[name] = desc
                done += 1
                _report()

        _report(force=True)
        return results

    # ============================================================
    @staticmethod
    def build_final_name(number, translated, suffix, max_total_len):
        prefix_len = len(number) + 1
        suffix_len = len(suffix) + 1 if suffix else 0
        max_middle_len = max_total_len - prefix_len - suffix_len
        if max_middle_len < 5:
            max_middle_len = 5

        if len(translated) > max_middle_len:
            translated = translated[:max_middle_len].rstrip()

        translated = re.sub(r'\s+', '-', translated)

        if suffix:
            new_name = f"{number}-{translated}-{suffix}"
        else:
            new_name = f"{number}-{translated}"

        if len(new_name) > max_total_len:
            overflow = len(new_name) - max_total_len
            if overflow < len(translated):
                trans_part = translated[:-overflow].rstrip('-')
            else:
                trans_part = ""
            if suffix:
                new_name = f"{number}-{trans_part}-{suffix}".strip('-')
            else:
                new_name = f"{number}-{trans_part}".strip('-')

        new_name = re.sub(r'[\\/*?:"<>|]', '-', new_name)
        new_name = re.sub(r'-+', '-', new_name)
        new_name = new_name.strip('-')
        return new_name

    # ============================================================
    def _do_batch_translate(self, texts, max_len_per_item=None,
                            unlimited=True):
        valid_indices = [i for i, txt in enumerate(texts) if txt.strip()]
        if not valid_indices:
            return [""] * len(texts)

        tasks = [f"{idx}: {texts[idx]}" for idx in valid_indices]
        tasks_text = "\n".join(tasks)

        if unlimited:
            prompt = (
                "你是一个专业翻译助手。请将以下多个【中文】文本分别翻译为【英文】，"
                "保留原文所有信息，不要删除任何词汇。长度不限，请完整翻译。"
                "每个翻译结果应只包含英文字母、数字和空格，"
                "不要包含标点符号或特殊字符。"
            )
        else:
            prompt = (
                "你是一个专业的海外电商标题优化专家。请将以下英文电商标题"
                "进行精简优化，"
                f"每个标题压缩到 {max_len_per_item} 个字符以内。"
                "删除无意义的营销词汇（如舒适、轻便、透气、复古、经典等），"
                "保留品牌、系列、材质、核心功能、颜色、儿童、童鞋、女性、"
                "男性、男女等关键信息。"
                "只包含英文字母、数字和空格，不要包含标点符号或特殊字符。"
            )

        prompt += (
            "请返回一个合法的 JSON 对象，键为原始序号（数字），"
            "值为处理后的英文字符串。"
            "只返回 JSON，不要附加其他内容。\n\n"
            f"待处理的文本（序号: 文本）：\n{tasks_text}"
        )

        est = len(texts) * 100
        max_tokens = min(8000, max(2000, est))

        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }

        resp = self.session.post(url, headers=headers, json=payload,
                                 timeout=self.DEFAULT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {})
        self.total_prompt_tokens += usage.get("prompt_tokens", 0)
        self.total_completion_tokens += usage.get("completion_tokens", 0)
        self.total_tokens += usage.get("total_tokens", 0)
        self.request_count += 1

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
        for idx in valid_indices:
            if not results[idx]:
                results[idx] = self.clean_text(texts[idx])
        return results

    def _submit_batch_with_retry(self, batch, max_len_per_item,
                                  unlimited, depth=0):
        sub_texts = [t for _, t in batch]
        try:
            sub_results = self._do_batch_translate(
                sub_texts, max_len_per_item, unlimited)
            return ({orig_idx: sub_results[j]
                     for j, (orig_idx, _) in enumerate(batch)}, 0)
        except Exception as e:
            if depth >= self.MAX_SPLIT_DEPTH or \
                    len(batch) <= self.MIN_SPLIT_SIZE:
                print(f"[翻译失败] 批 {len(batch)} 条: {str(e)[:100]}")
                return ({orig_idx: "" for orig_idx, _ in batch},
                        len(batch))

            mid = len(batch) // 2
            print(f"[翻译重试] 拆 {len(batch)} → "
                  f"{mid}+{len(batch) - mid} (第 {depth + 1} 层)")
            left_dict, lf = self._submit_batch_with_retry(
                batch[:mid], max_len_per_item, unlimited, depth + 1)
            right_dict, rf = self._submit_batch_with_retry(
                batch[mid:], max_len_per_item, unlimited, depth + 1)
            left_dict.update(right_dict)
            return left_dict, lf + rf

    def _do_batch_translate_parallel(self, texts,
                                     max_workers=4,
                                     batch_size=None,
                                     max_len_per_item=None,
                                     unlimited=True,
                                     progress_cb=None,
                                     stage_label=""):
        if not texts:
            return []

        from concurrent.futures import ThreadPoolExecutor, as_completed

        if batch_size is None:
            batch_size = self.DEFAULT_BATCH_SIZE

        indexed = list(enumerate(texts))
        batches = [indexed[i:i + batch_size]
                   for i in range(0, len(indexed), batch_size)]
        results = [""] * len(texts)

        total_items = len(texts)
        done_items = 0
        fail_items = 0
        start_ts = time.time()
        last_report = [0.0]

        def _report(force=False):
            now = time.time()
            if not force and (now - last_report[0]) < 0.3:
                return
            last_report[0] = now

            elapsed = now - start_ts
            speed = done_items / elapsed if elapsed > 0 else 0
            remain = (total_items - done_items) / speed if speed > 0 else 0
            pct = (done_items / total_items * 100) if total_items else 0

            fail_txt = f"  |  失败 {fail_items}" if fail_items > 0 else ""
            if progress_cb:
                try:
                    progress_cb(
                        f"{stage_label} {done_items}/{total_items} "
                        f"({pct:.0f}%)  |  "
                        f"{speed:.1f} 条/秒  |  "
                        f"剩余 {_fmt_duration(remain)}"
                        f"{fail_txt}"
                    )
                except Exception:
                    pass

        _report(force=True)

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {}
            for batch in batches:
                fut = ex.submit(
                    self._submit_batch_with_retry,
                    batch, max_len_per_item, unlimited, 0)
                futures[fut] = batch

            for fut in as_completed(futures):
                batch = futures[fut]
                try:
                    result_dict, failed = fut.result()
                except Exception:
                    result_dict = {orig_idx: ""
                                   for orig_idx, _ in batch}
                    failed = len(batch)

                for orig_idx, text in result_dict.items():
                    if 0 <= orig_idx < len(results):
                        results[orig_idx] = text

                done_items += len(batch)
                fail_items += failed
                _report()

        _report(force=True)
        return results

    # ============================================================
    def translate_folders(self, folder_names,
                          max_total_len=90,
                          min_translated_len=15,
                          retry_times=3,
                          progress_cb=None,
                          max_workers=4,
                          target_dir=None):
        folder_data = []
        middle_list = []

        desc_map = {}
        if target_dir:
            if progress_cb:
                progress_cb(
                    f"阶段⓪ 扫描 描述.txt · 共 {len(folder_names)} 个文件夹 · "
                    f"{max_workers} 线程")
            desc_map = self._scan_descs_parallel(
                folder_names, target_dir,
                max_workers=max_workers,
                progress_cb=progress_cb,
            )
            if progress_cb:
                progress_cb(
                    f"阶段⓪ 完成 · 找到 {len(desc_map)} 个 描述.txt")

        desc_count = 0
        for old_name in folder_names:
            number, suffix, middle = self.extract_parts(old_name)
            if number is None:
                folder_data.append({
                    "old": old_name, "new": "", "error": "无数字前缀",
                    "number": "", "suffix": "", "middle": "",
                    "translated": "", "desc_used": False,
                })
                continue

            desc_used = False
            if old_name in desc_map:
                middle = desc_map[old_name]
                desc_used = True
                desc_count += 1

            folder_data.append({
                "old": old_name, "new": "", "error": None,
                "number": number, "suffix": suffix,
                "middle": middle,
                "translated": "",
                "desc_used": desc_used,
            })
            middle_list.append(middle)

        if progress_cb and desc_count > 0:
            progress_cb(f"★ 使用 描述.txt 作为翻译源: {desc_count} 个")

        valid_idx_map = [i for i, d in enumerate(folder_data)
                         if d["error"] is None]
        valid_middles = [folder_data[i]["middle"] for i in valid_idx_map]
        if not valid_middles:
            return folder_data

        total_valid = len(valid_middles)
        bs = self.DEFAULT_BATCH_SIZE

        if progress_cb:
            progress_cb(f"阶段① 完整翻译 · 共 {total_valid} 条 · "
                        f"批 {bs} · 并发 {max_workers}")

        full_results = self._do_batch_translate_parallel(
            valid_middles, max_workers=max_workers,
            batch_size=bs, unlimited=True,
            progress_cb=progress_cb, stage_label="阶段①")

        retry_indices = [i for i, t in enumerate(full_results)
                         if len(t.strip()) < min_translated_len]

        for attempt in range(retry_times):
            if not retry_indices:
                break
            if progress_cb:
                progress_cb(f"阶段② 重译 {attempt + 1}/{retry_times} · "
                            f"待重译 {len(retry_indices)} 条")

            retry_texts = [valid_middles[i] for i in retry_indices]
            try:
                retry_results = self._do_batch_translate_parallel(
                    retry_texts, max_workers=max_workers,
                    batch_size=bs, unlimited=True,
                    progress_cb=progress_cb,
                    stage_label=f"阶段② ({attempt + 1}/{retry_times})")
            except Exception:
                break

            still = []
            for j, orig_i in enumerate(retry_indices):
                trans = retry_results[j] if j < len(retry_results) else ""
                if trans and len(trans.strip()) >= min_translated_len:
                    full_results[orig_i] = trans
                else:
                    still.append(orig_i)
            retry_indices = still

        for i in retry_indices:
            if len(full_results[i].strip()) < min_translated_len:
                full_results[i] = self.clean_text(valid_middles[i])

        if progress_cb:
            progress_cb("阶段③ 检查超长...")

        over_indices, over_texts, max_mid_list = [], [], []
        for j, orig_i in enumerate(valid_idx_map):
            d = folder_data[orig_i]
            prefix_len = len(d["number"]) + 1
            suffix_len = len(d["suffix"]) + 1 if d["suffix"] else 0
            mml = max(5, max_total_len - prefix_len - suffix_len)
            max_mid_list.append(mml)
            if len(full_results[j]) > mml:
                over_indices.append(j)
                over_texts.append(full_results[j])

        if over_indices:
            if progress_cb:
                progress_cb(f"阶段③ 精简 {len(over_indices)} 条超长...")

            min_allowed = min(max_mid_list[i] for i in over_indices)
            try:
                opt_results = self._do_batch_translate_parallel(
                    over_texts, max_workers=max_workers, batch_size=bs,
                    max_len_per_item=min_allowed, unlimited=False,
                    progress_cb=progress_cb, stage_label="阶段③")
            except Exception:
                opt_results = [t[:min_allowed].rstrip() for t in over_texts]

            for k, orig_j in enumerate(over_indices):
                if k < len(opt_results) and opt_results[k]:
                    full_results[orig_j] = opt_results[k]
                else:
                    full_results[orig_j] = full_results[orig_j][
                        :max_mid_list[orig_j]].rstrip()
        else:
            if progress_cb:
                progress_cb("阶段③ 无超长，跳过")

        for j, orig_i in enumerate(valid_idx_map):
            d = folder_data[orig_i]
            translated = full_results[j][:max_mid_list[j]].rstrip()
            d["translated"] = translated
            d["new"] = self.build_final_name(
                d["number"], translated, d["suffix"], max_total_len)

        if progress_cb:
            progress_cb("✅ 翻译完成")

        return folder_data

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass