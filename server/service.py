"""
Windows Service wrapper for OBS Remote.

Install:   python service.py install
Start:     python service.py start
Stop:      python service.py stop
Remove:    python service.py remove

Or use the installer which handles all of this automatically.
"""

import logging
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


class OBSRemoteService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = SERVICE_DISPLAY_NAME
    _svc_description_ = SERVICE_DESCRIPTION

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
