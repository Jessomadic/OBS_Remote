"""
System tray icon for OBS Remote.
Runs alongside the server so users can open the UI, check status,
and exit from the notification area.
"""

import os
import subprocess
import sys
import threading
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


def _open_ui():
    cfg = config.load()
    port = cfg.get("server_port", 42069)
    webbrowser.open(f"http://localhost:{port}")


def _open_settings():
    """Open the config file in Notepad for manual editing."""
    import os
    appdata = Path(os.environ.get("APPDATA", Path.home())) / "OBSRemote" / "config.json"
    os.startfile(str(appdata))


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
    from server import updater
    info = updater.check_now()
    if info:
        updater.download_and_apply(info)


def _quit(icon, item):
    icon.stop()
    # Stop the service if running as a service launcher; otherwise just exit
    sys.exit(0)


def run_tray():
    """Start the system tray icon. This call blocks until the icon is stopped."""
    icon_image = _create_icon_image()

    def make_menu():
        cfg = config.load()
        port = cfg.get("server_port", 42069)
        from server import obs_client as obs
        status = "Connected to OBS" if obs.is_connected() else "OBS not connected"
        return pystray.Menu(
            pystray.MenuItem(f"OBS Remote v{_version()}", None, enabled=False),
            pystray.MenuItem(status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(f"Open UI  (localhost:{port})", lambda i, it: _open_ui()),
            pystray.MenuItem("Settings / Config", lambda i, it: _open_settings()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Check for updates", lambda i, it: _check_update()),
            pystray.MenuItem("Restart service", lambda i, it: _restart_service()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit tray icon", _quit),
        )

    icon = pystray.Icon(
        name="OBSRemote",
        icon=icon_image,
        title="OBS Remote",
        menu=make_menu(),
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
