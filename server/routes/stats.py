"""OBS stats route."""

from fastapi import APIRouter, HTTPException

from server import obs_client as obs

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def get_stats():
    try:
        resp = obs.req("GetStats")
        stream = obs.req("GetStreamStatus")
        record = obs.req("GetRecordStatus")
        return {
            "cpu_usage": round(resp.cpu_usage, 1),
            "memory_usage": round(resp.memory_usage, 1),
            "available_disk_space": round(resp.available_disk_space, 1),
            "active_fps": round(resp.active_fps, 2),
            "average_frame_render_time": round(resp.average_frame_render_time, 2),
            "render_skipped_frames": resp.render_skipped_frames,
            "render_total_frames": resp.render_total_frames,
            "output_skipped_frames": resp.output_skipped_frames,
            "output_total_frames": resp.output_total_frames,
            "stream_active": stream.output_active,
            "stream_timecode": stream.output_timecode,
            "stream_congestion": stream.output_congestion,
            "stream_bytes": stream.output_bytes,
            "record_active": record.output_active,
            "record_paused": record.output_paused,
            "record_timecode": record.output_timecode,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
