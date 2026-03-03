"""
System tray icon for OBS Remote.
Pure control panel — the Windows Service runs the actual HTTP server.
The tray queries the server's /api/status endpoint to show live status.
"""

import json
import os
import subprocess
import sys
import threading
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
    # Outer circle
    draw.ellipse([2, 2, size - 2, size - 2], fill=color)
    # White dot in center
    center = size // 2
    r = size // 6
    draw.ellipse([center - r, center - r, center + r, center + r], fill="white")
    return img


def _get_server_status(port: int) -> dict | None:
    """Query the local server for status. Returns None if unreachable."""
    try:
        with urllib.request.urlopen(
            f"http://localhost:{port}/api/status", timeout=0.5
        ) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _open_ui():
    cfg = config.load()
    port = cfg.get("server_port", 42069)
    webbrowser.open(f"http://localhost:{port}")


def _open_settings():
    """Open the config file in Notepad for manual editing."""
    from server.config import _CONFIG_FILE
    os.startfile(str(_CONFIG_FILE))


def _open_logs():
    """Open the log file in Notepad."""
    log_file = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "OBSRemote" / "obs_remote.log"
    if log_file.exists():
        os.startfile(str(log_file))
    else:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "No log file found yet.", "OBS Remote", 0)


def _restart_service():
    subprocess.Popen(
        ["sc", "stop", "OBSRemote"],
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).wait()
    subprocess.Popen(
        ["sc", "start", "OBSRemote"],
        creationflags=subprocess.CREATE_NO_WINDOW,
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
    sys.exit(0)


def run_tray():
    """Start the system tray icon. This call blocks until the icon is stopped."""
    icon_image = _create_icon_image()

    def menu_items():
        cfg = config.load()
        port = cfg.get("server_port", 42069)
        status = _get_server_status(port)

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
            pystray.MenuItem(f"Open UI", lambda i, it: _open_ui()),
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
