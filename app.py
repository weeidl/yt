from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import tempfile, subprocess, os, uuid, glob, base64 as _b64, gzip, re
from typing import Optional
import requests

app = FastAPI(title="yt-clipper", version="1.2.0")

class CutReq(BaseModel):
    url: str = Field(..., description="YouTube link")
    start: str = Field(..., description="Start time (HH:MM:SS or MM:SS)")
    end: str = Field(..., description="End time (HH:MM:SS or MM:SS)")
    filename: Optional[str] = Field(default=None, description="Base filename without extension")
    cookies_txt: Optional[str] = Field(default=None, description="Netscape cookies.txt content")
    cookies_b64: Optional[str] = Field(default=None, description="Base64-encoded cookies.txt (plain or gzipped if cookies_b64_gzip=true)")
    cookies_b64_gzip: Optional[bool] = Field(default=None, description="Set true if cookies_b64 is gzip-compressed base64")
    cookies_url: Optional[str] = Field(default=None, description="URL to cookies.txt (https://...)")
    cookies_env: Optional[str] = Field(default=None, description="Env var name with base64 cookies; if not set, will try YTDLP_COOKIES_B64 or chunks YTDLP_COOKIES_B64_PART_*")

def _norm_time(t: str) -> str:
    t = t.strip()
    parts = t.split(":")
    if len(parts) == 2:
        hh, mm, ss = "00", parts[0], parts[1]
    elif len(parts) == 3:
        hh, mm, ss = parts
    else:
        raise ValueError("time must be MM:SS or HH:MM:SS")
    return f"{int(hh):02d}:{int(mm):02d}:{int(ss):02d}"

def _read_env_chunked(prefix: str):
    single = os.getenv(prefix)
    if single:
        return single
    pattern = re.compile(rf"^{re.escape(prefix)}_PART_(\d+)$")
    chunks = []
    for k, v in os.environ.items():
        m = pattern.match(k)
        if m and v:
            chunks.append((int(m.group(1)), v))
    if not chunks and prefix != "YTDLP_COOKIES_B64":
        return _read_env_chunked("YTDLP_COOKIES_B64")
    chunks.sort(key=lambda x: x[0])
    return "".join(v for _, v in chunks) if chunks else None

def _maybe_decode_base64(data_b64: str, gzipped_flag: Optional[bool] = None) -> bytes:
    raw = _b64.b64decode(data_b64)
    if gzipped_flag is True or (gzipped_flag is None and len(raw) >= 2 and raw[0] == 0x1f and raw[1] == 0x8b):
        try:
            import gzip as _gz
            return _gz.decompress(raw)
        except Exception:
            return raw
    return raw

def _prepare_cookies(tmpdir: str, req: CutReq):
    content = None
    if req.cookies_txt:
        content = req.cookies_txt.encode("utf-8")
    elif req.cookies_b64:
        try:
            content = _maybe_decode_base64(req.cookies_b64, req.cookies_b64_gzip)
        except Exception as e:
            raise HTTPException(400, f"cookies_b64 decode error: {e}")
    elif req.cookies_url:
        try:
            r = requests.get(req.cookies_url, timeout=15)
            r.raise_for_status()
            content = r.content
        except Exception as e:
            raise HTTPException(400, f"cookies_url fetch error: {e}")
    else:
        env_name = req.cookies_env or "YTDLP_COOKIES_B64"
        data_b64 = _read_env_chunked(env_name)
        if data_b64:
            try:
                content = _maybe_decode_base64(data_b64, None)
            except Exception as e:
                raise HTTPException(400, f"{env_name} base64 decode error: {e}")
    if not content:
        return None
    cpath = os.path.join(tmpdir, "cookies.txt")
    with open(cpath, "wb") as f:
        f.write(content)
    return cpath

@app.get("/")
def root():
    return {"ok": True, "service": "yt-clipper", "version": "1.2.0"}

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

        cookies_arg = []
        cookies_path = _prepare_cookies(td, req)
        if cookies_path:
            cookies_arg = ["--cookies", cookies_path]

        cmd = [
            "yt-dlp", req.url,
            *cookies_arg,
            "--no-playlist",
            "-f", "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4]/best",
            "--remux-video", "mp4",
            "--download-sections", f"*{start}-{end}",
            "-o", out_tpl,
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            err = (res.stderr or res.stdout or "").strip()
            err_tail = err[-6000:]
            raise HTTPException(400, f"yt-dlp error:\n{err_tail}")

        files = glob.glob(os.path.join(td, base + ".*"))
        if not files:
            raise HTTPException(500, "file not created")
        path = files[0]
        return FileResponse(path, filename=os.path.basename(path), media_type="video/mp4")
