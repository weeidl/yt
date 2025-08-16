# LLM Shorts (Railway)

Small FastAPI wrapper around `auto_short_llm_cache.py` to run on Railway.

## Deploy
- Create a new **Docker** service on Railway and upload this ZIP.
- Set env var `OPENAI_API_KEY` if you want LLM-based detection.
- The service listens on `$PORT` (Railway will inject).

## API
`POST /process` (multipart/form-data)

Fields:
- `url` – YouTube URL
- `range` OR `ranges` – e.g. `00:01:00-00:02:00` or `00:10:00-00:10:20,00:12:00-00:12:10`
- `bg` – file (image or video, 9:16 recommended)
- `llm` – `on`/`off` (default `on`)
- `vision_model` – default `gpt-4o-mini`
- `cookies_text` – optional Netscape cookie.txt pasted content (for age-restricted)
- `cookies_from_browser` – optional (rarely works in server envs)
- `out_name` – optional filename, default `final.mp4`
- `cache` – optional path, default `/tmp/yt_cache`

### Example (curl)
```bash
curl -X POST "https://<your-railway-domain>/process" \
  -F 'url=https://www.youtube.com/watch?v=XXXXXXXXXXX' \
  -F 'range=00:01:00-00:02:00' \
  -F 'llm=on' \
  -F 'bg=@test_video.mp4' \
  --output result.mp4
```

## Notes
- Requires `ffmpeg` (Dockerfile installs it).
- If the video is age-restricted, pass cookies via `cookies_text` in Netscape format.
- Caching is stored under `/tmp/yt_cache` by default.
```
