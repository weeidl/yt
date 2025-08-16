import os, tempfile, subprocess, shutil
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse, PlainTextResponse, JSONResponse
from typing import Optional

app = FastAPI(title="LLM Shorts", version="1.0")

@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/process")
async def process(
    url: str = Form(...),
    range: Optional[str] = Form(None),
    ranges: Optional[str] = Form(None),
    llm: str = Form("on"),
    vision_model: str = Form("gpt-4o-mini"),
    cache: str = Form("/tmp/yt_cache"),
    cookies_text: Optional[str] = Form(None),
    cookies_from_browser: Optional[str] = Form(None),
    bg: UploadFile = File(...),
    out_name: str = Form("final.mp4"),
):
    if not range and not ranges:
        return PlainTextResponse("Provide 'range' or 'ranges'.", status_code=400)

    workdir = tempfile.mkdtemp(prefix="api_work_")
    try:
        # Save background
        bg_path = os.path.join(workdir, bg.filename or "bg.bin")
        with open(bg_path, "wb") as f:
            f.write(await bg.read())

        # Optional cookies from text (Netscape format)
        cookies_path = None
        if cookies_text:
            cookies_path = os.path.join(workdir, "cookies.txt")
            with open(cookies_path, "w") as f:
                f.write(cookies_text)

        # Output path
        out_path = os.path.join(workdir, out_name)

        # Ensure cache dir
        os.makedirs(cache, exist_ok=True)

        cmd = [
            os.sys.executable, "auto_short_llm_cache.py",
            "--url", url,
            "--bg", bg_path,
            "--out", out_path,
            "--cache", cache,
            "--llm", llm,
            "--vision_model", vision_model,
        ]
        if range:
            cmd += ["--range", range]
        if ranges:
            cmd += ["--ranges", ranges]
        if cookies_path:
            cmd += ["--cookies", cookies_path]
        if cookies_from_browser:
            cmd += ["--cookies-from-browser", cookies_from_browser]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.exists(out_path):
            return PlainTextResponse(proc.stdout + "\n" + proc.stderr, status_code=500)

        def file_iterator(path):
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    yield chunk

        headers = {"Content-Disposition": f'attachment; filename="{os.path.basename(out_path)}"'}
        return StreamingResponse(file_iterator(out_path), media_type="video/mp4", headers=headers)
    finally:
        # keep cache directory
        pass
