"""
Fully silent auto-updater.
Checks GitHub Releases for a newer version, downloads the installer, and
runs it silently. The installer is expected to stop the service, replace
files, and restart the service automatically.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests

from server import config
from version import __version__

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
_CHECK_INTERVAL = 60 * 60  # 1 hour
_update_available: dict | None = None
_update_applied = False

# Local cache stores the asset ID of the last applied (or baseline) installer.
# Comparing asset IDs catches new builds even when the version number hasn't changed.
_CACHE_FILE = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "OBSRemote" / "update_cache.json"


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict):
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception as e:
        logger.warning("Could not write update cache: %s", e)


def get_update_available() -> dict | None:
    """Returns info about a pending update, or None if up-to-date."""
    return _update_available


def check_now() -> dict | None:
    """Synchronously check for an update and return release info if found.

    Uses the GitHub asset ID as a fingerprint rather than the version string,
    so a new build is detected even when the version number hasn't changed.
    """
    global _update_available
    repo = config.get("github_repo")
    cache = _load_cache()
    try:
        url = _GITHUB_API.format(repo=repo)
        resp = requests.get(url, timeout=10, headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        data = resp.json()

        # Find the .exe installer asset
        exe_asset = None
        for asset in data.get("assets", []):
            if asset["name"].endswith(".exe"):
                exe_asset = asset
                break
        if not exe_asset:
            return None

        asset_id = str(exe_asset["id"])
        latest_tag = data.get("tag_name", "").lstrip("v") or "unknown"
        last_asset_id = cache.get("last_applied_asset_id")

        # If no baseline is cached yet (fresh install), record current asset and
        # treat this release as already applied so we don't re-run the installer.
        if last_asset_id is None:
            _save_cache({"last_applied_asset_id": asset_id})
            logger.info("Update cache initialised with asset id %s", asset_id)
            return None

        # Update if asset ID changed (same version, new build) OR version string differs
        is_new_asset = asset_id != last_asset_id
        is_new_version = latest_tag not in ("unknown", __version__)

        if is_new_asset or is_new_version:
            _update_available = {
                "version": latest_tag,
                "current": __version__,
                "url": exe_asset["browser_download_url"],
                "asset_id": asset_id,
                "name": data.get("name", f"v{latest_tag}"),
                "body": data.get("body", ""),
            }
            logger.info(
                "Update available: v%s → v%s (asset %s, new_asset=%s, new_version=%s)",
                __version__, latest_tag, asset_id, is_new_asset, is_new_version,
            )
            return _update_available

    except Exception as e:
        logger.warning("Update check failed: %s", e)
    return None


def download_and_apply(update_info: dict):
    """Download the installer and run it silently in a background thread."""
    def _do_update():
        global _update_applied
        logger.info("Downloading update from %s", update_info["url"])
        try:
            resp = requests.get(update_info["url"], stream=True, timeout=120)
            resp.raise_for_status()
            tmp_dir = tempfile.mkdtemp(prefix="obs_remote_update_")
            installer_path = Path(tmp_dir) / f"OBSRemote_setup_{update_info['version']}.exe"
            with open(installer_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info("Installer downloaded to %s", installer_path)
            _save_cache({"last_applied_asset_id": update_info["asset_id"]})
            _update_applied = True
            # Run Inno Setup installer silently.
            # Use ShellExecuteW so Windows can prompt for UAC elevation
            # (Inno Setup embeds requireAdministrator in its manifest).
            # subprocess.Popen with CREATE_NO_WINDOW cannot trigger UAC.
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "open",
                    str(installer_path),
                    "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS",
                    None,
                    0,  # SW_HIDE
                )
            else:
                subprocess.Popen(
                    [str(installer_path), "/VERYSILENT", "/SUPPRESSMSGBOXES",
                     "/NORESTART", "/CLOSEAPPLICATIONS"],
                )
        except Exception as e:
            logger.error("Update failed: %s", e)
            _update_applied = False

    t = threading.Thread(target=_do_update, daemon=True)
    t.start()


def _background_loop():
    """Periodic update check loop."""
    # Wait a bit before first check so startup is not delayed
    time.sleep(30)
    while True:
        info = check_now()
        if info and not _update_applied:
            download_and_apply(info)
        time.sleep(_CHECK_INTERVAL)


def start_background_checker():
    """Start the background update-check thread."""
    t = threading.Thread(target=_background_loop, daemon=True, name="UpdateChecker")
    t.start()
    logger.info("Auto-updater started (checking every %d minutes)", _CHECK_INTERVAL // 60)
