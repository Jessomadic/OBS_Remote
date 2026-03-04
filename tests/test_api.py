"""
Integration tests for the FastAPI HTTP layer.

Uses FastAPI's TestClient (synchronous) with mocked OBS and updater
so no real OBS Studio instance is needed.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import server.config as cfg_module
import server.obs_client as obs_mod


@pytest.fixture(autouse=True)
def reset_obs_globals():
    """Reset obs_client globals between tests."""
    obs_mod._req_client = None
    obs_mod._event_client = None
    obs_mod._connected = False
    obs_mod._event_handlers.clear()
    yield
    obs_mod._req_client = None
    obs_mod._event_client = None
    obs_mod._connected = False
    obs_mod._event_handlers.clear()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """
    TestClient with:
    - Config redirected to a temp dir.
    - OBS connect/disconnect patched out (no real WebSocket needed).
    - Background updater patched out.
    """
    monkeypatch.setattr(cfg_module, "_APPDATA", tmp_path)
    monkeypatch.setattr(cfg_module, "_CONFIG_FILE", tmp_path / "config.json")

    with (
        patch("server.obs_client.connect"),
        patch("server.obs_client.disconnect"),
        patch("server.updater.start_background_checker"),
    ):
        from server.main import app
        with TestClient(app) as c:
            yield c


# ---------------------------------------------------------------------------
# GET /api/status
# ---------------------------------------------------------------------------

def test_status_200(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200


def test_status_contains_required_fields(client):
    resp = client.get("/api/status")
    data = resp.json()
    assert "version" in data
    assert "obs_connected" in data
    assert "obs_host" in data
    assert "obs_port" in data
    assert "server_port" in data


def test_status_obs_disconnected_by_default(client):
    with patch("server.obs_client.is_connected", return_value=False):
        resp = client.get("/api/status")
    assert resp.json()["obs_connected"] is False


def test_status_obs_connected_when_client_reports_connected(client):
    with patch("server.obs_client.is_connected", return_value=True):
        resp = client.get("/api/status")
    assert resp.json()["obs_connected"] is True


def test_status_reflects_config_obs_host(client, tmp_path):
    cfg_module.set_value("obs_host", "192.168.1.6")
    resp = client.get("/api/status")
    assert resp.json()["obs_host"] == "192.168.1.6"


def test_status_reflects_config_server_port(client):
    cfg_module.set_value("server_port", 9999)
    resp = client.get("/api/status")
    assert resp.json()["server_port"] == 9999


# ---------------------------------------------------------------------------
# POST /api/connect
# ---------------------------------------------------------------------------

def test_connect_returns_ok_true_on_success(client):
    with patch("server.obs_client.disconnect"), patch("server.obs_client.connect"):
        resp = client.post("/api/connect", json={"host": "localhost", "port": 4455, "password": ""})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_connect_saves_host_to_config(client):
    with patch("server.obs_client.disconnect"), patch("server.obs_client.connect"):
        client.post("/api/connect", json={"host": "192.168.1.6", "port": 4455, "password": ""})
    assert cfg_module.load()["obs_host"] == "192.168.1.6"


def test_connect_saves_port_to_config(client):
    with patch("server.obs_client.disconnect"), patch("server.obs_client.connect"):
        client.post("/api/connect", json={"host": "localhost", "port": 4456, "password": ""})
    assert cfg_module.load()["obs_port"] == 4456


def test_connect_saves_password_to_config(client):
    with patch("server.obs_client.disconnect"), patch("server.obs_client.connect"):
        client.post("/api/connect", json={"host": "localhost", "port": 4455, "password": "hunter2"})
    assert cfg_module.load()["obs_password"] == "hunter2"


def test_connect_calls_disconnect_first(client):
    with patch("server.obs_client.disconnect") as mock_disc, patch("server.obs_client.connect"):
        client.post("/api/connect", json={"host": "localhost", "port": 4455, "password": ""})
    mock_disc.assert_called_once()


def test_connect_calls_obs_connect_with_new_host(client):
    with patch("server.obs_client.disconnect"), patch("server.obs_client.connect") as mock_conn:
        client.post("/api/connect", json={"host": "192.168.1.6", "port": 4455, "password": ""})
    mock_conn.assert_called_once_with("192.168.1.6", 4455, "")


def test_connect_returns_ok_false_on_obs_failure(client):
    with (
        patch("server.obs_client.disconnect"),
        patch("server.obs_client.connect", side_effect=ConnectionRefusedError("refused")),
    ):
        resp = client.post("/api/connect", json={"host": "bad_host", "port": 9999, "password": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["connected"] is False
    assert "error" in data


# ---------------------------------------------------------------------------
# POST /api/disconnect
# ---------------------------------------------------------------------------

def test_disconnect_returns_ok(client):
    with patch("server.obs_client.disconnect") as mock_disc:
        resp = client.post("/api/disconnect")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    mock_disc.assert_called_once()


# ---------------------------------------------------------------------------
# GET /api/scenes
# ---------------------------------------------------------------------------

def test_scenes_503_when_not_connected(client):
    with patch("server.obs_client.req", side_effect=RuntimeError("Not connected to OBS")):
        resp = client.get("/api/scenes")
    assert resp.status_code == 503


def test_scenes_returns_list_and_current(client):
    mock_list = MagicMock()
    mock_list.scenes = [{"sceneName": "Scene 1"}, {"sceneName": "Scene 2"}]
    mock_current = MagicMock()
    mock_current.current_program_scene_name = "Scene 1"

    def fake_req(method, **kw):
        if method == "GetSceneList":
            return mock_list
        if method == "GetCurrentProgramScene":
            return mock_current

    with patch("server.obs_client.req", side_effect=fake_req):
        resp = client.get("/api/scenes")

    assert resp.status_code == 200
    data = resp.json()
    assert set(data["scenes"]) == {"Scene 1", "Scene 2"}
    assert data["current"] == "Scene 1"


def test_set_scene_calls_obs(client):
    with patch("server.obs_client.req") as mock_req:
        resp = client.post("/api/scenes/current", json={"scene_name": "Gaming"})
    assert resp.status_code == 200
    mock_req.assert_called_once_with("SetCurrentProgramScene", name="Gaming")


def test_set_scene_503_when_obs_fails(client):
    with patch("server.obs_client.req", side_effect=RuntimeError("Not connected")):
        resp = client.post("/api/scenes/current", json={"scene_name": "Gaming"})
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# POST /api/update/check
# ---------------------------------------------------------------------------

def test_update_check_returns_no_update(client):
    with patch("server.updater.check_now", return_value=None):
        resp = client.post("/api/update/check")
    assert resp.status_code == 200
    assert resp.json()["update_found"] is False


def test_update_check_returns_update_info(client):
    info = {"version": "2.0.0", "current": "1.0.3", "url": "http://example.com/setup.exe"}
    with (
        patch("server.updater.check_now", return_value=info),
        patch("server.updater.download_and_apply") as mock_dl,
    ):
        resp = client.post("/api/update/check")
    assert resp.json()["update_found"] is True
    assert resp.json()["version"] == "2.0.0"
    mock_dl.assert_called_once_with(info)


# ---------------------------------------------------------------------------
# WebSocket /ws
# ---------------------------------------------------------------------------

def test_websocket_sends_connected_event_on_connect(client):
    import json as _json
    with client.websocket_connect("/ws") as ws:
        msg = _json.loads(ws.receive_text())
    assert msg["event"] == "connected"
    assert "version" in msg["data"]
    assert "obs_connected" in msg["data"]


def test_websocket_responds_to_ping(client):
    import json as _json
    with client.websocket_connect("/ws") as ws:
        ws.receive_text()  # consume "connected" event
        ws.send_text("ping")
        msg = _json.loads(ws.receive_text())
    assert msg["event"] == "pong"
