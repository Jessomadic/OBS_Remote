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
        # Start server + tray icon (used when launched from startup shortcut or manually)
        import threading
        from server.main import run_server
        from server.tray import run_tray

        server_thread = threading.Thread(target=run_server, daemon=True, name="OBSRemoteServer")
        server_thread.start()

        # run_tray() blocks until the tray icon is exited
        run_tray()
