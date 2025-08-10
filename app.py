import os, uuid, glob, re, logging, subprocess
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
import base64 as _b64

app = FastAPI(title="yt-clipper", version="1.2.1")

class CutReq(BaseModel):
    url: str = Field(..., description="YouTube link")
    start: str = Field(..., description="Start time (HH:MM:SS or MM:SS)")
    end: str = Field(..., description="End time (HH:MM:SS or MM:SS)")
    filename: Optional[str] = Field(default=None, description="Base filename without extension")
    cookies_txt: Optional[str] = Field(default=None, description="Netscape cookies.txt content")
    cookies_b64: Optional[str] = Field(default=None, description="Base64-encoded cookies.txt (plain or gzipped)")
    cookies_b64_gzip: Optional[bool] = Field(default=None, description="Set true if cookies_b64 is gzip-compressed base64")
    cookies_url: Optional[str] = Field(default=None, description="URL to cookies.txt (https://...)")
    cookies_env: Optional[str] = Field(default=None, description="Env var name with base64 cookies; if not set, tries YTDLP_COOKIES_B64 or chunks YTDLP_COOKIES_B64_PART_*")

class DebugYTReq(BaseModel):
    url: str
    cookies_txt: Optional[str] = None
    cookies_b64: Optional[str] = None
    cookies_b64_gzip: Optional[bool] = None
    cookies_url: Optional[str] = None
    cookies_env: Optional[str] = None

ESSENTIAL_COOKIE_NAMES = (
    "__Secure-3PSID","__Secure-3PSIDTS","__Secure-1PSID",
    "SAPISID","APISID","SID","HSID","SSID","SIDCC",
    "LOGIN_INFO","PREF","CONSENT","SOCS","VISITOR_INFO1_LIVE","YSC"
)

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

def _read_env_chunked(prefix: str) -> Optional[str]:
    single = os.getenv(prefix)
    if single:
        return single
    import re as _re
    pattern = _re.compile(rf"^{_re.escape(prefix)}_PART_(\d+)$")
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
            import gzip
            return gzip.decompress(raw)
        except Exception:
            return raw
    return raw

def _prepare_cookies(tmpdir: str, obj) -> Optional[str]:
    content: Optional[bytes] = None
    if getattr(obj, "cookies_txt", None):
        content = obj.cookies_txt.encode("utf-8")
    elif getattr(obj, "cookies_b64", None):
        try:
            content = _maybe_decode_base64(obj.cookies_b64, getattr(obj, "cookies_b64_gzip", None))
        except Exception as e:
            raise HTTPException(400, f"cookies_b64 decode error: {e}")
    elif getattr(obj, "cookies_url", None):
        try:
            r = requests.get(obj.cookies_url, timeout=15); r.raise_for_status()
            content = r.content
        except Exception as e:
            raise HTTPException(400, f"cookies_url fetch error: {e}")
    else:
        env_name = getattr(obj, "cookies_env", None) or "YTDLP_COOKIES_B64"
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

def _safe_base(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:128] or f"clip-{uuid.uuid4().hex[:8]}"

@app.exception_handler(Exception)
async def unhandled(request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": f"internal error: {type(exc).__name__}: {str(exc)[:200]}"})

@app.get("/")
def root():
    return {"ok": True, "service": "yt-clipper", "version": "1.2.1"}

@app.post("/cut")
def cut(req: CutReq):
    try:
        start = _norm_time(req.start); end = _norm_time(req.end)
    except ValueError as e:
        raise HTTPException(400, str(e))

    out_dir = "/tmp/ytclipper"
    os.makedirs(out_dir, exist_ok=True)

    base = _safe_base(req.filename or f"clip-{uuid.uuid4().hex}")
    out_tpl = os.path.join(out_dir, base + ".%(ext)s")

    cookies_path = _prepare_cookies(out_dir, req)
    cookies_arg = ["--cookies", cookies_path] if cookies_path else []

    cmd = [
        "yt-dlp", req.url, *cookies_arg,
        "--no-playlist",
        "-f", "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4]/best",
        "--remux-video", "mp4",
        "--download-sections", f"*{start}-{end}",
        "-o", out_tpl,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)

    if res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip()
        raise HTTPException(400, f"yt-dlp error:\n{err[-6000:]}")

    files = glob.glob(os.path.join(out_dir, base + ".*"))
    if not files:
        raise HTTPException(500, "file not created")

    path = files[0]
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        raise HTTPException(500, "empty file")

    def cleanup(p=path, c=cookies_path):
        try:
            if p and os.path.exists(p): os.remove(p)
        except Exception: pass
        try:
            if c and os.path.exists(c): os.remove(c)
        except Exception: pass

    return FileResponse(path, filename=os.path.basename(path), media_type="video/mp4", background=BackgroundTask(cleanup))

@app.post("/debug/yt")
def debug_yt(req: DebugYTReq):
    tmpd = "/tmp/ytclipper"; os.makedirs(tmpd, exist_ok=True)
    cpath = _prepare_cookies(tmpd, req)
    cookies_arg = ["--cookies", cpath] if cpath else []
    cmd = ["yt-dlp", req.url, *cookies_arg, "--print", "title", "--skip-download"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return {"exit_code": res.returncode, "stdout_tail": (res.stdout or "")[-2000:], "stderr_tail": (res.stderr or "")[-2000:], "used_cookies": bool(cookies_arg)}
