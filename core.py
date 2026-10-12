"""Song Detector - logic with no screens (storage, detection, links).

Detection order: ACRCloud first (if you entered its keys in Settings),
then AudD as a backup. Your keys are typed into the app's Settings screen
and stored only on your phone, never in this code.
"""
import base64
import hashlib
import hmac
import json
import os
import ssl
import time
import urllib.request
import uuid
from datetime import datetime
from urllib.parse import quote, quote_plus

DATA_DIR = "."                 # the app sets this to its private folder
AUDD_DAILY_LIMIT = 10
MAX_HISTORY = 500
NO_MATCH = "No match. Move closer to the music, turn it up, and try again."


# ---------- storage ----------
def _path(name):
    return os.path.join(DATA_DIR, name)


def load(name, default):
    try:
        with open(_path(name), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def save(name, data):
    tmp = _path(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _path(name))


def get_settings():
    s = {"audd_token": "", "acr_host": "", "acr_key": "", "acr_secret": ""}
    data = load("settings.json", {})
    if isinstance(data, dict):
        s.update({k: str(v).strip() for k, v in data.items() if k in s})
    return s


def save_settings(values):
    save("settings.json", {k: str(v).strip() for k, v in values.items()})


def same_song(a, b):
    return (a["title"].lower(), a["artist"].lower()) == (b["title"].lower(), b["artist"].lower())


def get_history():
    return load("history.json", [])


def add_history(entry):
    save("history.json", (get_history() + [entry])[-MAX_HISTORY:])


def clear_history():
    save("history.json", [])


def get_library():
    return load("library.json", [])


def in_library(entry):
    return any(same_song(entry, s) for s in get_library())


def add_library(entry):
    if not in_library(entry):
        save("library.json", get_library() + [entry])


def remove_library(entry):
    save("library.json", [s for s in get_library() if not same_song(entry, s)])


# ---------- daily AudD counter ----------
def usage_today():
    data = load("usage.json", {})
    return data.get(datetime.now().strftime("%Y-%m-%d"), 0) if isinstance(data, dict) else 0


def add_usage():
    save("usage.json", {datetime.now().strftime("%Y-%m-%d"): usage_today() + 1})


# ---------- network ----------
def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def post_multipart(url, fields, file_field, file_path, timeout=60):
    boundary = "----songdetector" + uuid.uuid4().hex
    body = b""
    for key, value in fields.items():
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode()
    with open(file_path, "rb") as f:
        audio = f.read()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
             f'filename="clip.m4a"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
    body += audio + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "SongDetector/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------- ACRCloud ----------
def identify_acr(host, key, secret, path):
    ts = str(int(time.time()))
    to_sign = "\n".join(["POST", "/v1/identify", key, "audio", "1", ts])
    sig = base64.b64encode(
        hmac.new(secret.encode("ascii"), to_sign.encode("ascii"), digestmod=hashlib.sha1).digest()
    ).decode("ascii")
    fields = {
        "access_key": key,
        "sample_bytes": os.path.getsize(path),
        "timestamp": ts,
        "signature": sig,
        "data_type": "audio",
        "signature_version": "1",
    }
    return post_multipart(f"https://{host}/v1/identify", fields, "sample", path)


def entry_from_acr(m):
    ext = m.get("external_metadata") or {}
    spotify_id = ((ext.get("spotify") or {}).get("track") or {}).get("id")
    vid = (ext.get("youtube") or {}).get("vid")
    artists = ", ".join(a.get("name", "") for a in (m.get("artists") or []) if a.get("name"))
    return {
        "title": m.get("title") or "Unknown",
        "artist": artists or "Unknown",
        "album": (m.get("album") or {}).get("name") or "",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "youtube": f"https://www.youtube.com/watch?v={vid}" if vid else None,
        "spotify": f"https://open.spotify.com/track/{spotify_id}" if spotify_id else None,
        "apple": None,
        "via": "ACRCloud",
    }


# ---------- AudD ----------
def entry_from_audd(song):
    return {
        "title": song.get("title") or "Unknown",
        "artist": song.get("artist") or "Unknown",
        "album": song.get("album") or "",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "youtube": None,
        "spotify": ((song.get("spotify") or {}).get("external_urls") or {}).get("spotify"),
        "apple": (song.get("apple_music") or {}).get("url"),
        "via": "AudD",
    }


# ---------- detection ----------
def detect(path, allow_over_limit=False):
    """Return (entry, message, code). code is ok / nomatch / limit / error."""
    s = get_settings()
    acr = (s["acr_host"], s["acr_key"], s["acr_secret"]) if all(
        (s["acr_host"], s["acr_key"], s["acr_secret"])) else None
    audd = s["audd_token"] or None
    problems = []

    if acr:
        try:
            data = identify_acr(*acr, path)
            status = data.get("status") or {}
            music = (data.get("metadata") or {}).get("music") or []
            if status.get("code") == 0 and music:
                return entry_from_acr(music[0]), None, "ok"
            if status.get("code") == 1001:            # heard it, no match: don't waste the backup
                return None, NO_MATCH, "nomatch"
            problems.append("ACRCloud: " + str(status.get("msg", data)))
        except (OSError, ValueError) as err:
            problems.append(f"ACRCloud network problem: {err}")

    if audd or not acr:
        used = usage_today()
        if used >= AUDD_DAILY_LIMIT and not allow_over_limit:
            return None, f"You've used {used} of {AUDD_DAILY_LIMIT} AudD detections today.", "limit"
        try:
            data = post_multipart("https://api.audd.io/",
                                  {"api_token": audd or "test", "return": "apple_music,spotify"},
                                  "file", path)
            add_usage()
            if data.get("status") == "success":
                if data.get("result"):
                    return entry_from_audd(data["result"]), None, "ok"
                return None, NO_MATCH, "nomatch"
            problems.append("AudD: " + str((data.get("error") or {}).get("error_message", data)))
        except (OSError, ValueError) as err:
            problems.append(f"AudD network problem: {err}")

    return None, "\n".join(problems) or "Could not identify the song.", "error"


# ---------- links ----------
def sources(entry):
    name = f"{entry['artist']} {entry['title']}"
    return [
        ("Watch the video on YouTube",
         entry.get("youtube") or "https://www.youtube.com/results?search_query=" + quote_plus(name)),
        ("Spotify", entry.get("spotify") or "https://open.spotify.com/search/" + quote(name)),
        ("Apple Music", entry.get("apple") or "https://music.apple.com/search?term=" + quote_plus(name)),
        ("Boomplay", "https://www.boomplay.com/search/default/" + quote(name)),
        ("Audiomack", "https://audiomack.com/search?q=" + quote_plus(name)),
                 ]
