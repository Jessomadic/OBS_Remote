"""Audio mixer routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server import obs_client as obs

router = APIRouter(prefix="/api/audio", tags=["audio"])


class SetVolumeRequest(BaseModel):
    input_name: str
    volume_db: float  # dB (-100 to 26)


class SetMuteRequest(BaseModel):
    input_name: str
    muted: bool


class SetMonitorRequest(BaseModel):
    input_name: str
    monitor_type: str  # "OBS_MONITORING_TYPE_NONE" | "OBS_MONITORING_TYPE_MONITOR_ONLY" | "OBS_MONITORING_TYPE_MONITOR_AND_OUTPUT"


@router.get("")
def get_inputs():
    """Return all audio inputs with volume and mute state."""
    try:
        inputs_resp = obs.req("GetInputList")
        result = []
        for inp in inputs_resp.inputs:
            name = inp["inputName"]
            kind = inp.get("inputKind", "")
            # Only include audio-capable inputs
            audio_kinds = {
                "wasapi_input_capture", "wasapi_output_capture",
                "dshow_input", "coreaudio_input_capture", "coreaudio_output_capture",
                "pulse_input_capture", "pulse_output_capture",
                "alsa_input_capture", "browser_source", "ffmpeg_source",
                "vlc_source", "mediasource",
            }
            try:
                vol_resp = obs.req("GetInputVolume", name=name)
                mute_resp = obs.req("GetInputMute", name=name)
                result.append({
                    "name": name,
                    "kind": kind,
                    "volume_db": round(vol_resp.input_volume_db, 1),
                    "volume_mul": vol_resp.input_volume_mul,
                    "muted": mute_resp.input_muted,
                })
            except Exception:
                # Source may not support audio
                continue
        return {"inputs": result}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/volume")
def set_volume(body: SetVolumeRequest):
    if not -100.0 <= body.volume_db <= 26.0:
        raise HTTPException(status_code=400, detail="volume_db must be between -100 and 26")
    try:
        obs.req("SetInputVolume", name=body.input_name, vol_db=body.volume_db)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/mute")
def set_mute(body: SetMuteRequest):
    try:
        obs.req("SetInputMute", name=body.input_name, muted=body.muted)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/mute/toggle")
def toggle_mute(body: SetMuteRequest):
    try:
        obs.req("ToggleInputMute", name=body.input_name)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
