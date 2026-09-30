import json, os, re, base64
from http.server import BaseHTTPRequestHandler
import yt_dlp

PLATFORMS = {
    "instagram": re.compile(r"^https?://(www\.)?instagram\.com/", re.I),
    "facebook": re.compile(r"^https?://(www\.|m\.|web\.|fb\.)?(facebook\.com|fb\.watch)/", re.I),
    "tiktok": re.compile(r"^https?://(www\.|vm\.|vt\.)?tiktok\.com/", re.I),
}

def detect(url):
    return next((k for k, p in PLATFORMS.items() if p.search(url)), None)

def cookie_file():
    """Optional: set COOKIES_TXT env var in Vercel to the contents of a Netscape cookies.txt."""
    raw = os.environ.get("COOKIES_TXT")
    if not raw:
        return None
    path = "/tmp/cookies.txt"
    with open(path, "w") as f:
        f.write(raw)
    return path

def b64(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

def friendly(msg):
    m = msg.lower()
    if "login" in m or "cookies" in m or "rate-limit" in m or "not available" in m:
        return "This platform is asking for a login. The site owner can add cookies to fix this."
    if "private" in m:
        return "This video is private."
    if "unsupported url" in m or "no video" in m or "there is no video" in m:
        return "No downloadable video was found at that link."
    return "Couldn't fetch this video — the link may be wrong or the platform changed something."

def cdn_cookies(ydl, url, secret_names):
    """Cookies the CDN expects (TikTok 403s without them), minus the owner's login cookies.

    These end up in the download URL the visitor sees, so anything from COOKIES_TXT is dropped.
    """
    try:
        header = ydl.cookiejar.get_cookie_header(url) or ""
    except Exception:
        return ""
    pairs = [p.strip() for p in header.split(";") if p.strip()]
    return "; ".join(p for p in pairs if p.split("=", 1)[0] not in secret_names)

def pick_formats(info, ydl, secret_names):
    fmts = info.get("formats") or []
    # progressive = video + audio in one file (no ffmpeg needed)
    prog = [f for f in fmts if f.get("url") and f.get("vcodec") != "none" and f.get("acodec") != "none"]
    if not prog and info.get("url"):
        prog = [{"url": info["url"], "ext": info.get("ext", "mp4"), "height": info.get("height"), "http_headers": info.get("http_headers")}]
    prog.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0), reverse=True)

    out, seen = [], set()
    for f in prog:
        w, h = f.get("width"), f.get("height")
        # "720p" means the short side, so a vertical 720x1280 reel is 720p, not 1280p
        short = min(w, h) if w and h else h
        key = short or f.get("format_id")
        if key in seen:
            continue
        seen.add(key)
        label = f"{short}p" if short else (f.get("format_note") or "Video").upper()
        headers = dict(f.get("http_headers") or {})
        ck = cdn_cookies(ydl, f["url"], secret_names)
        if ck:
            headers["Cookie"] = ck
        out.append({
            "label": label,
            "url": f["url"],
            "ext": f.get("ext") or "mp4",
            "width": w,
            "height": h,
            "filesize": f.get("filesize") or f.get("filesize_approx"),
            "note": "no watermark" if "nowm" in (f.get("format_id") or "").lower() else "",
            "h": b64(headers),
        })
        if len(out) == 4:
            break
    return out

class handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            data = {}
        url = (data.get("url") or "").strip()
        platform = detect(url)
        if not platform:
            return self._json(400, {"error": "Only Instagram, Facebook and TikTok links are supported."})

        opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
                "cachedir": False, "socket_timeout": 20}
        ck = cookie_file()
        if ck:
            opts["cookiefile"] = ck

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                secret_names = {c.name for c in ydl.cookiejar}
                info = ydl.extract_info(url, download=False)
                if info.get("_type") == "playlist" or "entries" in info:   # carousel posts
                    entries = [e for e in (info.get("entries") or []) if e]
                    info = entries[0] if entries else {}
                formats = pick_formats(info, ydl, secret_names)
        except yt_dlp.utils.DownloadError as e:
            return self._json(422, {"error": friendly(str(e))})
        except Exception:
            return self._json(500, {"error": "Something went wrong while fetching the video."})

        if not formats:
            return self._json(422, {"error": "This post doesn't contain a downloadable video."})

        self._json(200, {
            "platform": platform,
            "title": info.get("title") or (info.get("description") or "")[:90] or "Untitled video",
            "uploader": info.get("uploader") or info.get("channel") or "",
            "uploader_id": info.get("uploader_id") or info.get("channel_id") or "",
            "description": (info.get("description") or "")[:5000],
            "webpage_url": info.get("webpage_url") or url,
            "upload_date": info.get("upload_date"),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "comment_count": info.get("comment_count"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "formats": formats,
        })
