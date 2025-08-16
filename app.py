from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import tempfile, os, subprocess, shutil, uuid

app = FastAPI(title="LLM Shorts")

def run(cmd: list[str]):
    print(">>>", " ".join(cmd), flush=True)
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if res.returncode != 0:
        print(res.stdout)
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{res.stdout}")
    return res.stdout

@app.get("/healthz")
async def healthz():
    return {"ok": True}

@app.post("/process")
async def process(
    url: str = Form(...),
    range: str | None = Form(None),
    ranges: str | None = Form(None),
    llm: str = Form("on"),
    vision_model: str = Form("gpt-4o-mini"),
    cookies_text: str | None = Form(None),
    out_name: str = Form("final.mp4"),
    cache: str = Form("/tmp/yt_cache"),
    bg: UploadFile = File(...),
):
    if not range and not ranges:
        raise HTTPException(400, "Provide 'range' or 'ranges'")

    work = tempfile.mkdtemp(prefix="api_")
    try:
        # save bg to file
        bg_path = os.path.join(work, bg.filename or "bg.bin")
        with open(bg_path, "wb") as f:
            shutil.copyfileobj(bg.file, f)

        # optional cookies file (for age-restricted videos)
        cookies_path = None
        if cookies_text:
            cookies_path = os.path.join(work, "cookies.txt")
            with open(cookies_path, "w") as f:
                f.write(cookies_text)

        out_path = os.path.join(work, out_name)

        cmd = ["python", "auto_short_llm_cache.py",
               "--url", url,
               "--bg", bg_path,
               "--out", out_path,
               "--cache", cache,
               "--llm", llm,
               "--vision_model", vision_model]
        if range:
            cmd += ["--range", range]
        if ranges:
            cmd += ["--ranges", ranges]
        if cookies_path:
            cmd += ["--cookies", cookies_path]

        run(cmd)

        if not os.path.exists(out_path):
            raise HTTPException(500, "Output not created")

        return FileResponse(out_path, media_type="video/mp4", filename=out_name)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        # keep workdir if you want debugging
        pass
