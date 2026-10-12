"""Song Detector - Android app (Kivy). Logic lives in core.py."""
import math
import os
import threading
import time
from urllib.parse import quote_plus

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

import core
import preview

SECONDS = 10

# ---------- colours ----------
BG = (0.043, 0.027, 0.086, 1)
CARD = (0.09, 0.07, 0.17, 0.92)
TEXT = (0.93, 0.945, 0.97, 1)
DIM = (0.58, 0.64, 0.74, 1)
AMBER = (0.74, 0.58, 1, 1)          # accent colour (violet)
VIOLET = (0.45, 0.30, 1, 1)
REC = (1, 0.35, 0.37, 1)
DARK = (0.08, 0.08, 0.1, 1)
CLEAR = (0, 0, 0, 0)
COVERS = [(0.24, 0.84, 0.76, 1), (0.65, 0.55, 0.98, 1), (0.96, 0.56, 0.69, 1),
          (0.55, 0.82, 0.31, 1), (0.42, 0.71, 1, 1), (1, 0.72, 0.3, 1)]
SERVICES = {"YouTube": (1, 0.25, 0.25, 1), "Spotify": (0.12, 0.84, 0.38, 1),
            "Apple Music": (0.98, 0.34, 0.5, 1), "Boomplay": (0.2, 0.6, 1, 1),
            "Audiomack": (1, 0.62, 0.1, 1), "Search": (0.62, 0.68, 0.78, 1)}


def online_on():
    """The Online switch at the top of the home screen (remembered between launches)."""
    data = core.load("online.json", {})
    return bool(data.get("on", True)) if isinstance(data, dict) else True


def set_online(value):
    core.save("online.json", {"on": bool(value)})


