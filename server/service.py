"""
Windows Service wrapper for OBS Remote.

Install:   python service.py install
Start:     python service.py start
Stop:      python service.py stop
Remove:    python service.py remove

Or use the installer which handles all of this automatically.
"""

import logging
import subprocess
import sys
import threading

import servicemanager
import win32event
import win32service
import win32serviceutil

logger = logging.getLogger(__name__)

SERVICE_NAME = "OBSRemote"
SERVICE_DISPLAY_NAME = "OBS Remote"
SERVICE_DESCRIPTION = "OBS Remote — web-based control panel for OBS Studio"


def _ensure_firewall_rules():
    """
    Guarantee the Windows Firewall rules exist for OBS Remote.

    The service runs as SYSTEM so it has full permission to add/update rules
    without a UAC prompt.  This self-heals cases where the installer was run
    without elevation, rules were manually removed, or the port changed.
    """
    from server import config
    port = config.get("server_port") or 42069
    exe = sys.executable  # path to OBSRemote.exe in the install dir

    def _run(args):
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0 and result.stderr:
            logger.warning("netsh: %s", result.stderr.strip())

    try:
        # Remove any stale rules first so we always have a clean set
        _run(["netsh", "advfirewall", "firewall", "delete", "rule", "name=OBS Remote"])
        _run(["netsh", "advfirewall", "firewall", "delete", "rule", "name=OBS Remote Port"])

        # Program-based rule — allows the exe on all network profiles
        _run([
            "netsh", "advfirewall", "firewall", "add", "rule",
            "name=OBS Remote", "dir=in", "action=allow",
            f"program={exe}", "enable=yes", "profile=any",
        ])

        # Port-based rule — belt-and-suspenders; reliable for SYSTEM services
        _run([
            "netsh", "advfirewall", "firewall", "add", "rule",
            "name=OBS Remote Port", "dir=in", "action=allow",
            "protocol=TCP", f"localport={port}", "enable=yes", "profile=any",
        ])
        logger.info("Firewall rules ensured (exe=%s, port=%d)", exe, port)
    except Exception as e:
        logger.warning("Could not update firewall rules: %s", e)


class OBSRemoteService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION
    # Start automatically with Windows — without this pywin32 defaults to
    # SERVICE_DEMAND_START (manual), so the server never starts after a reboot.
    _svc_start_type_ = win32service.SERVICE_AUTO_START

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)
        self._server_thread: threading.Thread | None = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self._stop_event)
        self._shutdown()

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        try:
            _ensure_firewall_rules()
        except Exception as e:
            # Non-fatal: server must start even if firewall setup fails
            logger.warning("Firewall rule setup failed (non-fatal): %s", e)
        self._start_server()
        win32event.WaitForSingleObject(self._stop_event, win32event.INFINITE)

    def _start_server(self):
        from server.main import run_server
        self._server_thread = threading.Thread(target=run_server, daemon=True, name="OBSRemoteServer")
        self._server_thread.start()

    def _shutdown(self):
        from server import obs_client as obs
        obs.disconnect()
        # uvicorn will exit when the process exits; service framework handles cleanup


def main():
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(OBSRemoteService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(OBSRemoteService)


if __name__ == "__main__":
    main()
