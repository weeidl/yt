# yt-clipper v1.2

**New:**
- ENV chunks: `YTDLP_COOKIES_B64_PART_1`, `_2`, ...
- Gzipped base64 cookies (`cookies_b64_gzip: true` or auto-detect)

## Chunks
```bash
base64 < cookies_min.txt > cookies.b64
split -b 24000 -d -a 2 cookies.b64 cookies_part_
# Vars on Railway/Render:
# YTDLP_COOKIES_B64_PART_1 = (cookies_part_00)
# YTDLP_COOKIES_B64_PART_2 = (cookies_part_01)
# Redeploy
```

## Gzip
```bash
gzip -c cookies_min.txt | base64 > cookies_gz.b64
# { "cookies_b64": "<...>", "cookies_b64_gzip": true }
```

## API
POST `/cut` JSON:
```json
{
  "url": "https://www.youtube.com/watch?v=XXXX",
  "start": "00:18:41",
  "end": "00:18:59",
  "filename": "my_clip",
  "cookies_b64": null,
  "cookies_b64_gzip": null,
  "cookies_txt": null,
  "cookies_url": null,
  "cookies_env": null
}
```