class Backdrop(FloatLayout):
    """The app background: violet gradient, soft neon glows, faint rings and waves."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(pos=self.redraw, size=self.redraw)
        self.redraw()

    @staticmethod
    def _glow(cx, cy, radius, rgb, strength, steps=40):
        for k in range(steps):
            r = radius * (1 - k / float(steps))
            Color(rgb[0], rgb[1], rgb[2], strength / steps * 2.2)
            Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))

    def redraw(self, *a):
        self.canvas.before.clear()
        x, y, w, h = self.x, self.y, self.width, self.height
        if w < 2 or h < 2:
            return
        cx, cy = x + w / 2, y + h * 0.52
        with self.canvas.before:
            top, bottom = (0.062, 0.036, 0.125), (0.027, 0.020, 0.062)
            bands = 48
            for i in range(bands):
                t = i / float(bands - 1)
                Color(bottom[0] + (top[0] - bottom[0]) * t, bottom[1] + (top[1] - bottom[1]) * t,
                      bottom[2] + (top[2] - bottom[2]) * t, 1)
                Rectangle(pos=(x, y + h * i / bands), size=(w, h / bands + 1))
            self._glow(x + w * 0.1, y + h * 0.85, w * 0.95, (0.50, 0.25, 1.0), 0.32)
            self._glow(x + w * 0.95, y + h * 0.12, w * 0.95, (0.22, 0.38, 1.0), 0.28)
            self._glow(cx, cy, w * 0.60, (0.85, 0.30, 0.90), 0.16)
            for k, f in enumerate((0.22, 0.34, 0.46, 0.58, 0.70)):
                alpha = 0.16 - k * 0.025
                Color(0.55, 0.40, 1.0, alpha * 0.45)
                Line(circle=(cx, cy, w * f), width=dp(4))
                Color(0.66, 0.52, 1.0, alpha)
                Line(circle=(cx, cy, w * f), width=dp(1))
            for amp, ph, col in ((0.040, 0.0, (0.62, 0.45, 1.0, 0.20)), (0.030, 1.7, (0.35, 0.50, 1.0, 0.18))):
                pts = []
                for i in range(41):
                    px = x + w * i / 40.0
                    py = cy + h * amp * math.sin(i / 40.0 * 6.283 * 1.6 + ph) * (0.4 + 0.6 * math.sin(i / 40.0 * 3.1416))
                    pts += [px, py]
                Color(*col)
                Line(points=pts, width=dp(1.4))


# ---------- building blocks ----------
def label(text, size=16, color=TEXT, bold=False, height=None, halign="left", one_line=False):
    lab = Label(text=text, font_size=dp(size), color=color, bold=bold, halign=halign, valign="middle")
    lab.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    lab.size_hint_y = None
    if one_line:
        lab.shorten = True
        lab.shorten_from = "right"
    if height:
        lab.height = dp(height)
    else:
        lab.bind(texture_size=lambda w, s: setattr(w, "height", s[1] + dp(6)))
    return lab


class Surface(BoxLayout):
    """A box with a rounded, coloured background."""

    def __init__(self, bg=CARD, radius=16, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            self._color = Color(*bg)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(radius)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def set_bg(self, rgba):
        self._color.rgba = rgba


class Row(ButtonBehavior, Surface):
    """A tappable Surface."""

    def __init__(self, bg=CARD, **kw):
        super().__init__(bg=bg, **kw)
        self._base = bg
        self.bind(state=self._paint)

    def _paint(self, *a):
        r, g, b, al = self._base
        self.set_bg((r * 0.8, g * 0.8, b * 0.8, al) if self.state == "down" else self._base)


class RoundButton(ButtonBehavior, Label):
    def __init__(self, text="", bg=CARD, fg=TEXT, radius=14, height=52, **kw):
        super().__init__(text=text, color=fg, bold=True, font_size=dp(16),
                         size_hint_y=None, height=dp(height), **kw)
        self.bg = bg
        with self.canvas.before:
            self._color = Color(*bg)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(radius)])
        self.bind(pos=self._sync, size=self._sync, state=self._paint, disabled=self._paint)

    def _sync(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size

    def _paint(self, *a):
        r, g, b, a = self.bg
        if self.disabled:
            a *= 0.4
        elif self.state == "down":
            r, g, b = r * 0.8, g * 0.8, b * 0.8
        self._color.rgba = (r, g, b, a)


class Dot(Widget):
    def __init__(self, rgba, **kw):
        super().__init__(size_hint=(None, None), size=(dp(14), dp(14)), **kw)
        with self.canvas:
            Color(*rgba)
            self._e = Ellipse(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._e.pos = self.pos
        self._e.size = self.size


class Logo(Widget):
    """The app logo (icon.png) with rounded corners."""

    def __init__(self, side=52, **kw):
        super().__init__(size_hint=(None, None), size=(dp(side), dp(side)), **kw)
        with self.canvas:
            Color(1, 1, 1, 1)
            self._r = RoundedRectangle(source="icon.png", pos=self.pos, size=self.size,
                                       radius=[dp(side * 0.24)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._r.pos = self.pos
        self._r.size = self.size


def cover(title, side=56):
    tint = COVERS[sum(ord(c) for c in title) % len(COVERS)]
    box = Surface(bg=tint, radius=side * 0.28, size_hint=(None, None), size=(dp(side), dp(side)))
    box.add_widget(Label(text=(title[:1] or "?").upper(), font_size=dp(side * 0.5), bold=True, color=DARK))
    return box


def header(title, back=None):
    bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
    if back:
        b = RoundButton("Back", bg=CARD, height=40, size_hint_x=None, width=dp(84), pos_hint={"center_y": 0.5})
        b.bind(on_release=lambda *_: back())
        bar.add_widget(b)
    bar.add_widget(label(title, 22, bold=True, height=48))
    return bar


def scroll_list():
    scroll = ScrollView()
    grid = GridLayout(cols=1, spacing=dp(10), size_hint_y=None, padding=[0, 0, 0, dp(10)])
    grid.bind(minimum_height=grid.setter("height"))
    scroll.add_widget(grid)
    return scroll, grid


class ListenButton(ButtonBehavior, Widget):
    """The big round button. It pulses while the app is listening."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.active = False
        self.phase = 0.0
        self._ev = None
        self.bind(pos=self.redraw, size=self.redraw, state=self.redraw, disabled=self.redraw)

    def set_active(self, on):
        self.active = on
        if on and not self._ev:
            self._ev = Clock.schedule_interval(self.tick, 1 / 30)
        if not on and self._ev:
            self._ev.cancel()
            self._ev = None
            self.phase = 0.0
        self.redraw()

    def tick(self, dt):
        self.phase = (self.phase + dt * 0.7) % 1
        self.redraw()

    def redraw(self, *a):
        self.canvas.clear()
        cx, cy = self.center_x, self.center_y
        r = min(self.width, self.height) * 0.30
        with self.canvas:
            if self.active:
                for offset in (0.0, 0.5):
                    p = (self.phase + offset) % 1
                    rr = r * (1 + p * 0.9)
                    Color(1, 0.35, 0.37, 0.35 * (1 - p))
                    Ellipse(pos=(cx - rr, cy - rr), size=(2 * rr, 2 * rr))
            else:
                rr = r * 1.35
                Color(1, 0.35, 0.37, 0.18)
                Ellipse(pos=(cx - rr, cy - rr), size=(2 * rr, 2 * rr))
            if self.disabled:
                Color(0.8, 0.3, 0.32, 0.6)
            elif self.state == "down":
                Color(0.8, 0.25, 0.28, 1)
            else:
                Color(*REC)
            Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
            # microphone icon
            Color(1, 1, 1, 1)
            w, h = r * 0.36, r * 0.7
            RoundedRectangle(pos=(cx - w / 2, cy - h * 0.35), size=(w, h), radius=[w / 2])
            Rectangle(pos=(cx - r * 0.04, cy - r * 0.5), size=(r * 0.08, r * 0.25))
            Rectangle(pos=(cx - r * 0.2, cy - r * 0.55), size=(r * 0.4, r * 0.07))


