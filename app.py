from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
import tempfile, subprocess, os, uuid, glob, re

app = FastAPI(title="yt-clipper", version="1.0.0")

class CutReq(BaseModel):
    url: str = Field(..., description="YouTube link")
    start: str = Field(..., description="Start time (HH:MM:SS or MM:SS)")
    end: str = Field(..., description="End time (HH:MM:SS or MM:SS)")
    filename: str | None = Field(default=None, description="Base filename without extension")
    cookies_txt: str | None = Field(default=None, description="Optional cookies.txt content")

def _norm_time(t: str) -> str:
    t = t.strip()
    if not t:
        raise ValueError("empty time")
    parts = t.split(":")
    if len(parts) == 2:
        mm, ss = parts
        hh = "00"
    elif len(parts) == 3:
        hh, mm, ss = parts
    else:
        raise ValueError("time must be MM:SS or HH:MM:SS")
    hh = hh.zfill(2)
    mm = mm.zfill(2)
    ss = ss.zfill(2)
    return f"{hh}:{mm}:{ss}"

@app.get("/")
def root():
    return {"ok": True, "service": "yt-clipper"}

@app.post("/cut")
def cut(req: CutReq):
    try:
        start = _norm_time(req.start)
        end = _norm_time(req.end)
    except ValueError as e:
        raise HTTPException(400, str(e))

    with tempfile.TemporaryDirectory() as td:
        base = req.filename or f"clip-{uuid.uuid4().hex}"
        out_tpl = os.path.join(td, base + ".%(ext)s")

        # optional cookies.txt
        cookies_arg = []
        if req.cookies_txt:
            cpath = os.path.join(td, "cookies.txt")
            with open(cpath, "w", encoding="utf-8") as f:
                f.write(req.cookies_txt)
            cookies_arg = ["--cookies", cpath]

        cmd = [
            "yt-dlp", req.url,
            *cookies_arg,
            "--download-sections", f"*{start}-{end}",
            "--merge-output-format", "mp4",
            "--no-playlist",
            "-o", out_tpl,
        ]
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as e:
            raise HTTPException(400, f"yt-dlp error: {e}")

        files = glob.glob(os.path.join(td, base + ".*"))
        if not files:
            raise HTTPException(500, "file not created")
        path = files[0]
        fname = os.path.basename(path)
        return FileResponse(path, filename=fname, media_type="video/mp4")
