from __future__ import annotations
import os, sys, re, json, argparse, tempfile, subprocess, shutil, random, hashlib, base64
from typing import List, Tuple, Optional

# ---------- utils ----------
def sh(cmd: List[str], check=True):
    print(">>>", " ".join(cmd))
    return subprocess.run(cmd, check=check)

def sh_out(cmd: List[str]) -> str:
    print(">>>", " ".join(cmd))
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode("utf-8", "ignore")

def ensure_has(bin_name: str):
    if shutil.which(bin_name) is None:
        raise RuntimeError(f"'{bin_name}' не найден в PATH")
    flag = "--version" if bin_name == "yt-dlp" else "-version"
    try:
        sh_out([bin_name, flag])
    except Exception:
        if bin_name == "yt-dlp":
            sh_out([sys.executable, "-m", "yt_dlp", "--version"])
        else:
            raise

def sec(hhmmss: str) -> float:
    m = re.match(r"^\s*(\d{1,2}):(\d{2}):(\d{2})\s*$", hhmmss)
    if not m:
        raise ValueError(f"Неверный формат времени: {hhmmss}")
    h, m_, s = map(int, m.groups())
    return h*3600 + m_*60 + s

def parse_ranges(s: str) -> List[Tuple[float, float]]:
    parts = [p.strip() for p in s.split(",") if p.strip()]
    out = []
    for p in parts:
        a, b = [q.strip() for q in p.split("-", 1)]
        out.append((sec(a), sec(b)))
    return out

def ffprobe_duration(path: str) -> float:
    out = sh_out([
        "ffprobe","-v","error","-show_entries","format=duration",
        "-of","default=nw=1:nk=1", path
    ]).strip()
    try: return float(out)
    except: return 0.0