# ---------- phone helpers ----------
def open_url(url):
    if platform == "android":
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        activity.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    else:
        import webbrowser
        webbrowser.open(url)


def ask_mic(callback):
    """callback(True/False) is called on the main thread."""
    if platform != "android":
        callback(True)
        return
    from android.permissions import Permission, check_permission, request_permissions
    if check_permission(Permission.RECORD_AUDIO):
        callback(True)
        return
    request_permissions([Permission.RECORD_AUDIO],
                        lambda perms, grants: Clock.schedule_once(lambda dt: callback(all(grants))))


class Recorder:
    """Records the microphone to an .m4a file using Android's MediaRecorder."""

    def __init__(self, path):
        self.path = path
        self.rec = None

    def start(self):
        if platform != "android":
            raise RuntimeError("Listening only works on the phone.")
        from jnius import autoclass
        MediaRecorder = autoclass("android.media.MediaRecorder")
        Source = autoclass("android.media.MediaRecorder$AudioSource")
        Fmt = autoclass("android.media.MediaRecorder$OutputFormat")
        Enc = autoclass("android.media.MediaRecorder$AudioEncoder")
        if os.path.exists(self.path):
            os.remove(self.path)
        rec = MediaRecorder()
        rec.setAudioSource(Source.MIC)
        rec.setOutputFormat(Fmt.MPEG_4)
        rec.setAudioEncoder(Enc.AAC)
        rec.setAudioSamplingRate(44100)
        rec.setAudioEncodingBitRate(128000)
        rec.setOutputFile(self.path)
        rec.prepare()
        rec.start()
        self.rec = rec

    def stop(self):
        if self.rec:
            try:
                self.rec.stop()
            finally:
                self.rec.release()
                self.rec = None


class Player:
    """Plays a downloaded preview file using Android's MediaPlayer."""

    def __init__(self):
        self.mp = None

    def play(self, path):
        if platform != "android":
            raise RuntimeError("Previews only play on the phone.")
        from jnius import autoclass
        MediaPlayer = autoclass("android.media.MediaPlayer")
        self.stop()
        mp = MediaPlayer()
        mp.setDataSource(path)
        mp.prepare()
        mp.start()
        self.mp = mp

    def is_playing(self):
        try:
            return self.mp is not None and bool(self.mp.isPlaying())
        except Exception:  # noqa: BLE001
            return False

    def stop(self):
        if self.mp:
            try:
                self.mp.stop()
            except Exception:  # noqa: BLE001
                pass
            self.mp.release()
            self.mp = None


PLAYER = Player()


