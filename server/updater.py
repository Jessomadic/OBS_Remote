"""
Fully silent auto-updater.
Checks GitHub Releases for a newer version, downloads the installer, and
runs it silently. The installer is expected to stop the service, replace
files, and restart the service automatically.
"""

import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests
from packaging.version import Version

from server import config
from version import __version__

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
_CHECK_INTERVAL = 60 * 60  # 1 hour
_update_available: dict | None = None
_update_applied = False


def get_update_available() -> dict | None:
    """Returns info about a pending update, or None if up-to-date."""
    return _update_available


def check_now() -> dict | None:
    """Synchronously check for an update and return release info if found."""
    global _update_available
    repo = config.get("github_repo")
    try:
        url = _GITHUB_API.format(repo=repo)
        resp = requests.get(url, timeout=10, headers={"Accept": "application/vnd.github+json"})
        resp.raise_for_status()
        data = resp.json()
        latest_tag = data.get("tag_name", "").lstrip("v")
        if not latest_tag:
            return None
        if Version(latest_tag) > Version(__version__):
            # Find the .exe asset
            exe_url = None
            for asset in data.get("assets", []):
                if asset["name"].endswith(".exe"):
                    exe_url = asset["browser_download_url"]
                    break
            if exe_url:
                _update_available = {
                    "version": latest_tag,
                    "current": __version__,
                    "url": exe_url,
                    "name": data.get("name", f"v{latest_tag}"),
                    "body": data.get("body", ""),
                }
                logger.info("Update available: %s → %s", __version__, latest_tag)
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
