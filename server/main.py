"""
OBS Remote — FastAPI application entry point.

Serves:
  - REST API under /api/*
  - WebSocket event stream at /ws
  - Static web UI from /ui directory
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Set

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server import config, obs_client as obs
from server import updater
from server.routes import audio, filters, scenes, sources, stats, streaming, studio
from version import __version__

_LOG_DIR = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "OBSRemote"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            _LOG_DIR / "obs_remote.log",
            maxBytes=1024 * 1024,  # 1 MB
            backupCount=3,
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

_ws_clients: Set[WebSocket] = set()


async def broadcast(event: str, data: dict):
    """Broadcast a JSON event to all connected WebSocket clients."""
    message = json.dumps({"event": event, "data": data})
    dead = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


# ---------------------------------------------------------------------------
# OBS event → WebSocket bridge
# ---------------------------------------------------------------------------

def _register_obs_events(loop: asyncio.AbstractEventLoop):
    """Register OBS event handlers that forward events to WebSocket clients."""

    def emit(event: str, data: dict):
        asyncio.run_coroutine_threadsafe(broadcast(event, data), loop)

    @obs.on_event("CurrentProgramSceneChanged")
    def on_scene_changed(d):
        emit("scene_changed", {"scene": d.scene_name})

    @obs.on_event("CurrentPreviewSceneChanged")
    def on_preview_changed(d):
        emit("preview_changed", {"scene": d.scene_name})

    @obs.on_event("StreamStateChanged")
    def on_stream_state(d):
        emit("stream_state", {"active": d.output_active, "state": d.output_state})

    @obs.on_event("RecordStateChanged")
    def on_record_state(d):
        emit("record_state", {"active": d.output_active, "state": d.output_state})

    @obs.on_event("InputVolumeChanged")
    def on_volume(d):
        emit("volume_changed", {"input": d.input_name, "db": d.input_volume_db, "mul": d.input_volume_mul})

    @obs.on_event("InputMuteStateChanged")
    def on_mute(d):
        emit("mute_changed", {"input": d.input_name, "muted": d.input_muted})

    @obs.on_event("SceneItemEnableStateChanged")
    def on_source_visibility(d):
        emit("source_visibility", {
            "scene": d.scene_name,
            "item_id": d.scene_item_id,
            "enabled": d.scene_item_enabled,
        })

    @obs.on_event("StudioModeStateChanged")
    def on_studio(d):
        emit("studio_mode", {"enabled": d.studio_mode_enabled})

    @obs.on_event("CurrentSceneCollectionChanged")
    def on_collection(d):
        emit("collection_changed", {"collection": d.scene_collection_name})

    @obs.on_event("SourceFilterEnableStateChanged")
    def on_filter(d):
        emit("filter_changed", {
            "source": d.source_name,
            "filter": d.filter_name,
            "enabled": d.filter_enabled,
        })


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    cfg = config.load()

    # Connect to OBS
    try:
        obs.connect(cfg["obs_host"], cfg["obs_port"], cfg["obs_password"])
        _register_obs_events(loop)
        logger.info("OBS connected")
    except Exception as e:
        logger.warning("OBS not available on startup: %s", e)

    # Start auto-updater
    if cfg.get("check_updates", True):
        updater.start_background_checker()

    yield

    obs.disconnect()
    logger.info("OBS Remote shutdown complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    # Running in a PyInstaller bundle
    UI_DIR = Path(sys._MEIPASS) / "ui"
else:
    # Running in normal Python environment
    UI_DIR = Path(__file__).parent.parent / "ui"

app = FastAPI(title="OBS Remote", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(scenes.router)
app.include_router(audio.router)
app.include_router(streaming.router)
app.include_router(sources.router)
app.include_router(filters.router)
app.include_router(studio.router)
app.include_router(stats.router)


# ---------------------------------------------------------------------------
# Connection management endpoint
# ---------------------------------------------------------------------------

from fastapi import APIRouter
from pydantic import BaseModel

mgmt = APIRouter(prefix="/api", tags=["management"])


class ConnectRequest(BaseModel):
    host: str = "localhost"
    port: int = 4455
    password: str = ""


@mgmt.get("/status")
def get_status():
    cfg = config.load()
    update_info = updater.get_update_available()
    return {
        "version": __version__,
        "obs_connected": obs.is_connected(),
        "obs_host": cfg["obs_host"],
        "obs_port": cfg["obs_port"],
        "server_port": cfg["server_port"],
        "update_available": update_info,
    }


@mgmt.post("/connect")
def connect_obs(body: ConnectRequest):
    obs.disconnect()
    config.set_value("obs_host", body.host)
    config.set_value("obs_port", body.port)
    config.set_value("obs_password", body.password)
    try:
        obs.connect(body.host, body.port, body.password)
        return {"ok": True, "connected": True}
    except Exception as e:
        return {"ok": False, "connected": False, "error": str(e)}


@mgmt.post("/disconnect")
def disconnect_obs():
    obs.disconnect()
    return {"ok": True}


@mgmt.post("/update/check")
def trigger_update_check():
    """Manually trigger an update check and apply if found."""
    info = updater.check_now()
    if info:
        updater.download_and_apply(info)
        return {"update_found": True, "version": info["version"], "current": info["current"]}
    return {"update_found": False, "current": __version__}


app.include_router(mgmt)


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        # Send current status immediately on connect
        cfg = config.load()
        await ws.send_text(json.dumps({
            "event": "connected",
            "data": {"version": __version__, "obs_connected": obs.is_connected()}
        }))
        while True:
            # Keep alive — client may send pings
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_text(json.dumps({"event": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)


# ---------------------------------------------------------------------------
# Static UI — mount at root so relative paths in HTML (css/, js/) resolve correctly
# ---------------------------------------------------------------------------

if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")


# ---------------------------------------------------------------------------
# Entry point (direct run or service mode)
# ---------------------------------------------------------------------------

def run_server():
    cfg = config.load()
    port = cfg.get("server_port", 42069)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


if __name__ == "__main__":
    run_server()