# ---------- screens ----------
class Home(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.busy = False
        root = BoxLayout(orientation="vertical", padding=[dp(20), dp(16), dp(20), dp(14)], spacing=dp(8))
        top = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(12))
        top.add_widget(Logo(52, pos_hint={"center_y": 0.5}))
        names = BoxLayout(orientation="vertical")
        names.add_widget(label("Wenzosong Detector", 22, bold=True, height=32, one_line=True))
        names.add_widget(label("Find any song in seconds", 13, DIM, height=22))
        top.add_widget(names)
        self.online_btn = RoundButton("Online", bg=VIOLET, fg=(1, 1, 1, 1), height=40, size_hint_x=None,
                                      width=dp(96), pos_hint={"center_y": 0.5})
        self.online_btn.bind(on_release=lambda *_: self.toggle_online())
        top.add_widget(self.online_btn)
        root.add_widget(top)
        self.counter = label("", 14, DIM, height=22)
        root.add_widget(self.counter)

        self.listen = ListenButton()
        self.listen.bind(on_release=lambda *_: self.start())
        root.add_widget(self.listen)

        self.status = label("Play a song near your phone, then tap the button.", 16, TEXT,
                            height=64, halign="center")
        root.add_widget(self.status)

        tabs = Surface(bg=CARD, radius=20, size_hint_y=None, height=dp(64), padding=dp(6), spacing=dp(6))
        for name, target in (("History", "history"), ("Library", "library"), ("Settings", "settings")):
            t = RoundButton(name, bg=CLEAR, fg=DIM, height=52)
            t.bind(on_release=lambda _b, tg=target: App.get_running_app().go(tg))
            tabs.add_widget(t)
        root.add_widget(tabs)
        self.add_widget(root)

    def refresh_online(self):
        on = online_on()
        self.online_btn.text = "Online" if on else "Offline"
        self.online_btn.color = (1, 1, 1, 1) if on else DIM
        self.online_btn.bg = VIOLET if on else CARD
        self.online_btn._paint()

    def toggle_online(self):
        set_online(not online_on())
        self.on_pre_enter()
        if online_on():
            self.set_status("Online mode is on. Tap the button to detect a song.")
        else:
            self.set_status("Online mode is off. Tap Offline at the top to turn it on.")

    def on_pre_enter(self, *a):
        self.refresh_online()
        s = core.get_settings()
        if not online_on():
            self.counter.text = "Offline: turn Online on at the top to detect songs."
        elif not (s["audd_token"] or s["acr_key"]):
            self.counter.text = "Open Settings and add your AudD token or ACRCloud keys first."
        elif s["audd_token"] or not s["acr_key"]:
            self.counter.text = f"AudD detections today: {core.usage_today()} of {core.AUDD_DAILY_LIMIT}"
        else:
            self.counter.text = "Detecting with ACRCloud"

    def set_status(self, text):
        self.status.text = text

    def start(self):
        if self.busy:
            return
        if not online_on():
            self.set_status("Online mode is off. Tap Offline at the top to turn it on.")
            return
        ask_mic(self._after_permission)

    def _after_permission(self, ok):
        if not ok:
            self.set_status("The microphone is blocked. Allow it in Android Settings, Apps, Song Detector.")
            return
        self.run(record_first=True, over=False)

    def run(self, record_first, over):
        self.busy = True
        self.listen.disabled = True
        self.listen.set_active(True)
        threading.Thread(target=self._work, args=(record_first, over), daemon=True).start()

    def post(self, fn, *args):
        Clock.schedule_once(lambda dt: fn(*args))

    def _work(self, record_first, over):
        path = os.path.join(App.get_running_app().user_data_dir, "clip.m4a")
        try:
            if record_first:
                rec = Recorder(path)
                rec.start()
                for i in range(SECONDS, 0, -1):
                    self.post(self.set_status, f"Listening... {i}")
                    time.sleep(1)
                rec.stop()
            self.post(self.set_status, "Identifying...")
            entry, msg, code = core.detect(path, over)
        except Exception as err:  # noqa: BLE001 - show any problem on screen
            entry, msg, code = None, f"Something went wrong: {err}", "error"
        self.post(self.finish, entry, msg, code)

    def finish(self, entry, msg, code):
        self.busy = False
        self.listen.disabled = False
        self.listen.set_active(False)
        self.on_pre_enter()
        if code == "ok":
            core.add_history(entry)
            self.set_status("Found it! Saved to history.")
            App.get_running_app().open_song(entry, "home")
        elif code == "limit":
            self.set_status("Daily AudD limit reached.")
            self.ask_over_limit(msg)
        else:
            self.set_status(msg)

    def ask_over_limit(self, msg):
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        box.add_widget(Label(text=msg + "\nTry anyway?", halign="center"))
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(10))
        pop = Popup(title="Daily limit", content=box, size_hint=(0.9, 0.4), auto_dismiss=False)
        yes, no = Button(text="Try anyway"), Button(text="Cancel")
        yes.bind(on_release=lambda *_: (pop.dismiss(), self.run(False, True)))
        no.bind(on_release=lambda *_: pop.dismiss())
        row.add_widget(yes)
        row.add_widget(no)
        box.add_widget(row)
        pop.open()


