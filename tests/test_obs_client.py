"""
Tests for server.obs_client — connection state, req dispatch, disconnect.

All OBS WebSocket calls are mocked so no real OBS instance is needed.
"""

import pytest
from unittest.mock import MagicMock, patch, call

import server.obs_client as obs_mod


@pytest.fixture(autouse=True)
def reset_obs_globals():
    """Reset all module-level globals between tests to prevent state leaks."""
    obs_mod._req_client = None
    obs_mod._event_client = None
    obs_mod._connected = False
    obs_mod._event_handlers.clear()
    yield
    obs_mod._req_client = None
    obs_mod._event_client = None
    obs_mod._connected = False
    obs_mod._event_handlers.clear()


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_is_connected_false_initially():
    assert obs_mod.is_connected() is False


def test_get_req_returns_none_initially():
    assert obs_mod.get_req() is None


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------

def test_connect_sets_connected_true(monkeypatch):
    monkeypatch.setattr("server.obs_client.obs.ReqClient", lambda **kw: MagicMock())
    monkeypatch.setattr("server.obs_client.obs.EventClient", lambda **kw: MagicMock())

    obs_mod.connect("localhost", 4455, "")
    assert obs_mod.is_connected() is True


def test_connect_stores_req_client(monkeypatch):
    fake_req = MagicMock()
    monkeypatch.setattr("server.obs_client.obs.ReqClient", lambda **kw: fake_req)
    monkeypatch.setattr("server.obs_client.obs.EventClient", lambda **kw: MagicMock())

    obs_mod.connect("localhost", 4455, "")
    assert obs_mod.get_req() is fake_req


def test_connect_passes_host_port_password(monkeypatch):
    captured = {}

    def fake_req(**kw):
        captured.update(kw)
        return MagicMock()

    monkeypatch.setattr("server.obs_client.obs.ReqClient", fake_req)
    monkeypatch.setattr("server.obs_client.obs.EventClient", lambda **kw: MagicMock())

    obs_mod.connect("192.168.1.6", 4455, "secret")
    assert captured["host"] == "192.168.1.6"
    assert captured["port"] == 4455
    assert captured["password"] == "secret"


def test_connect_raises_and_leaves_disconnected_on_failure(monkeypatch):
    monkeypatch.setattr(
        "server.obs_client.obs.ReqClient",
        lambda **kw: (_ for _ in ()).throw(ConnectionRefusedError("refused")),
    )

    with pytest.raises(ConnectionRefusedError):
        obs_mod.connect("bad_host", 9999, "")

    assert obs_mod.is_connected() is False
    assert obs_mod.get_req() is None


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------

def test_disconnect_clears_connected_flag(monkeypatch):
    monkeypatch.setattr("server.obs_client.obs.ReqClient", lambda **kw: MagicMock())
    monkeypatch.setattr("server.obs_client.obs.EventClient", lambda **kw: MagicMock())
    obs_mod.connect("localhost", 4455, "")

    obs_mod.disconnect()
    assert obs_mod.is_connected() is False


def test_disconnect_clears_clients(monkeypatch):
    monkeypatch.setattr("server.obs_client.obs.ReqClient", lambda **kw: MagicMock())
    monkeypatch.setattr("server.obs_client.obs.EventClient", lambda **kw: MagicMock())
    obs_mod.connect("localhost", 4455, "")

    obs_mod.disconnect()
    assert obs_mod._req_client is None
    assert obs_mod._event_client is None


def test_disconnect_when_already_disconnected_does_not_raise():
    """Calling disconnect when not connected should be a no-op."""
    obs_mod.disconnect()  # should not raise
    assert obs_mod.is_connected() is False


def test_disconnect_calls_client_disconnect(monkeypatch):
    mock_req = MagicMock()
    mock_event = MagicMock()
    monkeypatch.setattr("server.obs_client.obs.ReqClient", lambda **kw: mock_req)
    monkeypatch.setattr("server.obs_client.obs.EventClient", lambda **kw: mock_event)
    obs_mod.connect("localhost", 4455, "")

    obs_mod.disconnect()
    mock_req.disconnect.assert_called_once()
    mock_event.disconnect.assert_called_once()


# ---------------------------------------------------------------------------
# req()
# ---------------------------------------------------------------------------

def test_req_raises_runtime_error_when_not_connected():
    with pytest.raises(RuntimeError, match="Not connected"):
        obs_mod.req("GetSceneList")


def test_req_calls_snake_case_method_on_client(monkeypatch):
    mock_req = MagicMock()
    mock_req.get_scene_list.return_value = MagicMock(scenes=[])
    monkeypatch.setattr("server.obs_client.obs.ReqClient", lambda **kw: mock_req)
    monkeypatch.setattr("server.obs_client.obs.EventClient", lambda **kw: MagicMock())
    obs_mod.connect("localhost", 4455, "")

    obs_mod.req("GetSceneList")
    mock_req.get_scene_list.assert_called_once_with()


def test_req_passes_kwargs_to_client_method(monkeypatch):
    mock_req = MagicMock()
    monkeypatch.setattr("server.obs_client.obs.ReqClient", lambda **kw: mock_req)
    monkeypatch.setattr("server.obs_client.obs.EventClient", lambda **kw: MagicMock())
    obs_mod.connect("localhost", 4455, "")

    obs_mod.req("SetCurrentProgramScene", scene_name="Gaming")
    mock_req.set_current_program_scene.assert_called_once_with(scene_name="Gaming")


def test_req_raises_attribute_error_for_unknown_method(monkeypatch):
    mock_req = MagicMock(spec=[])  # no attributes
    monkeypatch.setattr("server.obs_client.obs.ReqClient", lambda **kw: mock_req)
    monkeypatch.setattr("server.obs_client.obs.EventClient", lambda **kw: MagicMock())
    obs_mod.connect("localhost", 4455, "")

    with pytest.raises(AttributeError, match="Unknown OBS request"):
        obs_mod.req("NonExistentMethod")


# ---------------------------------------------------------------------------
# _to_snake()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pascal,snake", [
    ("GetSceneList",              "get_scene_list"),
    ("SetCurrentProgramScene",    "set_current_program_scene"),
    ("ToggleStream",              "toggle_stream"),
    ("GetInputVolumeDB",          "get_input_volume_db"),
    ("StudioModeStateChanged",    "studio_mode_state_changed"),
])
def test_to_snake_conversion(pascal, snake):
    assert obs_mod._to_snake(pascal) == snake


# ---------------------------------------------------------------------------
# Event handler registration
# ---------------------------------------------------------------------------

def test_on_event_decorator_registers_handler():
    results = []

    @obs_mod.on_event("TestEvent")
    def handler(data):
        results.append(data)

    assert "TestEvent" in obs_mod._event_handlers
    assert handler in obs_mod._event_handlers["TestEvent"]


def test_multiple_handlers_for_same_event_all_called(monkeypatch):
    called = []

    @obs_mod.on_event("TestEvent2")
    def h1(data): called.append("h1")

    @obs_mod.on_event("TestEvent2")
    def h2(data): called.append("h2")

    for fn in obs_mod._event_handlers["TestEvent2"]:
        fn(None)

    assert "h1" in called
    assert "h2" in called
