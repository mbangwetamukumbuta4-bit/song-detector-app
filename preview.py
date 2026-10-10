"""30-second previews from Apple's free iTunes Search API (no key needed)."""
import json
import urllib.request
from urllib.parse import quote_plus

import core


def find_preview(artist, title, timeout=20):
    """Return the URL of a 30-second preview, or None if the song has none."""
    q = quote_plus(f"{artist} {title}")
    url = f"https://itunes.apple.com/search?term={q}&media=music&entity=song&limit=5"
    req = urllib.request.Request(url, headers={"User-Agent": "SongDetector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=core._ssl_context()) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    results = data.get("results") or []
    wanted = title.lower()
    for item in results:                      # best: the title matches
        if wanted in (item.get("trackName") or "").lower() and item.get("previewUrl"):
            return item["previewUrl"]
    for item in results:                      # otherwise the first result with a preview
        if item.get("previewUrl"):
            return item["previewUrl"]
    return None


def download(url, path, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "SongDetector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=core._ssl_context()) as resp:
        data = resp.read()
    with open(path, "wb") as f:
        f.write(data)
