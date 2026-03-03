"""Source visibility routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server import obs_client as obs

router = APIRouter(prefix="/api/sources", tags=["sources"])


class SetVisibilityRequest(BaseModel):
    scene_name: str
    scene_item_id: int
    enabled: bool


@router.get("/{scene_name}")
def get_sources(scene_name: str):
    """Get all sources (scene items) in a scene with visibility state."""
    try:
        resp = obs.req("GetSceneItemList", scene_name=scene_name)
        items = []
        for item in resp.scene_items:
            items.append({
                "id": item["sceneItemId"],
                "index": item["sceneItemIndex"],
                "name": item["sourceName"],
                "kind": item.get("inputKind") or item.get("sourceType", ""),
                "enabled": item["sceneItemEnabled"],
                "locked": item.get("sceneItemLocked", False),
                "blend_mode": item.get("blendMode", "OBS_BLEND_NORMAL"),
            })
        # Sort by index (top of stack first)
        items.sort(key=lambda x: x["index"], reverse=True)
        return {"sources": items}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/visibility")
def set_visibility(body: SetVisibilityRequest):
    try:
        obs.req(
            "SetSceneItemEnabled",
            scene_name=body.scene_name,
            scene_item_id=body.scene_item_id,
            scene_item_enabled=body.enabled,
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