class SongScreen(Screen):
    back = "home"
    loading = False
    poll = None

    def show(self, entry, back):
        self.stop_preview()
        self.entry, self.back = entry, back
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=[dp(20), dp(16), dp(20), dp(14)], spacing=dp(10))
        root.add_widget(header("Song found", lambda: App.get_running_app().go(self.back)))

        card = Surface(bg=CARD, radius=20, size_hint_y=None, height=dp(120), padding=dp(16), spacing=dp(16))
        card.add_widget(cover(entry["title"], 88))
        info = BoxLayout(orientation="vertical", spacing=dp(2))
        info.add_widget(label(entry["title"], 20, bold=True, height=30, one_line=True))
        info.add_widget(label(entry["artist"], 16, AMBER, height=26, one_line=True))
        if entry.get("album"):
            info.add_widget(label(entry["album"], 13, DIM, height=22, one_line=True))
        card.add_widget(info)
        root.add_widget(card)

        root.add_widget(label("Open this song on", 15, DIM, height=24))
        scroll, grid = scroll_list()
        items = core.sources(entry)
        web = "https://www.google.com/search?q=" + quote_plus(f"{entry['artist']} {entry['title']} song")
        items.insert(1, ("Search the web", web))
        for name, url in items:
            colour = next((c for key, c in SERVICES.items() if key in name), AMBER)
            row = Row(bg=CARD, radius=14, size_hint_y=None, height=dp(56), padding=[dp(16), 0, dp(16), 0],
                      spacing=dp(14))
            row.add_widget(Dot(colour, pos_hint={"center_y": 0.5}))
            row.add_widget(label(name, 16, TEXT, bold=True, height=56, one_line=True))
            row.add_widget(label(">", 18, DIM, height=56, halign="right"))
            row.children[0].size_hint_x = None
            row.children[0].width = dp(20)
            row.bind(on_release=lambda _r, u=url: open_url(u))
            grid.add_widget(row)
        root.add_widget(scroll)

        self.note = label("", 13, DIM, height=20, halign="center")
        root.add_widget(self.note)
        self.preview_btn = RoundButton("Play 30-second preview", bg=CARD, fg=TEXT)
        self.preview_btn.bind(on_release=lambda *_: self.toggle_preview())
        root.add_widget(self.preview_btn)
        self.save_btn = RoundButton("", bg=AMBER, fg=DARK)
        self.save_btn.bind(on_release=lambda *_: self.toggle())
        root.add_widget(self.save_btn)
        self.refresh_save()
        self.add_widget(root)

    def on_leave(self, *a):
        self.stop_preview()

    # ----- 30-second preview -----
    def toggle_preview(self):
        if self.loading:
            return
        if PLAYER.is_playing():
            self.stop_preview()
            return
        if not online_on():
            self.note.text = "Online mode is off. Turn it on at the top of the home screen."
            return
        self.loading = True
        self.preview_btn.text = "Loading preview..."
        self.note.text = ""
        threading.Thread(target=self._fetch_preview, args=(self.entry,), daemon=True).start()

    def _fetch_preview(self, entry):
        path = os.path.join(App.get_running_app().user_data_dir, "preview.m4a")
        error = None
        try:
            url = preview.find_preview(entry["artist"], entry["title"])
            if not url:
                error = "No preview is available for this song."
            else:
                preview.download(url, path)
        except Exception:  # noqa: BLE001
            error = "Could not load the preview. Check your internet."
        if error:
            Clock.schedule_once(lambda dt: self._preview_failed(error))
        else:
            Clock.schedule_once(lambda dt: self._play(path, entry))

    def _preview_failed(self, message):
        self.loading = False
        self.preview_btn.text = "Play 30-second preview"
        self.note.text = message

    def _play(self, path, entry):
        self.loading = False
        if entry is not self.entry or self.manager.current != "song":
            return
        try:
            PLAYER.play(path)
        except Exception as err:  # noqa: BLE001
            self._preview_failed(f"Could not play the preview: {err}")
            return
        self.preview_btn.text = "Stop preview"
        self.note.text = "Playing a 30-second preview from Apple's iTunes"
        self.poll = Clock.schedule_interval(self._check, 0.5)

    def _check(self, dt):
        if not PLAYER.is_playing():
            self.stop_preview()

    def stop_preview(self):
        PLAYER.stop()
        if self.poll:
            self.poll.cancel()
            self.poll = None
        self.loading = False
        if hasattr(self, "preview_btn"):
            self.preview_btn.text = "Play 30-second preview"
            self.note.text = ""

    def refresh_save(self):
        self.save_btn.text = "Remove from library" if core.in_library(self.entry) else "Save to library"

    def toggle(self):
        if core.in_library(self.entry):
            core.remove_library(self.entry)
        else:
            core.add_library(self.entry)
        self.refresh_save()


