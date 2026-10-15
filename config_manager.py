# config_manager.py
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "DEEPSEEK_API_KEY": "",
    "MODEL": "deepseek-chat",
    "MAX_TOTAL_LENGTH": 90,
    "MIN_TRANSLATED_LENGTH": 15,
    "RETRY_TIMES": 3,
    "DELAY": 0.05,
    "INPUT_TOKEN_PRICE": 0.00014,
    "OUTPUT_TOKEN_PRICE": 0.00028,
    "TARGET_LANG": "英文",
    "LAST_TARGET_DIR": "",
}


def load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def update_config(**kwargs):
    cfg = load_config()
    cfg.update(kwargs)
    save_config(cfg)
    return cfg