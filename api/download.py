import json, base64, re, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

# Only proxy the platforms' own CDNs — prevents this endpoint being abused as an open proxy.
# Matched as domain suffixes, so "instagram.com.evil.net" or "notfbcdn.net" are rejected.
ALLOWED_DOMAINS = (
    "instagram.com", "cdninstagram.com",
    "facebook.com", "fbcdn.net", "fbsbx.com",
    "tiktok.com", "tiktokcdn.com", "tiktokcdn-us.com", "tiktokv.com", "tiktokv.us",
    "byteoversea.com", "ibytedtos.com", "muscdn.com", "ttwstatic.com",
    "akamaized.net",  # TikTok serves some videos from Akamai edge hosts
    "googlevideo.com", "ytimg.com", "ggpht.com", "youtube.com",
)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

def allowed(url):
    p = urlparse(url)
    host = (p.hostname or "").lower()
    return p.scheme in ("http", "https") and any(host == d or host.endswith("." + d) for d in ALLOWED_DOMAINS)

class CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """Re-check the allowlist on every redirect so a CDN hop can't lead somewhere else."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed(newurl):
            raise urllib.error.HTTPError(newurl, 403, "Redirect to a host that is not allowed", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

opener = urllib.request.build_opener(CheckedRedirects)

class handler(BaseHTTPRequestHandler):
    def _err(self, code, text):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(text.encode())

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        src = qs.get("u", [""])[0]
        name = qs.get("n", ["video.mp4"])[0]
        hdr = qs.get("h", [""])[0]
        inline = qs.get("inline", [""])[0] == "1"

        if not allowed(src):
            return self._err(403, "That host is not allowed.")

        headers = {"User-Agent": UA, "Accept": "*/*"}
        if hdr:
            try:
                headers.update(json.loads(base64.urlsafe_b64decode(hdr + "=" * (-len(hdr) % 4))))
            except Exception:
                pass
        rng = self.headers.get("Range")
        if rng:
            headers["Range"] = rng

        try:
            r = opener.open(urllib.request.Request(src, headers=headers), timeout=25)
        except Exception:
            return self._err(502, "The video source didn't respond. Fetch the link again and retry.")

        with r:
            self.send_response(r.status)
            self.send_header("Content-Type", r.headers.get("Content-Type", "application/octet-stream"))
            for k in ("Content-Length", "Content-Range", "Accept-Ranges"):
                if r.headers.get(k):
                    self.send_header(k, r.headers[k])
            if inline:
                self.send_header("Cache-Control", "public, max-age=3600")
            else:
                safe = re.sub(r"[^\w.\- ]", "", name) or "video.mp4"
                self.send_header("Content-Disposition",
                                 f"attachment; filename=\"{safe}\"; filename*=UTF-8''{quote(safe)}")
                self.send_header("Cache-Control", "no-store")
            self.end_headers()
            # Headers are already sent, so a mid-stream failure can only end the response early
            try:
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            except Exception:
                pass
