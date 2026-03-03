"""
Tests for server.config — load, save, defaults, set_value.

All tests redirect config I/O to a temporary directory via monkeypatching
so they never touch the real ProgramData/OBSRemote/config.json.
"""

import json
import pytest
import server.config as cfg_module


@pytest.fixture(autouse=True)
def tmp_config(tmp_path, monkeypatch):
    """Redirect all config I/O to a per-test temporary directory."""
    monkeypatch.setattr(cfg_module, "_APPDATA", tmp_path)
    monkeypatch.setattr(cfg_module, "_CONFIG_FILE", tmp_path / "config.json")


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------

def test_load_returns_all_default_keys_when_no_file_exists():
    cfg = cfg_module.load()
    assert cfg["obs_host"] == "localhost"
    assert cfg["obs_port"] == 4455
    assert cfg["obs_password"] == ""
    assert cfg["server_port"] == 42069
    assert cfg["check_updates"] is True
    assert "github_repo" in cfg


def test_load_creates_config_file_on_first_run(tmp_path):
    cfg_module.load()
    assert (tmp_path / "config.json").exists()


def test_load_parses_written_file_correctly(tmp_path):
    data = {
        "obs_host": "192.168.1.6",
        "obs_port": 4455,
        "obs_password": "s3cr3t",
        "server_port": 8080,
        "check_updates": False,
        "github_repo": "test/repo",
    }
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    cfg = cfg_module.load()
    assert cfg["obs_host"] == "192.168.1.6"
    assert cfg["server_port"] == 8080
    assert cfg["obs_password"] == "s3cr3t"
    assert cfg["check_updates"] is False


def test_load_backfills_missing_keys_from_defaults(tmp_path):
    """A partial config gets missing keys filled in from defaults."""
    partial = {"obs_host": "192.168.1.99", "obs_port": 4455}
    (tmp_path / "config.json").write_text(json.dumps(partial), encoding="utf-8")

    cfg = cfg_module.load()
    assert cfg["obs_host"] == "192.168.1.99"       # preserved
    assert cfg["server_port"] == 42069              # backfilled
    assert cfg["check_updates"] is True             # backfilled
    assert cfg["obs_password"] == ""                # backfilled


def test_load_backfill_writes_updated_config_to_disk(tmp_path):
    """When keys are backfilled they are also persisted."""
    partial = {"obs_host": "10.0.0.1"}
    (tmp_path / "config.json").write_text(json.dumps(partial), encoding="utf-8")

    cfg_module.load()

    on_disk = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert "server_port" in on_disk


# ---------------------------------------------------------------------------
# save()
# ---------------------------------------------------------------------------

def test_save_writes_valid_json(tmp_path):
    data = {"obs_host": "10.0.0.1", "obs_port": 4455}
    cfg_module.save(data)
    raw = (tmp_path / "config.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["obs_host"] == "10.0.0.1"


def test_save_creates_directory_if_missing(tmp_path, monkeypatch):
    nested = tmp_path / "a" / "b" / "OBSRemote"
    monkeypatch.setattr(cfg_module, "_APPDATA", nested)
    monkeypatch.setattr(cfg_module, "_CONFIG_FILE", nested / "config.json")

    cfg_module.save({"obs_host": "localhost"})
    assert (nested / "config.json").exists()


# ---------------------------------------------------------------------------
# set_value()
# ---------------------------------------------------------------------------

def test_set_value_updates_single_key():
    cfg_module.load()  # ensure defaults exist on disk
    cfg_module.set_value("obs_host", "10.0.0.1")
    updated = cfg_module.load()
    assert updated["obs_host"] == "10.0.0.1"


def test_set_value_preserves_other_keys():
    cfg_module.load()
    cfg_module.set_value("server_port", 9000)
    cfg = cfg_module.load()
    assert cfg["server_port"] == 9000
    assert cfg["obs_host"] == "localhost"   # default still intact
    assert cfg["obs_port"] == 4455          # default still intact


def test_set_value_can_overwrite_existing_key():
    cfg_module.load()
    cfg_module.set_value("obs_host", "first")
    cfg_module.set_value("obs_host", "second")
    assert cfg_module.load()["obs_host"] == "second"


def test_set_value_persists_across_fresh_load(tmp_path):
    cfg_module.set_value("obs_password", "hunter2")
    # Simulate a fresh load (new process reading the same file)
    on_disk = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert on_disk["obs_password"] == "hunter2"


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------

def test_get_returns_value_for_existing_key():
    cfg_module.load()
    assert cfg_module.get("obs_host") == "localhost"


def test_get_returns_default_for_unknown_key():
    cfg_module.load()
    assert cfg_module.get("nonexistent_key") is None
