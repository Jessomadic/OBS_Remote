"""
System tray icon for OBS Remote.
Pure control panel — the Windows Service runs the actual HTTP server.
The tray queries the server's /api/status endpoint to show live status,
via a background polling thread so the menu renders instantly.
"""

import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from server import config


def _create_icon_image(color: str = "#7C3AED") -> Image.Image:
    """Generate a simple circular icon with the OBS Remote brand color."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, size - 2, size - 2], fill=color)
    center = size // 2
    r = size // 6
    draw.ellipse([center - r, center - r, center + r, center + r], fill="white")
    return img


def _get_server_status(port: int) -> dict | None:
    """Query the local server for status. Returns None if unreachable."""
    try:
        # Bypass any user/system proxies that might break localhost requests
        proxy_handler = urllib.request.ProxyHandler({})
        opener = urllib.request.build_opener(proxy_handler)
        with opener.open(f"http://127.0.0.1:{port}/api/status", timeout=2) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _open_ui():
    cfg = config.load()
    port = cfg.get("server_port", 42069)
    webbrowser.open(f"http://localhost:{port}")


def _open_settings():
    """Open the config file in the default text editor."""
    from server.config import _CONFIG_FILE
    os.startfile(str(_CONFIG_FILE))


def _open_logs():
    """Open the log file in the default text editor."""
    log_file = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "OBSRemote" / "obs_remote.log"
    if log_file.exists():
        os.startfile(str(log_file))
    else:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "No log file found yet.", "OBS Remote", 0)


def _restart_service():
    """Restart the Windows service. Uses ShellExecute+runas to get admin elevation."""
    import ctypes
    ret = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        "powershell.exe",
        '-WindowStyle Hidden -Command "Restart-Service OBSRemote -Force"',
        None,
        0,  # SW_HIDE
    )
    if ret <= 32:
        ctypes.windll.user32.MessageBoxW(
            0,
            "Could not restart the service.\nAdministrator access is required.",
            "OBS Remote",
            0x10,  # MB_ICONERROR
        )


def _check_update():
    import ctypes
    from server import updater
    info = updater.check_now()
    if info:
        updater.download_and_apply(info)
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Update to v{info['version']} is downloading.\nThe app will restart automatically when ready.",
            "OBS Remote — Update Found",
            0x40,  # MB_ICONINFORMATION
        )
    else:
        ctypes.windll.user32.MessageBoxW(
            0,
            "You're already on the latest version.",
            "OBS Remote — Up to Date",
            0x40,
        )


def _quit(icon, item):
    icon.stop()
    # os._exit bypasses Python cleanup and terminates the whole process
    # immediately — sys.exit() called from a non-main thread only kills
    # that thread, leaving the process running.
    os._exit(0)


# ---------------------------------------------------------------------------
# Background status polling — keeps a cached result so menu renders instantly
# ---------------------------------------------------------------------------

_status_lock = threading.Lock()
_status_cache: dict | None = None
_status_port: int = 42069
_POLL_INTERVAL = 5  # seconds


def _status_poll_loop():
    """Poll /api/status every 5 seconds and cache the result."""
    global _status_cache, _status_port
    while True:
        try:
            cfg = config.load()
            port = cfg.get("server_port", 42069)
            _status_port = port
            status = _get_server_status(port)
        except Exception:
            status = None
        with _status_lock:
            _status_cache = status
        time.sleep(_POLL_INTERVAL)


def run_tray():
    """Start the system tray icon. This call blocks until the icon is stopped."""
    icon_image = _create_icon_image()

    # Start background status poller immediately
    poll_thread = threading.Thread(target=_status_poll_loop, daemon=True, name="StatusPoll")
    poll_thread.start()

    def menu_items():
        with _status_lock:
            status = _status_cache
        port = _status_port

        if status:
            server_line = f"Server running  (port {port})"
            obs_line = "OBS: Connected" if status.get("obs_connected") else "OBS: Not connected"
        else:
            server_line = f"Server not running  (port {port})"
            obs_line = "OBS: —"

        return [
            pystray.MenuItem(f"OBS Remote v{_version()}", None, enabled=False),
            pystray.MenuItem(server_line, None, enabled=False),
            pystray.MenuItem(obs_line, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open UI", lambda i, it: _open_ui()),
            pystray.MenuItem("Settings / Config", lambda i, it: _open_settings()),
            pystray.MenuItem("View logs", lambda i, it: _open_logs()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Check for updates", lambda i, it: _check_update()),
            pystray.MenuItem("Restart service", lambda i, it: _restart_service()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit tray icon", _quit),
        ]

    icon = pystray.Icon(
        name="OBSRemote",
        icon=icon_image,
        title="OBS Remote",
        menu=pystray.Menu(menu_items),
    )
    icon.run()


def _version() -> str:
    try:
        from version import __version__
        return __version__
    except Exception:
        return "?"


def start_tray_thread():
    """Start tray icon in a background thread (non-blocking)."""
    t = threading.Thread(target=run_tray, daemon=True, name="TrayIcon")
    t.start()
    return t