def b64_of_file(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ---------- cache helpers ----------
def yt_id_from_url(url: str) -> str:
    m = re.search(r"(?:v=|/shorts/|/live/)([A-Za-z0-9_-]{6,})", url)
    return m.group(1) if m else hashlib.sha1(url.encode()).hexdigest()[:16]

def cache_paths(cache_dir: str, url: str, ranges: List[Tuple[float,float]]):
    vid = yt_id_from_url(url)
    key = ",".join(f"{int(a)}-{int(b)}" for a,b in ranges)
    h = hashlib.sha1(key.encode()).hexdigest()[:12]
    d = os.path.join(cache_dir, vid); os.makedirs(d, exist_ok=True)
    return {
        "dir": d,
        "full": os.path.join(d, "full.mp4"),
        "sections": os.path.join(d, f"sec_{h}.mp4"),
    }

def cookie_flags(cookies_path: Optional[str], cookies_from_browser: Optional[str]) -> list[str]:
    if cookies_from_browser:
        return ["--cookies-from-browser", cookies_from_browser]
    if cookies_path:
        return ["--cookies", os.path.expanduser(cookies_path)]
    return []

# ---------- 1) download / cut (with cache) ----------
def hhmmss(t: float) -> str:
    t = int(round(max(0,t))); h=t//3600; m=(t%3600)//60; s=t%60
    return f"{h:02d}:{m:02d}:{s:02d}"

def yt_download_sections(url: str, ranges: List[Tuple[float,float]], out_mp4: str,
                         cookies: Optional[str], cookies_from_browser: Optional[str]):
    sections = ",".join(f"*{hhmmss(a)}-{hhmmss(b)}" for a,b in ranges)
    ytcmd = ["yt-dlp"] if shutil.which("yt-dlp") else [sys.executable,"-m","yt_dlp"]
    args = ytcmd + [
        url,
        "--download-sections", sections,
        "-f", "22/18/bv*[ext=mp4][vcodec~='(avc1|h264)']+ba[ext=mp4]/b[ext=mp4]/best",
        "--merge-output-format","mp4",
        "--no-part",
        "--retries","15","--retry-sleep","2","--concurrent-fragments","1",
        "-o", out_mp4,
        *cookie_flags(cookies, cookies_from_browser),
    ]
    sh(args)
    if ffprobe_duration(out_mp4) <= 0.1:
        raise RuntimeError("sections download produced invalid file")

def yt_download_full(url: str, out_mp4: str,
                     cookies: Optional[str], cookies_from_browser: Optional[str]):
    args = ["yt-dlp", url,
            "-f", "bv*+ba/b", "--merge-output-format","mp4",
            "-o", out_mp4,
            *cookie_flags(cookies, cookies_from_browser)]
    sh(args)

def ffmpeg_cut(src: str, t0: float, t1: float, out_mp4: str):
    dur = max(0.1, t1 - t0)
    sh([
        "ffmpeg","-y","-ss",f"{t0}","-i",src,"-t",f"{dur}",
        "-c:v","libx264","-preset","veryfast","-crf","20",
        "-r","30","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","128k","-movflags","+faststart", out_mp4
    ])

def concat_mp4s(parts: List[str], out_mp4: str):
    inputs=[]; maps_v=[]; maps_a=[]
    for i,p in enumerate(parts):
        inputs+=["-i",p]; maps_v.append(f"[{i}:v]"); maps_a.append(f"[{i}:a?]")
    n=len(parts)
    filter_str="".join(maps_v+maps_a)+f"concat=n={n}:v=1:a=1[v][a]"
    sh(["ffmpeg","-y",*inputs,"-filter_complex",filter_str,
        "-map","[v]","-map","[a]","-c:v","libx264","-preset","veryfast","-crf","20",
        "-r","30","-pix_fmt","yuv420p","-c:a","aac","-b:a","128k","-movflags","+faststart", out_mp4])

def download_clip_by_ranges(url: str, ranges: List[Tuple[float,float]], workdir: str,
                            cookies: Optional[str], cookies_from_browser: Optional[str],
                            cache_dir: str) -> str:
    c = cache_paths(cache_dir, url, ranges)
    # 1) берём из кеша, если есть
    if os.path.exists(c["sections"]) and ffprobe_duration(c["sections"]) > 0.1:
        dst = os.path.join(workdir, "clip_sections.mp4")
        shutil.copy2(c["sections"], dst)
        return dst
    # 2) пробуем скачать секциями
    try:
        tmp = os.path.join(workdir, "clip_sections.mp4")
        yt_download_sections(url, ranges, tmp, cookies, cookies_from_browser)
        shutil.copy2(tmp, c["sections"])
        return tmp
    except Exception as e:
        print("[sections->fallback full+cut]", e)
    # 3) full в кеш
    full = c["full"]
    if not os.path.exists(full):
        yt_download_full(url, full, cookies, cookies_from_browser)
    # 4) cut/concat
    parts=[]
    for i,(a,b) in enumerate(ranges,1):
        p=os.path.join(workdir,f"part_{i:02d}.mp4"); ffmpeg_cut(full,a,b,p); parts.append(p)
    if len(parts)==1:
        shutil.copy2(parts[0], c["sections"]); return parts[0]
    merged=os.path.join(workdir,"clip_merged.mp4"); concat_mp4s(parts, merged)
    shutil.copy2(merged, c["sections"])
    return merged

# ---------- 2) LLM: random frame -> detect boxes ----------
def sample_random_frame(video: str, out_jpg: str) -> float:
    dur = max(1.0, ffprobe_duration(video))
    t = random.uniform(dur*0.15, dur*0.85)
    # -frames:v 1 + -f image2 у тебя уже было; добавим -update 1 для стабильной одиночной записи
    sh(["ffmpeg","-y","-ss",f"{t}","-i",video,"-frames:v","1","-q:v","2","-update","1","-f","image2", out_jpg])
    return t

def expand_boxes(boxes: List[dict], pad: float = 0.012) -> List[dict]:
    out = []
    for b in boxes:
        if b.get("label") == "side_panel":
            out.append(b); continue
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        x -= pad; y -= pad; w += 2*pad; h += 2*pad
        x = max(0.0, x); y = max(0.0, y)
        if x + w > 1.0: w = 1.0 - x
        if y + h > 1.0: h = 1.0 - y
        out.append({**b, "x": x, "y": y, "w": max(0.0, w), "h": max(0.0, h)})
    return out

def promote_side_panels(boxes: List[dict],
                        edge_thresh: float = 0.12,  # насколько близко к краю (доля ширины)
                        min_w: float = 0.12,        # минимальная ширина панели
                        min_h: float = 0.60) -> List[dict]:
    """Любой бокс у края, достаточно широкий и высокий — считаем боковой панелью."""
    out = []
    for b in boxes:
        x, y, w, h = b.get("x", 0.0), b.get("y", 0.0), b.get("w", 0.0), b.get("h", 0.0)
        label = b.get("label", "watermark")
        if h >= min_h and w >= min_w and (x <= edge_thresh or x + w >= 1.0 - edge_thresh):
            label = "side_panel"
        out.append({**b, "label": label})
    return out

def llm_detect_boxes(image_path: str, model="gpt-4o-mini") -> List[dict]:
    """
    Возвращает список боксов (0..1): {label:'side_panel'|'watermark', x,y,w,h, conf}
    """
    try:
        from openai import OpenAI
        api = OpenAI()
        prompt = (
            "Return ONLY JSON {\"boxes\":[{\"label\":\"side_panel|watermark\",\"x\":0.78,"
            "\"y\":0.0,\"w\":0.22,\"h\":1.00,\"conf\":0.9}, ...]}. "
            "Mark LONG vertical stripes attached to the LEFT or RIGHT edge as \"side_panel\" "
            "(height >= 60% and width >= 12%), e.g. ranking/info columns. "
            "Small logos/text anywhere else are \"watermark\". "
            "Use relative coords 0..1 (x,y=top-left). If nothing -> boxes:[]."
        )
        b64 = b64_of_file(image_path)
        r = api.chat.completions.create(
            model=model,
            messages=[
                {"role":"system","content":"Answer strictly JSON."},
                {"role":"user","content":[
                    {"type":"text","text":prompt},
                    {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{b64}"}}
                ]}
            ],
            temperature=0.0,
            response_format={"type":"json_object"},
        )
        txt = (r.choices[0].message.content or "").strip()
        js = json.loads(txt) if txt else {}
        out=[]
        for b in js.get("boxes",[]):
            try:
                x=float(b["x"]); y=float(b["y"]); w=float(b["w"]); h=float(b["h"])
                lab=str(b.get("label","watermark")); conf=float(b.get("conf",0.5))
                if 0<=x<=1 and 0<=y<=1 and 0<w<=1 and 0<h<=1 and x+w<=1.001 and y+h<=1.001:
                    out.append({"label":lab,"x":x,"y":y,"w":w,"h":h,"conf":conf})
            except: pass
        return out
    except Exception as e:
        print("[LLM] vision error:", e)
        return []

def choose_crop(boxes: List[dict]) -> Optional[dict]:
    """Возвращает {side:'right'|'left', keep_start, keep_width} — какую часть оставить по X."""
    cand = None
    for b in boxes:
        if b.get("label") != "side_panel":
            continue
        if b["h"] >= 0.6 and b["w"] >= 0.12 and (b["x"] > 0.65 or b["x"] < 0.10):
            if cand is None or b["w"] > cand["w"]:
                cand = b
    if not cand:
        return None
    if cand["x"] > 0.5:
        return {"side": "right", "keep_start": 0.0, "keep_width": cand["x"]}
    start = cand["x"] + cand["w"]
    return {"side": "left", "keep_start": start, "keep_width": max(1.0 - start, 0.01)}

def transform_boxes_for_crop(boxes: List[dict], keep_start: float, keep_width: float) -> List[dict]:
    """Пересчитать watermark боксы под горизонтальный кроп (по X). Отфильтруем side_panel."""
    out=[]
    for b in boxes:
        if b.get("label")=="side_panel":  # уже убрали панель
            continue
        x = (b["x"] - keep_start) / max(keep_width, 1e-6)
        w = b["w"] / max(keep_width, 1e-6)
        # отсечь те, кто полностью вне видимой области
        if x+w <= 0 or x >= 1:
            continue
        # подрезать и клампнуть
        x = max(0.0, min(1.0, x))
        w = max(0.0, min(1.0-x, w))
        out.append({"label":b.get("label","watermark"),"x":x,"y":b["y"],"w":w,"h":b["h"],"conf":b.get("conf",0.5)})
    return out

def blur_boxes_chain(src_label: str, boxes: List[dict]) -> str:
    """
    Из [{src_label}] получаем один выход [fg] с заблюренными watermark-боксами.
    ВАЖНО: split всегда с явным числом выходов, чтобы не плодить лишние видеопотоки.
    """
    wm = [b for b in boxes if b.get("label") != "side_panel"]
    if not wm:
        return f"[{src_label}]scale=1080:-2,setsar=1[fg]"

    BLUR = "9:1:9:1"  # безопасно для yuv420p на macOS/FFmpeg 7
    chain = f"[{src_label}]split=1[s0]"   # строго один выход
    prev = "s0"
    for i, b in enumerate(wm, start=1):
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        chain += (
            f";[{prev}]split=2[{prev}a][for{i}]"  # явно 2 выхода
            f";[for{i}]crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f},boxblur={BLUR}[bl{i}]"
            f";[{prev}a][bl{i}]overlay=W*{x:.4f}:H*{y:.4f}:format=auto[s{i}]"
        )
        prev = f"s{i}"
    chain += f";[{prev}]scale=1080:-2,setsar=1[fg]"
    return chain

# ---------- 3) compose (crop/blur -> overlay center) ----------
def compose_with_boxes(video_in: str, bg_path: str, out_mp4: str, boxes: List[dict]):
    """Кропим боковые панели (если есть) и кладём 16:9 по центру 9:16 фона. Без блюра."""
    dur = max(1.0, ffprobe_duration(video_in))

    # входы
    is_image = os.path.splitext(bg_path)[1].lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")
    inputs = ["-i", video_in]
    if is_image:
        inputs += ["-loop", "1", "-t", f"{dur}", "-i", bg_path]
    else:
        inputs += ["-stream_loop", "-1", "-t", f"{dur}", "-i", bg_path]

    # усиливаем распознавание панелей
    boxes = promote_side_panels(boxes)

    crop = choose_crop(boxes)

    # фон 1080x1920
    bg = "[1:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p[bg]"

    if crop:
        keep_start = crop["keep_start"]; keep_width = crop["keep_width"]
        if crop["side"] == "right":
            # Оставляем левую часть [0 .. keep_width]
            fg = f"[0:v]crop=iw*{keep_width:.4f}:ih:0:0,scale=1080:-2,setsar=1[fg]"
        else:
            # Оставляем правую часть [keep_start .. 1]
            fg = f"[0:v]crop=iw*{keep_width:.4f}:ih:iw*{keep_start:.4f}:0,scale=1080:-2,setsar=1[fg]"
    else:
        # Панелей не нашли — просто масштаб по ширине (как раньше)
        fg = "[0:v]scale=1080:-2,setsar=1[fg]"

    overlay = "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[v]"
    fc = ";".join([fg, bg, overlay])

    cmd = ["ffmpeg", "-y", *inputs,
           "-filter_complex", fc,
           "-map", "[v]", "-map", "0:a?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-r", "30", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
           out_mp4]
    print("\n[ffmpeg cmd]\n", " ".join(cmd), "\n")
    sh(cmd)

# ---------- 4) simple compose (как было изначально) ----------
def compose_simple(video_in: str, bg_path: str, out_mp4: str):
    dur = max(1.0, ffprobe_duration(video_in))
    is_image = os.path.splitext(bg_path)[1].lower() in (".jpg",".jpeg",".png",".webp",".bmp",".tif",".tiff")
    inputs = ["-i", video_in]
    if is_image:
        inputs += ["-loop","1","-t",f"{dur}","-i", bg_path]
    else:
        inputs += ["-stream_loop","-1","-t",f"{dur}","-i", bg_path]
    fc = (
        "[0:v]scale=1080:-2,setsar=1,format=yuv420p[fg];"
        "[1:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,format=yuv420p[bg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[v]"
    )

    tmp_out, final_out = atomic_paths(out_mp4)

    cmd = ["ffmpeg","-y", *inputs,
           "-filter_complex", fc,
           "-map","[v]","-map","0:a?",
           "-c:v","libx264","-preset","veryfast","-crf","20",
           "-r","30","-pix_fmt","yuv420p",
           "-c:a","aac","-b:a","128k","-movflags","+faststart",
           "-f","mp4",      # <— критично
           tmp_out]
    print("\n[ffmpeg cmd]\n", " ".join(cmd), "\n")
    try:
        sh(cmd)
        os.replace(tmp_out, final_out)
    finally:
        if os.path.exists(tmp_out):
            try: os.remove(tmp_out)
            except: pass

# ---------- main ----------
def main():
    ap=argparse.ArgumentParser(description="YT → cut (cache) → LLM detect → crop/blur → overlay 16:9 center")
    ap.add_argument("--url", required=True)
    g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--range", help="HH:MM:SS-HH:MM:SS")
    g.add_argument("--ranges", help="'12:54-13:21,18:41-18:59'")
    ap.add_argument("--bg", required=True, help="Путь к фону (JPG/PNG/WebP/BMP/TIFF или видео MP4/MOV/GIF и т.п.)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cookies", help="Путь к Netscape cookie.txt")
    ap.add_argument("--cookies-from-browser", dest="cookies_browser",
                    help="например: chrome:Default | brave:Default | firefox:default-release | safari")
    ap.add_argument("--cache", default=os.path.expanduser("~/.cache/yt_shorts"),
                    help="Каталог для кеша (по умолчанию ~/.cache/yt_shorts)")
    ap.add_argument("--llm", choices=["on","off"], default="on")
    ap.add_argument("--vision_model", default="gpt-4o-mini")
    args=ap.parse_args()

    ensure_has("ffmpeg"); ensure_has("ffprobe"); ensure_has("yt-dlp")
    os.makedirs(args.cache, exist_ok=True)

    work = tempfile.mkdtemp(prefix="shorts_")
    try:
        # таймкоды
        if args.range:
            a,b=args.range.split("-",1); ranges=[(sec(a), sec(b))]
        else:
            ranges=parse_ranges(args.ranges)

        # скачать только нужные участки (с кешом)
        clip = download_clip_by_ranges(
            args.url, ranges, work,
            cookies=args.cookies,
            cookies_from_browser=args.cookies_browser,
            cache_dir=args.cache
        )
        if ffprobe_duration(clip) <= 0.1:
            raise RuntimeError("invalid clip: zero duration")

        if args.llm == "on":
            # случайный кадр -> LLM
            frame = os.path.join(work, "rnd.jpg")
            sample_random_frame(clip, frame)
            boxes = llm_detect_boxes(frame, model=args.vision_model)
            compose_with_boxes(clip, args.bg, args.out, boxes)
        else:
            # режим "как было изначально": просто вставка по центру
            compose_simple(clip, args.bg, args.out)

        print(f"[OK] saved: {args.out}")
    finally:
        shutil.rmtree(work, ignore_errors=True)

def atomic_paths(final_out: str) -> tuple[str, str]:
    """
    Делаем временное имя так, чтобы ПОСЛЕДНИМ расширением было .mp4.
    Пример: /path/video.mp4 -> /path/.video.part.mp4  (потом атомарно os.replace)
    """
    d, b = os.path.split(final_out)
    root, ext = os.path.splitext(b)
    if not ext:
        ext = ".mp4"
    tmp = os.path.join(d, f".{root}.part{ext}")  # .part.mp4 (последнее расширение — .mp4)
    return tmp, final_out

if __name__=="__main__":
    main()
