"""Shared pytest fixtures and path setup for OBS Remote tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure the project root is on sys.path so 'server', 'version', etc. are importable
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Stub out packages that require external installs or Windows-only binaries.
# This lets the test suite run without obsws_python, pywin32, pystray, etc.
# ---------------------------------------------------------------------------

def _stub(name: str, **attrs) -> MagicMock:
    m = MagicMock(name=name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m

# obsws-python — OBS WebSocket client (requires a running OBS instance)
if "obsws_python" not in sys.modules:
    obs_stub = _stub("obsws_python")
    obs_stub.ReqClient = MagicMock
    obs_stub.EventClient = MagicMock

# pywin32 service modules (Windows-only, not needed for HTTP/config tests)
for _mod in ("win32serviceutil", "win32service", "win32event", "servicemanager"):
    if _mod not in sys.modules:
        _stub(_mod)

# pystray + Pillow (UI-only, not needed for server tests)
if "pystray" not in sys.modules:
    _stub("pystray")
if "PIL" not in sys.modules:
    _stub("PIL")
    _stub("PIL.Image")
    _stub("PIL.ImageDraw")
