"""Stream and recording control routes."""

from fastapi import APIRouter, HTTPException

from server import obs_client as obs

router = APIRouter(prefix="/api/streaming", tags=["streaming"])


@router.get("/status")
def get_status():
    try:
        stream = obs.req("GetStreamStatus")
        record = obs.req("GetRecordStatus")
        return {
            "stream": {
                "active": stream.output_active,
                "reconnecting": stream.output_reconnecting,
                "timecode": stream.output_timecode,
                "duration": stream.output_duration,
                "congestion": stream.output_congestion,
                "bytes": stream.output_bytes,
                "skipped_frames": stream.output_skipped_frames,
                "total_frames": stream.output_total_frames,
            },
            "record": {
                "active": record.output_active,
                "paused": record.output_paused,
                "timecode": record.output_timecode,
                "duration": record.output_duration,
                "bytes": record.output_bytes,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/stream/start")
def start_stream():
    try:
        obs.req("StartStream")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/stream/stop")
def stop_stream():
    try:
        obs.req("StopStream")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/stream/toggle")
def toggle_stream():
    try:
        obs.req("ToggleStream")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/record/start")
def start_record():
    try:
        obs.req("StartRecord")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/record/stop")
def stop_record():
    try:
        obs.req("StopRecord")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/record/toggle")
def toggle_record():
    try:
        obs.req("ToggleRecord")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/record/pause")
def pause_record():
    try:
        obs.req("PauseRecord")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/record/resume")
def resume_record():
    try:
        obs.req("ResumeRecord")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/virtualcam/toggle")
def toggle_virtualcam():
    try:
        obs.req("ToggleVirtualCam")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/replay/toggle")
def toggle_replay():
    try:
        obs.req("ToggleReplayBuffer")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/replay/save")
def save_replay():
    try:
        obs.req("SaveReplayBuffer")
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