ACCENT = globals().get("VIOLET_L") or globals().get("AMBER")
DANGER = globals().get("RED") or globals().get("REC")
AUDIO_EXT = (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus")


def ask_storage(callback):
    """Ask Android for permission to read music files. callback(True/False) runs on the main thread."""
    if platform != "android":
        callback(True)
        return
    from android.permissions import check_permission, request_permissions
    wanted = ["android.permission.READ_MEDIA_AUDIO", "android.permission.READ_EXTERNAL_STORAGE"]
    try:
        if any(check_permission(p) for p in wanted):
            callback(True)
            return
    except Exception:  # noqa: BLE001
        pass
    request_permissions(wanted, lambda perms, grants: Clock.schedule_once(lambda dt: callback(any(grants))))


class ListScreen(Screen):
    SCAN_ROOTS = ("/storage/emulated/0", "/sdcard")
    MAX_DEPTH = 5
    MAX_FILES = 1500
    MIN_BYTES = 300 * 1024          # skip tiny files like ringtones and voice notes

    def __init__(self, mode, **kw):
        super().__init__(**kw)
        self.mode = mode
        self._poll = None
        self._playing_path = None
        self._scan_id = 0

    # ----- building the screen -----
    def on_pre_enter(self, *a):
        self.clear_widgets()
        self.stop_local()
        root = BoxLayout(orientation="vertical", padding=[dp(20), dp(16), dp(20), dp(14)], spacing=dp(12))
        root.add_widget(header(self.mode.capitalize(), lambda: App.get_running_app().go("home")))
        scroll, grid = scroll_list()
        if self.mode == "library":
            self.now = label("", 13, ACCENT, height=22)
            root.add_widget(self.now)
            self._fill_library(grid)
            root.add_widget(scroll)
            self.add_widget(root)
            self._start_scan()
            return
        items = list(reversed(core.get_history()))
        if not items:
            grid.add_widget(label("Nothing here yet. Detect a song and it will appear here.", 16, DIM))
        for e in items:
            row = Row(bg=CARD, radius=16, size_hint_y=None, height=dp(76), padding=dp(10), spacing=dp(14))
            row.add_widget(cover(e["title"], 54))
            info = BoxLayout(orientation="vertical", spacing=dp(2))
            info.add_widget(label(e["title"], 16, bold=True, height=26, one_line=True))
            info.add_widget(label(e["artist"] + f"  -  {e['date']}", 13, DIM, height=22, one_line=True))
            row.add_widget(info)
            row.bind(on_release=lambda _r, entry=e: App.get_running_app().open_song(entry, self.mode))
            grid.add_widget(row)
        root.add_widget(scroll)
        if items:
            clear = RoundButton("Clear history", bg=CARD, fg=DANGER)
            clear.bind(on_release=lambda *_: (core.clear_history(), self.on_pre_enter()))
            root.add_widget(clear)
        self.add_widget(root)

    def _fill_library(self, grid):
        saved = list(reversed(core.get_library()))
        grid.add_widget(label("Saved Songs", 16, ACCENT, height=30, bold=True))
        if not saved:
            grid.add_widget(label("No saved songs yet. Tap the heart on a detected song.", 14, DIM))
        for e in saved:
            row = Row(bg=CARD, radius=16, size_hint_y=None, height=dp(76), padding=dp(10), spacing=dp(14))
            row.add_widget(cover(e["title"], 54))
            info = BoxLayout(orientation="vertical", spacing=dp(2))
            info.add_widget(label(e["title"], 16, bold=True, height=26, one_line=True))
            info.add_widget(label(e["artist"], 13, DIM, height=22, one_line=True))
            row.add_widget(info)
            row.bind(on_release=lambda _r, entry=e: App.get_running_app().open_song(entry, self.mode))
            grid.add_widget(row)
        grid.add_widget(label("", 10, height=14))
        grid.add_widget(label("On this phone", 16, ACCENT, height=30, bold=True))
        self.grid = grid
        self.local_status = label("Looking for music on your phone...", 14, DIM)
        grid.add_widget(self.local_status)
        self.allow_btn = None

    # ----- finding music on the phone -----
    def _start_scan(self):
        self._scan_id += 1
        ask_storage(self._on_storage)

    def _on_storage(self, ok):
        if not ok:
            self.local_status.text = ("Music access is blocked. Tap the button, or allow it in\n"
                                      "Android Settings, Apps, this app, Permissions.")
            if not self.allow_btn:
                self.allow_btn = RoundButton("Allow music access", bg=CARD, fg=ACCENT)
                self.allow_btn.bind(on_release=lambda *_: self._start_scan())
                self.grid.add_widget(self.allow_btn)
            return
        if self.allow_btn:
            self.grid.remove_widget(self.allow_btn)
            self.allow_btn = None
        self.local_status.text = "Looking for music on your phone..."
        threading.Thread(target=self._scan_thread, args=(self._scan_id,), daemon=True).start()

    def _scan_thread(self, sid):
        songs = self.scan_local_music()
        Clock.schedule_once(lambda dt: self._show_local(songs, sid))

    def scan_local_music(self):
        """Look through the phone's storage for music files (runs in the background)."""
        found, seen = [], set()
        for base in self.SCAN_ROOTS:
            if not os.path.isdir(base):
                continue
            base_depth = base.rstrip(os.sep).count(os.sep)
            for folder, dirs, files in os.walk(base):
                depth = folder.rstrip(os.sep).count(os.sep) - base_depth
                if depth >= self.MAX_DEPTH:
                    dirs[:] = []
                else:
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d != "Android"]
                for name in files:
                    if not name.lower().endswith(AUDIO_EXT):
                        continue
                    path = os.path.join(folder, name)
                    real = os.path.realpath(path)
                    if real in seen:
                        continue
                    try:
                        if os.path.getsize(path) < self.MIN_BYTES:
                            continue
                    except OSError:
                        continue
                    seen.add(real)
                    found.append({"title": os.path.splitext(name)[0], "path": path})
                    if len(found) >= self.MAX_FILES:
                        return sorted(found, key=lambda s: s["title"].lower())
            if found:
                break               # /sdcard is the same place as /storage/emulated/0
        return sorted(found, key=lambda s: s["title"].lower())

    def _show_local(self, songs, sid):
        if sid != self._scan_id or self.mode != "library" or self.manager is None \
                or self.manager.current != self.name:
            return
        if not songs:
            self.local_status.text = ("No music files found on this phone yet.\n"
                                      "Songs saved in Music or Download will appear here.")
            return
        self.local_status.text = f"{len(songs)} songs found. Tap one to play it, tap again to stop."
        for song in songs:
            row = Row(bg=CARD, radius=14, size_hint_y=None, height=dp(64), padding=dp(10), spacing=dp(12))
            row.add_widget(cover(song["title"], 44))
            info = BoxLayout(orientation="vertical", spacing=dp(1))
            info.add_widget(label(song["title"], 15, bold=True, height=26, one_line=True))
            info.add_widget(label(os.path.basename(os.path.dirname(song["path"])), 12, DIM, height=20, one_line=True))
            row.add_widget(info)
            row.bind(on_release=lambda _r, p=song["path"], t=song["title"]: self.play_local(p, t))
            self.grid.add_widget(row)

    # ----- playing a song from the phone -----
    def play_local(self, path, title):
        if PLAYER.is_playing() and self._playing_path == path:
            self.stop_local()
            return
        try:
            PLAYER.play(path)
        except Exception as err:  # noqa: BLE001
            self.now.text = f"Could not play this file: {err}"
            return
        self._playing_path = path
        self.now.text = f"Playing: {title}"
        if not self._poll:
            self._poll = Clock.schedule_interval(self._check, 0.5)

    def _check(self, dt):
        if not PLAYER.is_playing():
            self.stop_local()

    def stop_local(self):
        PLAYER.stop()
        if self._poll:
            self._poll.cancel()
            self._poll = None
        self._playing_path = None
        if hasattr(self, "now") and self.mode == "library":
            self.now.text = ""

    def on_leave(self, *a):
        self.stop_local()


