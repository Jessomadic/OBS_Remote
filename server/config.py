"""
Configuration management for OBS Remote.
Settings are stored in %ProgramData%/OBSRemote/config.json (shared between
the Windows Service and the tray icon process).
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Primary location — shared between the Windows Service (SYSTEM) and tray (user).
_CONFIG_DIR = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "OBSRemote"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

# Legacy location used before the switch to ProgramData.
# Only accessible in user-context processes (tray); the SYSTEM service account
# sees a different APPDATA path, so migration silently no-ops there.
_LEGACY_DIR = Path(os.environ.get("APPDATA", "")) / "OBSRemote"
_LEGACY_CONFIG_FILE = _LEGACY_DIR / "config.json"

_DEFAULTS = {
    "obs_host": "localhost",
    "obs_port": 4455,
    "obs_password": "",
    "server_port": 42069,
    "check_updates": True,
    "github_repo": "Jessomadic/OBS_Remote",
}

# Keep old name as alias so other modules that imported _APPDATA still work.
_APPDATA = _CONFIG_DIR


def _ensure_dir():
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _try_load_legacy() -> dict | None:
    """Return the legacy APPDATA config if it has a saved password, else None.

    Used to migrate passwords from the old per-user APPDATA location to the
    new shared ProgramData location.  This only works from user-context
    processes (tray icon); the SYSTEM service sees a different APPDATA path.
    """
    try:
        if _LEGACY_CONFIG_FILE.exists():
            with open(_LEGACY_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("obs_password"):
                return data
    except Exception:
        pass
    return None


def load() -> dict:
    _ensure_dir()
    if not _CONFIG_FILE.exists():
        # First run in new location — migrate from legacy APPDATA if available.
        legacy = _try_load_legacy()
        if legacy:
            save(legacy)
            logger.info("Config migrated from APPDATA to ProgramData")
            data = legacy
        else:
            save(_DEFAULTS.copy())
            return _DEFAULTS.copy()
    else:
        with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # If the saved password is empty, try recovering it from the legacy location.
        # This handles upgrades where ProgramData was created fresh (empty password)
        # while the real password was only ever stored in the old APPDATA location.
        if not data.get("obs_password"):
            legacy = _try_load_legacy()
            if legacy:
                data["obs_password"] = legacy["obs_password"]
                save(data)
                logger.info("Recovered password from legacy APPDATA config")
    # Merge in any new default keys added by newer versions.
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
    # Write to a temp file then rename so a crash mid-write can't corrupt the config.
    tmp = _CONFIG_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    tmp.replace(_CONFIG_FILE)


def get(key: str):
    return load().get(key, _DEFAULTS.get(key))


def set_value(key: str, value):
    cfg = load()
    cfg[key] = value
    save(cfg)
