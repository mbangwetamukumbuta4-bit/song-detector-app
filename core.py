"""core.py - Logic for Wenzosong Detector"""
import os
import json
import time
import requests
from datetime import datetime, date

# This will be set by the app
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


# ---------- Settings ----------
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


# ---------- Usage (daily limit) ----------
def usage_today():
    data = _load(USAGE_FILE, {})
    today = str(date.today())
    return data.get(today, 0)


def _add_usage():
    data = _load(USAGE_FILE, {})
    today = str(date.today())
    data[today] = data.get(today, 0) + 1
    _save(USAGE_FILE, data)


# ---------- History ----------
def get_history():
    return _load(HISTORY_FILE, [])


def add_history(entry):
    history = get_history()
    entry = dict(entry)
    entry["date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    history.append(entry)
    # keep only last 100
    history = history[-100:]
    _save(HISTORY_FILE, history)


def clear_history():
    _save(HISTORY_FILE, [])


# ---------- Library ----------
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
    lib = [i
