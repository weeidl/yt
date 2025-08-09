# yt-clipper v1.1

Cuts a YouTube clip by timecodes and returns MP4. Uses yt-dlp + ffmpeg.
Supports multiple cookie inputs for authorized videos.

## API

**POST /cut**
Body:
```json
{
  "url": "https://www.youtube.com/watch?v=XXXX",
  "start": "00:18:41",
  "end": "00:18:59",
  "filename": "my_clip",
  "cookies_txt": null,
  "cookies_b64": null,
  "cookies_url": null,
  "cookies_env": null
}
```
- Time format: `MM:SS` or `HH:MM:SS`.
- Cookies priority: `cookies_txt` > `cookies_b64` > `cookies_url` > env var (`cookies_env` or `YTDLP_COOKIES_B64`).

### Env var cookies (recommended on Render/Railway)
Base64-encode your `cookies.txt` and put it into `YTDLP_COOKIES_B64` env var.
```bash
base64 -i cookies.txt | pbcopy
```
Then deploy. The service will decode it if no cookies were provided in request body.

## Docker
```bash
docker build -t yt-clipper .
docker run --rm -p 8000:8000 -e YTDLP_COOKIES_B64="$YTDLP_COOKIES_B64" yt-clipper
```

## Notes
- Prefers H.264/AAC and remuxes to mp4 to avoid WebM issues:
  `-f "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4]/best" --remux-video mp4`
- Use only for your own content or with permission; respect YouTube ToS.
