# Dropvid

Paste an Instagram, Facebook, TikTok or YouTube link, pick from the qualities the video actually has, and save it.

A single static page (`index.html`) plus two Python serverless functions on Vercel that use [yt-dlp](https://github.com/yt-dlp/yt-dlp).

```
index.html          the site
api/resolve.py      finds the video and its qualities
api/download.py     streams the file back with a proper filename
requirements.txt
vercel.json
```

## Deploy

1. On vercel.com: **Add New → Project**, import this repo, and deploy. No framework preset needed.
2. Optional but recommended for Instagram: in **Settings → Environment Variables**, add `COOKIES_TXT` with the contents of a Netscape `cookies.txt` exported from a logged-in throwaway account. Redeploy afterwards.

## Notes

- **Instagram** blocks datacenter IPs heavily. Without `COOKIES_TXT`, many Instagram links will fail with a login error. TikTok and Facebook usually work without it.
- **YouTube is limited on Vercel.** YouTube stores picture and sound separately, so most qualities are offered as silent video plus a separate Audio download (joining them needs ffmpeg, which Vercel doesn't have). File links are tied to the IP that fetched them, yt-dlp needs Deno to avoid YouTube's speed throttling (downloads run at roughly 20–45 KB/s without it), and YouTube often blocks datacenter IPs. Expect only small files to finish within the 60-second function limit. Full YouTube support needs the API on a long-running server with ffmpeg and Deno.
- **Keep yt-dlp fresh.** When a platform changes its site, extraction breaks until yt-dlp ships a fix. Redeploying installs the latest version.
- **Large files.** Video bytes stream through `api/download.py`. Test a video over 5 MB after deploying; if it gets cut off, the "Open the video directly" link on the result card is the fallback.
- `api/download.py` only proxies the platforms' own CDN domains and re-checks every redirect, so it can't be used as an open proxy.

Only download content you own or have permission to save. Not affiliated with Meta, ByteDance, Google or YouTube.
