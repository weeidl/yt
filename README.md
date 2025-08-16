# yt-shorts-service

FastAPI wrapper around `auto_short_llm_cache.py` for Railway.

## Deploy (Dockerfile)
Just push to Railway. It will build the Dockerfile.

Required system deps are installed in the image (ffmpeg).

## Runtime env
- `OPENAI_API_KEY` (optional). If missing, watermark detection is skipped.
- `CACHE_DIR` (optional, default `/tmp/yt_cache`).

## Health
```
GET /health
```

## Process
```
curl -X POST "$HOST/process"   -F "url=https://www.youtube.com/watch?v=wpIS02IrZ54"   -F "range=00:16:08-00:16:53"   -F "llm=on"   -F "bg=@/path/to/bg.mp4;type=video/mp4"   --output result.mp4
```

