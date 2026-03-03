"""Source filter routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server import obs_client as obs

router = APIRouter(prefix="/api/filters", tags=["filters"])


class SetFilterEnabledRequest(BaseModel):
    source_name: str
    filter_name: str
    enabled: bool


@router.get("/{source_name}")
def get_filters(source_name: str):
    """Get all filters on a source."""
    try:
        resp = obs.req("GetSourceFilterList", source_name=source_name)
        filters = []
        for f in resp.filters:
            filters.append({
                "name": f["filterName"],
                "kind": f["filterKind"],
                "enabled": f["filterEnabled"],
                "index": f["filterIndex"],
            })
        filters.sort(key=lambda x: x["index"])
        return {"filters": filters}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/enabled")
def set_filter_enabled(body: SetFilterEnabledRequest):
    try:
        obs.req(
            "SetSourceFilterEnabled",
            source_name=body.source_name,
            filter_name=body.filter_name,
            filter_enabled=body.enabled,
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
