"""Scene and scene-collection routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server import obs_client as obs

router = APIRouter(prefix="/api/scenes", tags=["scenes"])


class SetSceneRequest(BaseModel):
    scene_name: str


class SetCollectionRequest(BaseModel):
    collection_name: str


@router.get("")
def get_scenes():
    try:
        resp = obs.req("GetSceneList")
        current = obs.req("GetCurrentProgramScene")
        return {
            "scenes": [s["sceneName"] for s in reversed(resp.scenes)],
            "current": current.current_program_scene_name,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/current")
def set_scene(body: SetSceneRequest):
    try:
        obs.req("SetCurrentProgramScene", scene_name=body.scene_name)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/collections")
def get_collections():
    try:
        resp = obs.req("GetSceneCollectionList")
        return {
            "collections": resp.scene_collections,
            "current": resp.current_scene_collection_name,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/collections/current")
def set_collection(body: SetCollectionRequest):
    try:
        obs.req("SetCurrentSceneCollection", scene_collection_name=body.collection_name)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
