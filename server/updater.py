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
_update_downloading = False

# Callbacks fired when a download starts or completes.
# Set via set_callbacks() — used by main.py to broadcast WS events.
_on_download_start = None
_on_download_complete = None

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


def set_callbacks(on_start=None, on_complete=None):
    """Register callbacks fired when a download starts/completes.

    on_start(info: dict)            — called when download begins
    on_complete(info: dict, ok: bool) — called when download finishes (ok=True) or fails
    """
    global _on_download_start, _on_download_complete
    _on_download_start = on_start
    _on_download_complete = on_complete


def get_update_available() -> dict | None:
    """Returns info about a pending update, or None if up-to-date."""
    return _update_available


def get_update_status() -> dict:
    """Returns current download/apply state."""
    return {"downloading": _update_downloading, "applied": _update_applied}


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


def _run_installer(installer_path: Path):
    """Launch the Inno Setup installer (fire-and-forget).

    When already admin (SYSTEM service or elevated tray): launch directly via
    subprocess so it runs without a UAC prompt — avoids the prompt timing out
    when the caller is running in Session 0 with no desktop.

    When running as a regular user: use ShellExecuteW "runas" to trigger UAC
    elevation so the installer gets the admin rights it needs.
    """
    _args = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"
    if sys.platform == "win32":
        import ctypes
        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        logger.info("Launching installer (path=%s, admin=%s)", installer_path, is_admin)
        if is_admin:
            # Already elevated (SYSTEM service or admin tray) — launch directly.
            subprocess.Popen(
                [str(installer_path)] + _args.split(),
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
        else:
            # Standard user — request elevation via UAC.
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", str(installer_path), _args, None, 1,
            )
    else:
        subprocess.Popen([str(installer_path)] + _args.split())


def _download_and_run(update_info: dict, dialog=None) -> bool:
    """Download the installer and run it.  Blocking.  Returns True on success.

    If *dialog* is an UpdateDialog instance, drives its progress display.
    After the installer is launched the current process exits so the
    installer can replace the running exe cleanly.

    Fires _on_download_start / _on_download_complete callbacks so callers
    (e.g. main.py) can broadcast progress to connected browser clients.
    """
    global _update_applied, _update_downloading
    _update_downloading = True
    if _on_download_start:
        try:
            _on_download_start(update_info)
        except Exception:
            pass

    version = update_info["version"]
    logger.info("Downloading update v%s from %s", version, update_info["url"])

    def _log(msg):
        logger.info(msg)
        if dialog:
            dialog.log(msg)

    try:
        resp = requests.get(update_info["url"], stream=True, timeout=120)
        resp.raise_for_status()

        content_length = int(resp.headers.get("Content-Length", 0))
        if dialog and content_length:
            dialog.set_progress(0)

        tmp_dir = tempfile.mkdtemp(prefix="obs_remote_update_")
        installer_path = Path(tmp_dir) / f"OBSRemote_setup_{version}.exe"

        downloaded = 0
        with open(installer_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if dialog and dialog.cancelled:
                    logger.info("Update cancelled by user")
                    _update_downloading = False
                    return False
                f.write(chunk)
                downloaded += len(chunk)
                if dialog and content_length:
                    pct = min(100.0, downloaded * 100 / content_length)
                    dialog.set_progress(pct)
                    mb_done = downloaded / (1024 * 1024)
                    mb_total = content_length / (1024 * 1024)
                    dialog.set_status(
                        f"Downloading OBS Remote v{version}..."
                        f"  {mb_done:.1f} / {mb_total:.1f} MB"
                    )

        size_mb = downloaded / (1024 * 1024)
        _log(f"Download complete — {size_mb:.1f} MB saved to {installer_path}")
        _save_cache({"last_applied_asset_id": update_info["asset_id"]})
        _update_applied = True
        _update_downloading = False

        if _on_download_complete:
            try:
                _on_download_complete(update_info, True)
            except Exception:
                pass

        if dialog:
            dialog.set_indeterminate()
            dialog.set_status(f"Installing OBS Remote v{version}...")
            dialog.disable_cancel()
            _log("Stopping OBS Remote service and tray...")
            _log("Running installer — please approve the UAC prompt...")

        _run_installer(installer_path)

        if dialog:
            _log("Installer launched.  OBS Remote will restart automatically.")
            dialog.set_status("OBS Remote is restarting...")

        # Give the dialog a moment to display the final message, then exit so
        # the installer can replace the running exe without file-lock errors.
        # (The installer's CurStepChanged also does taskkill, so this is
        # belt-and-suspenders — whichever happens first is fine.)
        import time as _time
        _time.sleep(3)
        os._exit(0)

        return True  # unreachable after _exit, but keeps the return type clear

    except Exception as e:
        logger.error("Update failed: %s", e)
        _update_applied = False
        _update_downloading = False
        if dialog:
            dialog.set_status("Update failed — see log for details.")
            dialog.log(f"Error: {e}")
            dialog.disable_cancel()
        if _on_download_complete:
            try:
                _on_download_complete(update_info, False)
            except Exception:
                pass
        return False


def download_and_apply(update_info: dict, show_ui: bool = True):
    """Download the installer and run it in a background thread.

    When *show_ui* is True (the default), an UpdateDialog progress window
    is shown for the duration of the download and install.
    """
    if show_ui:
        try:
            from server.update_ui import UpdateDialog
            dlg = UpdateDialog(update_info["version"])
            # Run the tkinter window in its own daemon thread
            ui_thread = threading.Thread(target=dlg.run, daemon=True, name="UpdateUI")
            ui_thread.start()
            dlg._ready.wait(timeout=5)
            t = threading.Thread(
                target=_download_and_run,
                args=(update_info,),
                kwargs={"dialog": dlg},
                daemon=True,
                name="UpdateDownload",
            )
            t.start()
            return
        except Exception as e:
            logger.warning("Could not show update UI (%s) — falling back to silent", e)

    t = threading.Thread(target=_download_and_run, args=(update_info,), daemon=True, name="UpdateDownload")
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
