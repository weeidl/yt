import os, tempfile, shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from auto_short_llm_cache import (
    ensure_has, parse_ranges, download_clip_by_ranges,
    ffprobe_duration, sample_random_frame, llm_detect_boxes,
    compose_with_boxes, compose_simple
)

app = FastAPI(title="yt-shorts-service")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/process")
async def process(
    url: str = Form(...),
    range: str = Form(...),
    llm: str = Form("on"),
    cookies: str | None = Form(None),
    cookies_from_browser: str | None = Form(None),
    bg: UploadFile = File(...),
):
    try:
        ensure_has("ffmpeg"); ensure_has("ffprobe"); ensure_has("yt-dlp")
    except Exception as e:
        raise HTTPException(500, f"missing system dep: {e}")

    cache_dir = os.environ.get("CACHE_DIR", "/tmp/yt_cache")
    os.makedirs(cache_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        # save background
        bg_path = os.path.join(tmp, bg.filename or "bg.mp4")
        with open(bg_path, "wb") as f:
            shutil.copyfileobj(bg.file, f)

        out_path = os.path.join(tmp, "result.mp4")

        try:
            ranges = parse_ranges(range)
            clip = download_clip_by_ranges(
                url, ranges, tmp,
                cookies=cookies, cookies_from_browser=cookies_from_browser,
                cache_dir=cache_dir
            )

            if llm.lower() == "on":
                frame = os.path.join(tmp, "rnd.jpg")
                sample_random_frame(clip, frame)
                boxes = llm_detect_boxes(frame)
                compose_with_boxes(clip, bg_path, out_path, boxes)
            else:
                compose_simple(clip, bg_path, out_path)

            if not os.path.exists(out_path) or ffprobe_duration(out_path) < 0.1:
                raise RuntimeError("render failed")

            return FileResponse(out_path, media_type="video/mp4", filename="result.mp4")
        except HTTPException:
            raise
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