class SettingsScreen(Screen):
    FIELDS = (("audd_token", "AudD token", "Paste your AudD token"),
              ("acr_host", "ACRCloud host", "like identify-eu-west-1.acrcloud.com"),
              ("acr_key", "ACRCloud access key", "Paste the access key"),
              ("acr_secret", "ACRCloud access secret", "Paste the access secret"))

    def on_pre_enter(self, *a):
        self.clear_widgets()
        s = core.get_settings()
        root = BoxLayout(orientation="vertical", padding=[dp(20), dp(16), dp(20), dp(14)], spacing=dp(8))
        root.add_widget(header("Settings", lambda: App.get_running_app().go("home")))
        root.add_widget(label("Your keys stay on this phone. Paste them here once.", 14, DIM))
        scroll, grid = scroll_list()
        self.inputs = {}
        for key, title, hint in self.FIELDS:
            grid.add_widget(label(title, 14, DIM, height=22))
            ti = TextInput(text=s[key], hint_text=hint, multiline=False, size_hint_y=None, height=dp(50),
                           write_tab=False, font_size=dp(15), background_normal="", background_active="",
                           background_color=CARD, foreground_color=TEXT, cursor_color=AMBER,
                           hint_text_color=DIM, padding=[dp(14), dp(14), dp(14), dp(12)])
            self.inputs[key] = ti
            grid.add_widget(ti)
        root.add_widget(scroll)
        save = RoundButton("Save", bg=AMBER, fg=DARK)
        save.bind(on_release=lambda *_: self.save())
        root.add_widget(save)
        self.add_widget(root)

    def save(self):
        core.save_settings({k: ti.text for k, ti in self.inputs.items()})
        App.get_running_app().go("home")


