import os
import yaml
from pathlib import Path
from typing import Dict, Any

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"

class ConfigManager:
    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance.load()
        return cls._instance

    def load(self):
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}

    def get(self, key_path: str, default: Any = None) -> Any:
        keys = key_path.split(".")
        val = self._config
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

    def set(self, key_path: str, value: Any):
        keys = key_path.split(".")
        d = self._config
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(self._config, f, allow_unicode=True, sort_keys=False)

    @property
    def all_config(self) -> Dict[str, Any]:
        return self._config

config = ConfigManager()
