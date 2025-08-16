# Railway LLM Shorts

FastAPI wrapper around `auto_short_llm_cache.py`

## Deploy
- Create a Docker service on Railway.
- Set env `OPENAI_API_KEY` if using LLM watermark/panel detection.
- Deploy this directory.

## API
`POST /process` (multipart/form-data)

Fields:
- `url` (str) — YouTube URL
- `range` (str) OR `ranges` (str)
- `bg` (file) — 9:16 image/video background
- `llm` (on|off), default on
- `vision_model` (str), default gpt-4o-mini
- `cookies_text` (str) — optional Netscape cookie.txt content
- `out_name` (str), default final.mp4
- `cache` (str), default /tmp/yt_cache

Example:
```bash
curl -X POST "https://<host>/process"   -F 'url=https://www.youtube.com/watch?v=XXXXXXXXXXX'   -F 'range=00:01:00-00:02:00'   -F 'llm=on'   -F 'bg=@test_video.mp4'   --output result.mp4
```
