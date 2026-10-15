## 项目
- 名: Folder_processing_tool
- 路径: L:\PythonProject1\Folder_processing_tool
- 技术栈: Python 3 + tkinter + SQLite
- 主入口: main.py
- 7 个 Tab: A名称清洗 / B批量翻译 / C图片处理 / D历史报告 / E数据入库 / F整理数据 / G产品表格
- 数据库: data\products.db（36,580 条）
- 配置: %APPDATA%\FolderProcessingTool\*.json
- Gitee: https://gitee.com/kuangren911/folder-processing-tool

## 已完成关键优化

### A 名称清洗
- 合并 A2/3/4 → 一次 rename
- PreviewTable 用 _iids 缓存（O(1) 更新）
- 线程数默认 4（界面可调 1~16）
- UI 刷新每 200 条

### B 批量翻译
- 优先读 描述.txt（v7 提取规则：去 emoji/价格/尺码/ID）
- 批大小 40，动态 max_tokens，超时 120s
- 批次失败自动拆分重试（3 层）
- 进度/速度/剩余时间 上报
- 并发默认 8

### E 数据入库
- 顶部 E1/E2 模式切换（持久化到 config.json）
- E1：从描述.txt 读尺码（跳过 OCR），16 线程
- E2：原 OCR 流程，6 进程 GPU
- OCR 引擎延迟检测（不卡启动）
- desc_size_parser.py：三级搜索 + has_ban 全文判断

### F 整理数据
- 顶部数据源 + xlsx 合并单行（竖线分隔）
- 2×2 田字格：
  - 上左 筛选条件 / 上右 批量修改
  - 下左 相似度筛选 / 下右 二次翻译
- 列宽可拖动 + 保存到 %APPDATA%\tab_f_col_widths.json
- 右键菜单：恢复默认列宽

### G 产品表格
- 2×2 田字格：
  - 上左 数据源 / 上右 模板&输出
  - 下左 参数 / 下右 价格公式参数
- 已用标记（g_used_products 表）
- 随机抽取自动排除已用
- 一键清空标记
- 价格公式：calc_price(CHUPRICE)
- 配置导入/导出 + 自动保存

## core/ 模块状态

| 文件 | 版本 | 关键变化 |
|------|------|---------|
| db_manager.py | v2 | isolation_level=None、WAL、with 支持 |
| brand_manager.py | v2 | 长词优先、词边界正则、mapping keys |
| desc_size_parser.py | v2 | 新增，从 描述.txt 提尺码 |
| e_pipeline.py | 原版 | OCR 引擎 + parse_sizes |
| e_pipeline_mp.py | 原版 | 多进程 OCR |
| fs_executor.py | v2 | stem.lstrip("0") |
| g_generator.py | v5 | 首图 fallback、价格公式、GROUP 日期前缀 |
| preview_table.py | v2 | _iids 缓存 |
| ru_translator.py | v2 | 线程锁 + 退避重试 |
| translator.py | v7 | 描述提取规则 |

## 已知问题

1. E1 对 9image 归档目录失败（描述.txt 被 C 模块弄丢）
2. 相似度筛选后 _all_rows 覆盖，不可恢复
3. F 的 FIELDS 缺 local_url / source_dir
4. base_tab.process_table 阻塞主线程

## 开发约定

- 先给方案对比，用户定稿后再写代码
- 修改前先给"完整替换版"，方便直接覆盖
- 重要文件建议 .bak
- 用中文，简洁清晰

## 安全提醒

- 之前 config.json 泄露 API Key，已提示用户删除
- 新代码用 get_api_key() 从环境变量读取