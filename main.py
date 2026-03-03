"""
OBS Remote — top-level entry point.

When run directly (e.g. as a compiled exe):
  - If invoked with service arguments (install/start/stop/remove) → delegate to service.py
  - If running in Windows Session 0 (started by SCM with no args) → delegate to service.py
  - Otherwise → start tray icon (control panel only; service owns the HTTP server)

Windows Session 0 is the non-interactive service session. The SCM starts
the exe without any argv args, so we can't distinguish it from a user
double-click via argv alone — we check the session ID instead.
"""

import sys


def _is_service_call() -> bool:
    """True when the user explicitly passed a service management command."""
    service_args = {"install", "start", "stop", "remove", "restart", "debug", "update"}
    return len(sys.argv) > 1 and sys.argv[1].lower() in service_args


def _running_as_service() -> bool:
    """True when this process is in Windows Session 0 (started by SCM)."""
    try:
        import ctypes
        session_id = ctypes.c_ulong(0)
        pid = ctypes.windll.kernel32.GetCurrentProcessId()
        ctypes.windll.kernel32.ProcessIdToSessionId(pid, ctypes.byref(session_id))
        return session_id.value == 0
    except Exception:
        return False


if __name__ == "__main__":
    if _is_service_call() or _running_as_service():
        # Service management command (install/stop/…) OR started by SCM
        from server.service import main as service_main
        service_main()
    else:
        # Interactive user session — tray only.
        # The Windows Service is responsible for the HTTP server.
        from server.tray import run_tray
        run_tray()
