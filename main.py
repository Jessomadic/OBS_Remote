"""
OBS Remote — top-level entry point.

When run directly (e.g. as a compiled exe):
  - If invoked with service arguments (install/start/stop/remove) → delegate to service.py
  - Otherwise → start server + tray icon

The installer registers this as a Windows service AND places a startup shortcut
that runs the tray icon. The service itself runs the FastAPI server headlessly.
"""

import sys


def _is_service_call():
    service_args = {"install", "start", "stop", "remove", "restart", "debug", "update"}
    return len(sys.argv) > 1 and sys.argv[1].lower() in service_args


if __name__ == "__main__":
    if _is_service_call():
        # Delegate to Windows service handler
        from server.service import main as service_main
        service_main()
    else:
        # Tray-only mode: the Windows Service runs the actual HTTP server.
        # The tray is purely a control panel — starting a second server here
        # would conflict with the service on the same port.
        from server.tray import run_tray
        run_tray()
