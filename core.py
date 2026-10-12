"""core.py - Logic for Wenzosong Detector"""
import os
import json
import requests
from datetime import datetime, date
from urllib.parse import quote_plus

DATA_DIR = "."

AUDD_DAILY_LIMIT = 10
SETTINGS_FILE = "settings.json"
HISTORY_FILE = "history.json"
LIBRARY_FILE = "library.json"
USAGE_FILE = "usage.json"


def _path(name):
    return os.path.join(DATA_DIR, name)


def _load(name, default):
    try:
        with open(_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(name, data):
    try:
        with open(_path(name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_settings():
    return _load(SETTINGS_FILE, {
        "audd_token": "",
        "acr_host": "",
        "acr_key": "",
        "acr_secret": ""
    })


def save_settings(data):
    current = get_settings()
    current.update(data)
    _save(SETTINGS_FILE, current)


def usage_today():
    data = _load(USAGE_FILE, {})
    today = str(date.today())
    return data.get(today, 0)


def _add_usage():
    data = _load(USAGE_FILE, {})
    today = str(date.today())
    data[today] = data.get(today, 0) + 1
    _save(USAGE_FILE, data)


def get_history():
    return _load(HISTORY_FILE, [])


def add_history(entry):
    history = get_history()
    entry = dict(entry)
    entry["date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    history.append(entry)
    history = history[-100:]
    _save(HISTORY_FILE, history)


def clear_history():
    _save(HISTORY_FILE, [])


def get_library():
    return _load(LIBRARY_FILE, [])


def in_library(entry):
    lib = get_library()
    for item in lib:
        if item.get("title") == entry.get("title") and item.get("artist") == entry.get("artist"):
            return True
    return False


def add_library(entry):
    if in_library(entry):
        return
    lib = get_library()
    lib.append({
        "title": entry.get("title", ""),
        "artist": entry.get("artist", ""),
        "album": entry.get("album", ""),
        "image": entry.get("image", "")
    })
    _save(LIBRARY_FILE, lib)


def remove_library(entry):
    lib = get_library()
    new_lib = []
    for i in lib:
        if not (i.get("title") == entry.get("title") and i.get("artist") == entry.get("artist")):
            new_lib.append(i)
    _save(LIBRARY_FILE, new_lib)


def sources(entry):
    title = entry.get("title", "")
    artist = entry.get("artist", "")
    q = f"{artist} {title}".strip()
    query = quote_plus(q)

    return [
        ("YouTube", f"https://www.youtube.com/results?search_query={query}"),
        ("Spotify", f"https://open.spotify.com/search/{query}"),
        ("Apple Music", f"https://music.apple.com/search?term={query}"),
        ("Audiomack", f"https://audiomack.com/search?q={query}"),
        ("Boomplay", f"https://www.boomplay.com/search/{query}"),
    ]


def detect(path, over_limit=False):
    settings = get_settings()
    token = settings.get("audd_token", "").strip()

    if not token:
        return None, "Please add your AudD token in Settings.", "error"

    if not over_limit and usage_today() >= AUDD_DAILY_LIMIT:
        return None, f"You have reached the free limit of {AUDD_DAILY_LIMIT} detections today.", "limit"

    try:
        with open(path, "rb") as f:
            files = {"file": f}
            data = {
                "api_token": token,
                "return": "apple_music,spotify,deezer"
            }
            response = requests.post("https://api.audd.io/", data=data, files=files, timeout=30)

        result = response.json()

        if result.get("status") == "success" and result.get("result"):
            song = result["result"]
            entry = {
                "title": song.get("title", "Unknown"),
                "artist": song.get("artist", "Unknown"),
                "album": song.get("album", ""),
                "image": ""
            }

            if "apple_music" in song and song["apple_music"]:
                artwork = song["apple_music"].get("artwork", {})
                if artwork:
                    url = artwork.get("url", "")
                    entry["image"] = url.replace("{w}", "300").replace("{h}", "300")
            elif "spotify" in song and song["spotify"]:
                images = song["spotify"].get("album", {}).get("images", [])
                if images:
                    entry["image"] = images[0].get("url", "")

            _add_usage()
            return entry, "Song found", "ok"
        else:
            return None, "Could not identify the song. Try again with clearer audio.", "error"

    except requests.exceptions.Timeout:
        return None, "Connection timeout. Check your internet.", "error"
    except Exception as e:
        return None, f"Error: {str(e)}", "error"
