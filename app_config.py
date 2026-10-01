"""Resource paths and per-user settings; login secrets belong to Chromium."""

import json
import os
import sys
from pathlib import Path

APP_NAME = 'PixivBatchBookmark'
VERSION = '1.0.1'


def resource_path(name: str) -> Path:
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return root / 'resources' / name


def user_data_dir() -> Path:
    root = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_settings() -> dict:
    defaults = {'proxy': '', 'interval_ms': 1200}
    try:
        value = json.loads((user_data_dir() / 'settings.json').read_text(encoding='utf-8'))
        if isinstance(value, dict):
            defaults['proxy'] = value.get('proxy', '') if isinstance(value.get('proxy'), str) else ''
            interval = value.get('interval_ms', 1200)
            if type(interval) is int:
                defaults['interval_ms'] = max(1000, min(10000, interval))
    except (OSError, ValueError):
        pass
    return defaults


def save_settings(settings: dict):
    path = user_data_dir() / 'settings.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)