class SongApp(App):
    title = "Wenzosong Detector"

    def build(self):
        core.DATA_DIR = self.user_data_dir
        Window.clearcolor = BG
        Window.softinput_mode = "below_target"
        self.sm = ScreenManager(transition=NoTransition())
        self.sm.add_widget(Home(name="home"))
        self.sm.add_widget(SongScreen(name="song"))
        self.sm.add_widget(ListScreen("history", name="history"))
        self.sm.add_widget(ListScreen("library", name="library"))
        self.sm.add_widget(SettingsScreen(name="settings"))
        Window.bind(on_keyboard=self.on_key)
        root = Backdrop()
        root.add_widget(self.sm)
        return root

    def go(self, name):
        self.sm.current = name

    def open_song(self, entry, back):
        self.sm.get_screen("song").show(entry, back)
        self.sm.current = "song"

    def on_key(self, window, key, *args):
        if key == 27:  # Android back button
            if self.sm.current == "song":
                self.sm.current = self.sm.get_screen("song").back
                return True
            if self.sm.current != "home":
                self.sm.current = "home"
                return True
        return False


class CrashApp(App):
    """Shown only if the app crashes: the error text can be copied and sent for help."""
    title = "Error"

    def __init__(self, text, **kw):
        super().__init__(**kw)
        self.error_text = text

    def build(self):
        Window.clearcolor = (0.12, 0.03, 0.06, 1)
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        note = Label(text="The app hit an error.\nPress and hold the text below, choose Select all, Copy,\n"
                          "and send it to Claude.", size_hint_y=None, height=dp(90), halign="center")
        note.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
        box.add_widget(note)
        box.add_widget(TextInput(text=self.error_text, readonly=True, font_size=dp(12)))
        return box


if __name__ == "__main__":
    try:
        SongApp().run()
    except Exception:
        import traceback
        CrashApp(traceback.format_exc()).run()
