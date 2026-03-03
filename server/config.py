"""
Configuration management for OBS Remote.
Settings are stored in %APPDATA%/OBSRemote/config.json
"""

import json
import os
from pathlib import Path

# Use ProgramData so both the Windows Service (SYSTEM account) and the
# tray process (user account) read and write the same config file.
_APPDATA = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "OBSRemote"
_CONFIG_FILE = _APPDATA / "config.json"

_DEFAULTS = {
    "obs_host": "localhost",
    "obs_port": 4455,
    "obs_password": "",
    "server_port": 42069,
    "check_updates": True,
    "github_repo": "Jessomadic/OBS_Remote",
}


def _ensure_dir():
    _APPDATA.mkdir(parents=True, exist_ok=True)


def load() -> dict:
    _ensure_dir()
    if not _CONFIG_FILE.exists():
        save(_DEFAULTS.copy())
        return _DEFAULTS.copy()
    with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # fill in any missing keys from defaults
    updated = False
    for k, v in _DEFAULTS.items():
        if k not in data:
            data[k] = v
            updated = True
    if updated:
        save(data)
    return data


def save(cfg: dict):
    _ensure_dir()
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get(key: str):
    return load().get(key, _DEFAULTS.get(key))


def set_value(key: str, value):
    cfg = load()
    cfg[key] = value
    save(cfg)
