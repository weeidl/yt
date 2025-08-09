# yt-clipper (YouTube link + timecodes → clipped MP4)

Minimal service that accepts a YouTube URL and `start`/`end` timecodes, cuts the segment using `yt-dlp` (with ffmpeg), and returns an MP4.

## API

- `GET /` → health json
- `POST /cut` (JSON):

```json
{
  "url": "https://www.youtube.com/watch?v=XXXX",
  "start": "00:18:41",
  "end": "00:18:59",
  "filename": "my_clip",
  "cookies_txt": null
}
```

Returns the MP4 file directly.

## Local run (Docker)

```bash
docker build -t yt-clipper .
docker run --rm -p 8000:8000 yt-clipper
# test
curl -X POST http://localhost:8000/cut \
  -H "Content-Type: application/json" \
  -d '{"url":"<YOUTUBE_URL>", "start":"00:00:05", "end":"00:00:08"}' \
  --output clip.mp4
```

## Deploy: Railway (recommended)

1. Push these files to a Git repo (or upload directly in Railway).
2. Create **New Project → Deploy from Repo** (or **From Dockerfile**).
3. Railway will build the Dockerfile. No special settings needed.
4. Ensure the service listens on `$PORT` (already handled in Docker CMD).
5. After deploy, open the public URL and call `POST /cut`.

## Deploy: Render

1. Connect repo → **New Web Service**.
2. Build Command: `docker build -t app .` (or use Render’s native Docker)
3. Start Command: handled by Docker `CMD`.
4. Exposes port `$PORT` (Render injects it; Docker CMD uses it).

Notes:
- Outputs are streamed back; no persistent storage required.
- If a video requires cookies, send them via `cookies_txt` (netscape format).
- Respect YouTube Terms. Use only your own content or with permission.
