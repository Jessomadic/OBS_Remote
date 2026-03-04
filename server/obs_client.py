"""
OBS WebSocket v5 client wrapper.
Maintains a single connection and exposes a clean async interface.
"""

import logging
import threading
from typing import Optional

import obsws_python as obs

logger = logging.getLogger(__name__)

# Global client instances — guarded by _lock for thread safety
_lock = threading.Lock()
_req_client: Optional[obs.ReqClient] = None
_event_client: Optional[obs.EventClient] = None
_event_handlers: dict[str, list] = {}
_connected = False


def get_req() -> Optional[obs.ReqClient]:
    return _req_client


def is_connected() -> bool:
    return _connected


def connect(host: str, port: int, password: str):
    """Establish connection to OBS WebSocket.

    Disconnects any existing connection first, then connects fresh.
    Thread-safe: serialises against concurrent reconnect-loop calls.
    """
    global _req_client, _event_client, _connected
    pwd = password.strip() if password else None
    with _lock:
        # Tear down any previous connection cleanly before reconnecting
        _disconnect_unlocked()
        try:
            _req_client = obs.ReqClient(host=host, port=port, password=pwd, timeout=3)
            # Verify the connection is genuinely active with a real request
            _req_client.get_version()
            _event_client = obs.EventClient(host=host, port=port, password=pwd)
            _register_events()
            _connected = True
            logger.info("Connected to OBS at %s:%d", host, port)
        except Exception as e:
            _connected = False
            _req_client = None
            _event_client = None
            logger.error("Failed to connect to OBS: %s", e)
            raise


def disconnect():
    """Disconnect from OBS. Thread-safe."""
    with _lock:
        _disconnect_unlocked()


def _disconnect_unlocked():
    """Internal disconnect — caller must hold _lock."""
    global _req_client, _event_client, _connected
    _connected = False
    try:
        if _req_client:
            _req_client.disconnect()
    except Exception:
        pass
    try:
        if _event_client:
            _event_client.disconnect()
    except Exception:
        pass
    _req_client = None
    _event_client = None


def on_event(event_name: str):
    """Decorator to register an OBS event handler."""
    def decorator(fn):
        _event_handlers.setdefault(event_name, []).append(fn)
        return fn
    return decorator


def _register_events():
    """Wire up obsws-python callback to our dispatch table. Caller must hold _lock."""
    if not _event_client:
        return

    def make_handler(name):
        def handler(data):
            for fn in _event_handlers.get(name, []):
                try:
                    fn(data)
                except Exception as e:
                    logger.error("Event handler error for %s: %s", name, e)
        return handler

    events = [
        "CurrentProgramSceneChanged",
        "CurrentPreviewSceneChanged",
        "SceneListChanged",
        "SceneItemEnableStateChanged",
        "InputVolumeChanged",
        "InputMuteStateChanged",
        "StreamStateChanged",
        "RecordStateChanged",
        "ReplayBufferStateChanged",
        "VirtualcamStateChanged",
        "StudioModeStateChanged",
        "CurrentSceneCollectionChanged",
        "SceneCollectionListChanged",
        "SourceFilterEnableStateChanged",
    ]

    for event in events:
        callback_name = f"on_{_to_snake(event)}"
        handler = make_handler(event)
        if hasattr(_event_client, callback_name):
            setattr(_event_client, callback_name, handler)


def req(method: str, **kwargs):
    """
    Call any OBS WebSocket request by name.
    E.g. req("GetSceneList") or req("SetCurrentProgramScene", scene_name="Gaming")

    Marks _connected=False on any transport-level failure so the reconnect loop
    can detect the dead connection and re-establish it.
    """
    global _connected
    client = get_req()
    if not client:
        raise RuntimeError("Not connected to OBS")
    fn = getattr(client, _to_snake(method), None)
    if fn is None:
        raise AttributeError(f"Unknown OBS request: {method}")
    try:
        return fn(**kwargs) if kwargs else fn()
    except Exception as e:
        err = str(e).lower()
        # Detect transport-level failures (not application-level OBS errors).
        # Set _connected=False so the reconnect loop picks it up immediately.
        is_transport_error = (
            isinstance(e, (ConnectionError, TimeoutError, OSError, BrokenPipeError)) or
            any(x in err for x in (
                "connection", "socket", "broken pipe", "eof", "closed",
                "timeout", "timed out", "refused", "reset", "disconnected",
                "websocket", "handshake", "unreachable",
            ))
        )
        if is_transport_error:
            _connected = False
            logger.warning("OBS connection lost during req(%s): %s", method, e)
        raise


def _to_snake(name: str) -> str:
    """Convert PascalCase to snake_case for obsws-python method names."""
    import re
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
