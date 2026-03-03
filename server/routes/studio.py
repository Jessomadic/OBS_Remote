"""Studio mode routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server import obs_client as obs

router = APIRouter(prefix="/api/studio", tags=["studio"])


class SetPreviewSceneRequest(BaseModel):
    scene_name: str


@router.get("")
def get_studio_status():
    try:
        studio_resp = obs.req("GetStudioModeEnabled")
        result = {"enabled": studio_resp.studio_mode_enabled}
        if studio_resp.studio_mode_enabled:
            preview_resp = obs.req("GetCurrentPreviewScene")
            result["preview_scene"] = preview_resp.current_preview_scene_name
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/toggle")
def toggle_studio():
    try:
        current = obs.req("GetStudioModeEnabled")
        obs.req("SetStudioModeEnabled", studio_mode_enabled=not current.studio_mode_enabled)
        return {"enabled": not current.studio_mode_enabled}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/preview")
def set_preview(body: SetPreviewSceneRequest):
    try:
        obs.req("SetCurrentPreviewScene", scene_name=body.scene_name)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/transition")
def trigger_transition():
    """Trigger the studio mode transition (cut to program)."""
    try:
        obs.req("TriggerStudioModeTransition")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
