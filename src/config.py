"""CLIConductor configuration system."""

import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

DEFAULT_CONFIG: dict = {
    "cbc_import": {
        "min_message_count": 5,
        "max_sessions_shown": 30,
        "exclude_workdir_patterns": [],
        "project_dir_exact_match": False,
    }
}


def load_config() -> dict:
    """Load configuration from config.json, deep-merged with defaults."""
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        user_config = json.load(f)
    return _deep_merge(DEFAULT_CONFIG, user_config)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
