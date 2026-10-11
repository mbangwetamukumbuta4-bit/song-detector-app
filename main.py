"""Wenzosong Detector - Android app (Kivy). Logic lives in core.py and preview.py."""
import math
import os
import threading
import time
from urllib.parse import quote_plus

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Mesh, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
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

# ---------- colours (neon violet and blue on near-black) ----------
BG = (0.031, 0.027, 0.063, 1)
CARD = (0.063, 0.055, 0.118, 1)
EDGE = (0.45, 0.35, 1, 0.55)
TEXT = (0.94, 0.91, 1, 1)
DIM = (0.55, 0.58, 0.86, 1)
VIOLET = (0.56, 0.33, 1, 1)
VIOLET_L = (0.74, 0.58, 1, 1)
BLUE = (0.28, 0.40, 1, 1)
WHITE = (1, 1, 1, 1)
RED = (1, 0.38, 0.45, 1)
CLEAR = (0, 0, 0, 0)
COVERS = [(0.56, 0.33, 1, 1), (0.28, 0.40, 1, 1), (0.85, 0.35, 0.85, 1),
          (0.25, 0.75, 0.85, 1), (0.45, 0.55, 1, 1), (0.70, 0.45, 1, 1)]
SERVICES = {"YouTube": (1, 0.25, 0.25, 1), "Spotify": (0.12, 0.84, 0.38, 1),
            "Apple Music": (0.98, 0.34, 0.5, 1), "Boomplay": (0.2, 0.6, 1, 1),
            "Audiomack": (1, 0.62, 0.1, 1), "Search": (0.62, 0.68, 0.78, 1)}


def mix(c1, c2, t):
    return tuple(a + (b - a) * t for a, b in zip(c1, c2))


def online_on():
    """The Online switch at the top of the home screen (remembered between launches)."""
    data = core.load("online.json", {})
    return bool(data.get("on", True)) if isinstance(data, dict) else True


def set_online(value):
    core.save("online.json", {"on": bool(value)})


def fmt_time(seconds):
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


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
    """A box with a rounded background and an optional glowing outline."""

    def __init__(self, bg=CARD, radius=16, outline=None, **kw):
        super().__init__(**kw)
        self._radius = dp(radius)
        with self.canvas.before:
            self._color = Color(*bg)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[self._radius])
        self._line = None
        if outline:
            with self.canvas.after:
                Color(*outline)
                self._line = Line(rounded_rectangle=(self.x, self.y, self.width, self.height, self._radius),
                                  width=dp(1.2))
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._rect.pos = self.pos
        self._rect.size = self.size
        if self._line:
            self._line.rounded_rectangle = (self.x, self.y, self.width, self.height, self._radius)

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
        if self.state == "down":
            self.set_bg((r * 0.8 + 0.05, g * 0.8 + 0.05, b * 0.8 + 0.1, max(al, 0.5)))
        else:
            self.set_bg(self._base)


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
    """The app logo (icon.png) in a circle with a violet ring."""

    def __init__(self, side=52, **kw):
        super().__init__(size_hint=(None, None), size=(dp(side), dp(side)), **kw)
        with self.canvas:
            Color(1, 1, 1, 1)
            self._img = Ellipse(source="icon.png", pos=self.pos, size=self.size)
            Color(*VIOLET_L)
            self._ring = Line(circle=(self.center_x, self.center_y, min(self.width, self.height) / 2),
                              width=dp(1.8))
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._img.pos = self.pos
        self._img.size = self.size
        self._ring.circle = (self.center_x, self.center_y, min(self.width, self.height) / 2)


def cover(title, side=56):
    tint = COVERS[sum(ord(c) for c in title) % len(COVERS)]
    box = Surface(bg=tint, radius=side * 0.28, size_hint=(None, None), size=(dp(side), dp(side)))
    box.add_widget(Label(text=(title[:1] or "?").upper(), font_size=dp(side * 0.5), bold=True, color=WHITE))
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


def heart_points(cx, cy, size, n=48):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * size / 34.0, cy + (y + 1.5) * size / 34.0))
    return pts


class Icon(Widget):
    """Small line icons drawn with the canvas: clock, library, gear, heart, play, pause."""

    def __init__(self, kind, color=VIOLET_L, filled=False, **kw):
        super().__init__(**kw)
        self.kind, self.color, self.filled = kind, color, filled
        self.bind(pos=self.redraw, size=self.redraw)
        self.redraw()

    def set(self, kind=None, color=None, filled=None):
        if kind is not None:
            self.kind = kind
        if color is not None:
            self.color = color
        if filled is not None:
            self.filled = filled
        self.redraw()

    def redraw(self, *a):
        self.canvas.clear()
        cx, cy = self.center_x, self.center_y
        r = min(self.width, self.height) / 2 * 0.82
        w = dp(1.8)
        with self.canvas:
            Color(*self.color)
            if self.kind == "clock":
                Line(circle=(cx, cy, r), width=w)
                Line(points=[cx, cy + r * 0.55, cx, cy, cx + r * 0.45, cy - r * 0.25], width=w, joint="round")
            elif self.kind == "library":
                Line(points=[cx - r, cy + 0.35 * r, cx, cy + 0.8 * r, cx + r, cy + 0.35 * r, cx, cy - 0.1 * r],
                     width=w, close=True, joint="round")
                Line(points=[cx - r, cy - 0.05 * r, cx, cy - 0.5 * r, cx + r, cy - 0.05 * r], width=w, joint="round")
                Line(points=[cx - r, cy - 0.45 * r, cx, cy - 0.9 * r, cx + r, cy - 0.45 * r], width=w, joint="round")
            elif self.kind == "gear":
                Line(circle=(cx, cy, r * 0.52), width=w)
                Line(circle=(cx, cy, r * 0.2), width=w)
                for i in range(8):
                    a = i * math.pi / 4
                    Line(points=[cx + r * 0.62 * math.cos(a), cy + r * 0.62 * math.sin(a),
                                 cx + r * 0.95 * math.cos(a), cy + r * 0.95 * math.sin(a)], width=dp(2.6))
            elif self.kind == "heart":
                pts = heart_points(cx, cy, r * 2)
                if self.filled:
                    verts = [cx, cy, 0, 0]
                    for x, y in pts + [pts[0]]:
                        verts += [x, y, 0, 0]
                    Mesh(vertices=verts, indices=list(range(len(pts) + 2)), mode="triangle_fan")
                else:
                    flat = [v for p in pts for v in p]
                    Line(points=flat, width=w, close=True, joint="round")
            elif self.kind in ("wifi", "wifi_off"):
                dx, dy = cx, cy - r * 0.55
                Ellipse(pos=(dx - r * 0.12, dy - r * 0.12), size=(r * 0.24, r * 0.24))
                for rad in (0.5, 0.95, 1.4):
                    pts = []
                    for k in range(13):
                        ang = math.radians(42 + 96 * k / 12.0)
                        pts += [dx + r * rad * math.cos(ang), dy + r * rad * math.sin(ang)]
                    Line(points=pts, width=w, joint="round", cap="round")
                if self.kind == "wifi_off":
                    Line(points=[cx - r * 1.0, cy + r * 0.95, cx + r * 1.0, cy - r * 0.95], width=dp(2.2), cap="round")
            elif self.kind == "play":
                Triangle(points=[cx - r * 0.3, cy - r * 0.55, cx - r * 0.3, cy + r * 0.55, cx + r * 0.55, cy])
            elif self.kind == "pause":
                Rectangle(pos=(cx - r * 0.45, cy - r * 0.55), size=(r * 0.3, r * 1.1))
                Rectangle(pos=(cx + r * 0.15, cy - r * 0.55), size=(r * 0.3, r * 1.1))


class CircleButton(ButtonBehavior, Widget):
    """A round button with an icon: a filled gradient one (play) or an outlined one (heart)."""

    def __init__(self, kind, side=52, filled=True, **kw):
        super().__init__(size_hint=(None, None), size=(dp(side), dp(side)), **kw)
        self.kind, self.filled, self.on = kind, filled, False
        self.bind(pos=self.redraw, size=self.redraw, state=self.redraw, disabled=self.redraw)
        self.redraw()

    def set(self, kind=None, on=None):
        if kind is not None:
            self.kind = kind
        if on is not None:
            self.on = on
        self.redraw()

    def redraw(self, *a):
        self.canvas.clear()
        cx, cy = self.center_x, self.center_y
        r = min(self.width, self.height) / 2
        fade = 0.35 if self.disabled else 1.0
        down = 0.85 if self.state == "down" else 1.0
        with self.canvas:
            if self.filled:
                Color(BLUE[0] * down, BLUE[1] * down, BLUE[2] * down, fade)
                Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
                Color(VIOLET[0] * down, VIOLET[1] * down, VIOLET[2] * down, 0.9 * fade)
                Ellipse(pos=(cx - r * 0.95, cy - r * 0.78), size=(r * 1.55, r * 1.55))
                glyph = (1, 1, 1, fade)
            else:
                Color(VIOLET[0], VIOLET[1], VIOLET[2], fade)
                Line(circle=(cx, cy, r - dp(1)), width=dp(1.4))
                glyph = (VIOLET[0], VIOLET[1], VIOLET[2], fade)
        icon = Icon(self.kind, glyph, filled=(self.kind == "heart" and self.on),
                    size_hint=(None, None), size=(r * 1.1, r * 1.1))
        icon.center = (cx, cy)
        icon.redraw()
        # copy the icon's drawing onto this button
        self.canvas.add(icon.canvas)


class ProgressBar(Widget):
    def __init__(self, **kw):
        super().__init__(size_hint_y=None, height=dp(6), **kw)
        self.fraction = 0.0
        self.bind(pos=self.redraw, size=self.redraw)
        self.redraw()

    def set(self, fraction):
        self.fraction = max(0.0, min(1.0, fraction))
        self.redraw()

    def redraw(self, *a):
        self.canvas.clear()
        h = self.height
        with self.canvas:
            Color(1, 1, 1, 0.12)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[h / 2])
            if self.fraction > 0:
                Color(*VIOLET)
                RoundedRectangle(pos=self.pos, size=(max(h, self.width * self.fraction), h), radius=[h / 2])


class Handle(Widget):
    def __init__(self, **kw):
        super().__init__(size_hint=(None, None), size=(dp(44), dp(5)), **kw)
        with self.canvas:
            Color(1, 1, 1, 0.16)
            self._r = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(2.5)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *a):
        self._r.pos = self.pos
        self._r.size = self.size


# ---------- the big listening orb ----------
class ListenButton(ButtonBehavior, Widget):
    """A glowing orb with a circular equaliser. It reacts to the microphone while listening."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.active = False
        self.phase = 0.0
        self.level = 0.0
        self.target = 0.0
        self._ev = None
        self.bind(pos=self.redraw, size=self.redraw, state=self.redraw, disabled=self.redraw)

    def set_level(self, value):
        self.target = max(0.0, min(1.0, value))

    def set_active(self, on):
        self.active = on
        if on and not self._ev:
            self._ev = Clock.schedule_interval(self.tick, 1 / 30)
        if not on and self._ev:
            self._ev.cancel()
            self._ev = None
            self.phase = 0.0
            self.level = 0.0
            self.target = 0.0
        self.redraw()

    def tick(self, dt):
        self.phase = (self.phase + dt * 0.6) % 1
        self.level += (self.target - self.level) * 0.35
        self.redraw()

    def redraw(self, *a):
        self.canvas.clear()
        cx, cy = self.center_x, self.center_y
        base = min(self.width, self.height)
        R = base * 0.20
        ph = self.phase
        lvl = self.level if self.active else 0.0
        fade = 0.6 if self.disabled and not self.active else 1.0
        with self.canvas:
            # soft glow behind the orb
            for k in range(10):
                Color(0.45, 0.30, 1, 0.045)
                rr = R * (2.1 - k * 0.09)
                Ellipse(pos=(cx - rr, cy - rr), size=(2 * rr, 2 * rr))
            # thin glowing rings
            for f, al in ((1.42, 0.55), (1.72, 0.35), (2.05, 0.22), (2.4, 0.12)):
                rr = R * f
                Color(0.5, 0.35, 1, al * 0.35)
                Line(circle=(cx, cy, rr), width=dp(4))
                Color(0.62, 0.5, 1, al)
                Line(circle=(cx, cy, rr), width=dp(1))
            if self.active:   # expanding pulse rings
                for off in (0.0, 0.5):
                    p = (ph + off) % 1
                    Color(0.6, 0.45, 1, 0.5 * (1 - p))
                    Line(circle=(cx, cy, R * (1.4 + p * 1.2)), width=dp(2))
            # circular equaliser bars
            n = 72
            for i in range(n):
                a = 2 * math.pi * i / n
                wave = 0.5 + 0.5 * math.sin(a * 5 + ph * 6.283) * (0.6 + 0.4 * math.sin(a * 11 - ph * 9.0))
                amp = 0.18 + 0.82 * wave * (0.25 + 0.75 * lvl)
                r1 = R * 1.5
                r2 = r1 + base * (0.012 + 0.11 * amp)
                col = mix(VIOLET, BLUE, 0.5 + 0.5 * math.sin(a))
                Color(col[0], col[1], col[2], 0.55 + 0.45 * amp)
                Line(points=[cx + r1 * math.cos(a), cy + r1 * math.sin(a),
                             cx + r2 * math.cos(a), cy + r2 * math.sin(a)], width=dp(1.6))
            # side waveform bars
            span = self.width / 2 - R * 2.15 - dp(4)
            if span > dp(8):
                m = 16
                for side in (-1, 1):
                    for j in range(m):
                        x = cx + side * (R * 2.15 + span * j / m)
                        fall = 1 - j / m
                        hgt = base * 0.01 + base * 0.16 * fall * (0.25 + 0.75 * lvl) * \
                            (0.5 + 0.5 * math.sin(j * 1.7 + ph * 8 + side))
                        Color(0.6, 0.45, 1, 0.25 + 0.6 * fall)
                        Line(points=[x, cy - hgt, x, cy + hgt], width=dp(1.4))
            # the orb: violet at the centre, blue at the edge
            steps = 26
            for k in range(steps):
                t = k / (steps - 1)
                col = mix(BLUE, VIOLET_L, t)
                rr = R * (1 - 0.9 * t) * (1 + 0.04 * lvl)
                ofs = R * 0.22 * t
                Color(col[0], col[1], col[2], fade)
                Ellipse(pos=(cx - rr - ofs, cy - rr + ofs), size=(2 * rr, 2 * rr))
            # microphone
            Color(1, 1, 1, 0.95 * fade)
            w, h = R * 0.34, R * 0.62
            RoundedRectangle(pos=(cx - w / 2, cy - h * 0.2), size=(w, h), radius=[w / 2])
            Line(points=[cx - w * 0.95, cy + h * 0.25, cx - w * 0.95, cy - h * 0.15, cx - w * 0.55, cy - h * 0.40,
                         cx + w * 0.55, cy - h * 0.40, cx + w * 0.95, cy - h * 0.15, cx + w * 0.95, cy + h * 0.25],
                 width=dp(1.6), joint="round")
            Line(points=[cx, cy - h * 0.40, cx, cy - h * 0.62], width=dp(1.6))
            Line(points=[cx - w * 0.5, cy - h * 0.62, cx + w * 0.5, cy - h * 0.62], width=dp(1.6))


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

    def level(self):
        """How loud it is right now, from 0 to 1."""
        try:
            if self.rec:
                return min(1.0, (self.rec.getMaxAmplitude() / 14000.0) ** 0.6)
        except Exception:  # noqa: BLE001
            pass
        return 0.0

    def stop(self):
        if self.rec:
            rec, self.rec = self.rec, None
            try:
                rec.stop()
            finally:
                rec.release()


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

    def position_ms(self):
        try:
            return int(self.mp.getCurrentPosition()) if self.mp else 0
        except Exception:  # noqa: BLE001
            return 0

    def duration_ms(self):
        try:
            return int(self.mp.getDuration()) if self.mp else 0
        except Exception:  # noqa: BLE001
            return 0

    def stop(self):
        if self.mp:
            try:
                self.mp.stop()
            except Exception:  # noqa: BLE001
                pass
            self.mp.release()
            self.mp = None


PLAYER = Player()


class PreviewController:
    """Finds, downloads and plays the 30-second preview. The screen gets callbacks."""

    def __init__(self, on_change):
        self.on_change = on_change      # on_change(state, text): loading / playing / progress / error / idle
        self.entry = None
        self.loading = False
        self.poll = None

    def toggle(self, entry):
        if self.loading:
            return
        if PLAYER.is_playing():
            self.stop()
            return
        if not online_on():
            self.on_change("error", "Online mode is off. Turn it on at the top right of the home screen.")
            return
        self.entry = entry
        self.loading = True
        self.on_change("loading", "Loading preview...")
        threading.Thread(target=self._fetch, args=(entry,), daemon=True).start()

    def _fetch(self, entry):
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
            Clock.schedule_once(lambda dt: self._failed(error))
        else:
            Clock.schedule_once(lambda dt: self._ready(path, entry))

    def _failed(self, message):
        self.loading = False
        self.on_change("error", message)

    def _ready(self, path, entry):
        self.loading = False
        if entry is not self.entry:
            self.on_change("idle", "")
            return
        try:
            PLAYER.play(path)
        except Exception as err:  # noqa: BLE001
            self.on_change("error", f"Could not play the preview: {err}")
            return
        self.on_change("playing", "Playing a 30-second preview")
        self.poll = Clock.schedule_interval(self._tick, 0.25)

    def _tick(self, dt):
        if not PLAYER.is_playing():
            self.stop()
        else:
            self.on_change("progress", "")

    def stop(self):
        PLAYER.stop()
        if self.poll:
            self.poll.cancel()
            self.poll = None
        self.loading = False
        self.on_change("idle", "")


# ---------- the mini player on the home screen ----------
class MiniPlayer(Surface):
    def __init__(self, on_open, notify, **kw):
        super().__init__(bg=CARD, radius=26, outline=EDGE, orientation="vertical", size_hint_y=None,
                         height=dp(170), padding=[dp(16), dp(8), dp(16), dp(12)], spacing=dp(6), **kw)
        self.entry = None
        self.on_open, self.notify = on_open, notify
        self.ctrl = PreviewController(self._on_change)

        self.add_widget(Handle(pos_hint={"center_x": 0.5}))
        row = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(12))
        self.cover_box = BoxLayout(size_hint=(None, None), size=(dp(56), dp(56)), pos_hint={"center_y": 0.5})
        row.add_widget(self.cover_box)
        self.info = Row(bg=CLEAR, orientation="vertical", spacing=dp(2), padding=0)
        self.title = label("", 18, TEXT, bold=True, height=28, one_line=True)
        self.artist = label("", 15, VIOLET_L, height=24, one_line=True)
        self.info.add_widget(self.title)
        self.info.add_widget(self.artist)
        self.info.bind(on_release=lambda *_: self.entry and self.on_open(self.entry))
        row.add_widget(self.info)
        self.play = CircleButton("play", 52, filled=True, pos_hint={"center_y": 0.5})
        self.play.bind(on_release=lambda *_: self.entry and self.ctrl.toggle(self.entry))
        row.add_widget(self.play)
        self.heart = CircleButton("heart", 44, filled=False, pos_hint={"center_y": 0.5})
        self.heart.bind(on_release=lambda *_: self.toggle_heart())
        row.add_widget(self.heart)
        self.add_widget(row)

        self.bar = ProgressBar()
        self.add_widget(self.bar)
        times = BoxLayout(size_hint_y=None, height=dp(18))
        self.t_left = label("0:00", 13, DIM, height=18)
        self.t_right = label("-0:30", 13, DIM, height=18, halign="right")
        times.add_widget(self.t_left)
        times.add_widget(self.t_right)
        self.add_widget(times)
        self.set_entry(None)

    def set_entry(self, entry):
        self.ctrl.entry = None
        self.ctrl.stop()
        self.entry = entry
        self.cover_box.clear_widgets()
        if entry:
            self.cover_box.add_widget(cover(entry["title"], 56))
            self.title.text, self.artist.text = entry["title"], entry["artist"]
        else:
            self.cover_box.add_widget(cover("?", 56))
            self.title.text, self.artist.text = "No song yet", "Tap the orb and play a song"
        self.play.disabled = entry is None
        self.heart.disabled = entry is None
        self.heart.set(on=bool(entry) and core.in_library(entry))

    def toggle_heart(self):
        if not self.entry:
            return
        if core.in_library(self.entry):
            core.remove_library(self.entry)
        else:
            core.add_library(self.entry)
        self.heart.set(on=core.in_library(self.entry))

    def _on_change(self, state, text):
        if state == "progress":
            pos = PLAYER.position_ms() / 1000.0
            dur = (PLAYER.duration_ms() / 1000.0) or 30.0
            self.bar.set(pos / dur)
            self.t_left.text = fmt_time(pos)
            self.t_right.text = "-" + fmt_time(dur - pos)
            return
        if state == "loading":
            self.play.disabled = True
            self.t_left.text = "Loading..."
        elif state == "playing":
            self.play.disabled = self.entry is None
            self.play.set(kind="pause")
        else:   # idle or error
            self.play.disabled = self.entry is None
            self.play.set(kind="play")
            self.bar.set(0)
            self.t_left.text = "0:00"
            self.t_right.text = "-0:30"
        if state == "error":
            self.notify(text)


# ---------- screens ----------
class Tab(Row):
    def __init__(self, kind, name, target, **kw):
        super().__init__(bg=CLEAR, radius=18, orientation="vertical", padding=[0, dp(10), 0, dp(4)],
                         spacing=dp(3), **kw)
        self.add_widget(Icon(kind, VIOLET_L, size_hint=(None, None), size=(dp(28), dp(28)),
                             pos_hint={"center_x": 0.5}))
        self.add_widget(label(name, 13, VIOLET_L, bold=True, height=18, halign="center"))
        self.bind(on_release=lambda *_: App.get_running_app().go(target))


class Home(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.busy = False
        self.rec = None
        self.level_ev = None
        root = BoxLayout(orientation="vertical", padding=[dp(18), dp(14), dp(18), dp(12)], spacing=dp(8))

        top = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(12))
        top.add_widget(Logo(50, pos_hint={"center_y": 0.5}))
        top.add_widget(label("Wenzosong Detector", 22, TEXT, bold=True, height=56, one_line=True))
        self.online_btn = CircleButton("wifi", 44, filled=True, pos_hint={"center_y": 0.5})
        self.online_btn.bind(on_release=lambda *_: self.toggle_online())
        top.add_widget(self.online_btn)
        root.add_widget(top)
        self.counter = label("", 13, DIM, height=20)
        root.add_widget(self.counter)

        self.listen = ListenButton()
        self.listen.bind(on_release=lambda *_: self.start())
        root.add_widget(self.listen)

        self.status = label("Tap the orb, then play a song near your phone.", 16, DIM, height=60, halign="center")
        root.add_widget(self.status)

        self.mini = MiniPlayer(on_open=lambda e: App.get_running_app().open_song(e, "home"),
                               notify=self.set_status)
        root.add_widget(self.mini)

        tabs = Surface(bg=CARD, radius=26, outline=EDGE, size_hint_y=None, height=dp(78),
                       padding=[dp(8), dp(4), dp(8), dp(4)], spacing=dp(4))
        for kind, name, target in (("clock", "History", "history"), ("library", "Library", "library"),
                                   ("gear", "Settings", "settings")):
            tabs.add_widget(Tab(kind, name, target))
        root.add_widget(tabs)
        self.add_widget(root)

    def refresh_online(self):
        on = online_on()
        self.online_btn.filled = on
        self.online_btn.set(kind="wifi" if on else "wifi_off")

    def toggle_online(self):
        set_online(not online_on())
        self.refresh_online()
        self.on_pre_enter()
        if online_on():
            self.set_status("Online mode is on.\nTap the orb to detect a song.")
        else:
            self.set_status("Online mode is off.\nTap the Wi-Fi icon to turn it on.")

    def on_pre_enter(self, *a):
        self.refresh_online()
        s = core.get_settings()
        if not online_on():
            self.counter.text = "Offline: turn on the Wi-Fi icon to detect songs."
        elif not (s["audd_token"] or s["acr_key"]):
            self.counter.text = "Open Settings and add your AudD token or ACRCloud keys first."
        elif s["audd_token"] or not s["acr_key"]:
            self.counter.text = f"AudD detections today: {core.usage_today()} of {core.AUDD_DAILY_LIMIT}"
        else:
            self.counter.text = "Detecting with ACRCloud"
        history = core.get_history()
        last = history[-1] if history else None
        if last and not (self.mini.entry and core.same_song(last, self.mini.entry)):
            self.mini.set_entry(last)
        elif self.mini.entry:
            self.mini.heart.set(on=core.in_library(self.mini.entry))

    def on_leave(self, *a):
        self.mini.ctrl.stop()

    def set_status(self, text):
        self.status.text = text

    def start(self):
        if self.busy:
            return
        if not online_on():
            self.set_status("Online mode is off.\nTap the Wi-Fi icon at the top to turn it on.")
            return
        self.mini.ctrl.stop()
        ask_mic(self._after_permission)

    def _after_permission(self, ok):
        if not ok:
            self.set_status("The microphone is blocked.\nAllow it in Android Settings, Apps.")
            return
        self.run(record_first=True, over=False)

    def run(self, record_first, over):
        self.busy = True
        self.listen.disabled = True
        self.listen.set_active(True)
        self.level_ev = Clock.schedule_interval(self._poll_level, 1 / 20)
        threading.Thread(target=self._work, args=(record_first, over), daemon=True).start()

    def _poll_level(self, dt):
        self.listen.set_level(self.rec.level() if self.rec else 0.25)

    def post(self, fn, *args):
        Clock.schedule_once(lambda dt: fn(*args))

    def _work(self, record_first, over):
        path = os.path.join(App.get_running_app().user_data_dir, "clip.m4a")
        try:
            if record_first:
                rec = Recorder(path)
                rec.start()
                self.rec = rec
                for i in range(SECONDS, 0, -1):
                    self.post(self.set_status, f"Listening... {i}s\nDetecting sound")
                    time.sleep(1)
                self.rec = None
                rec.stop()
            self.post(self.set_status, "Identifying...\nPlease wait")
            entry, msg, code = core.detect(path, over)
        except Exception as err:  # noqa: BLE001 - show any problem on screen
            self.rec = None
            entry, msg, code = None, f"Something went wrong: {err}", "error"
        self.post(self.finish, entry, msg, code)

    def finish(self, entry, msg, code):
        self.busy = False
        self.rec = None
        self.listen.disabled = False
        self.listen.set_active(False)
        if self.level_ev:
            self.level_ev.cancel()
            self.level_ev = None
        self.on_pre_enter()
        if code == "ok":
            core.add_history(entry)
            self.mini.set_entry(entry)
            self.set_status("Found it!\nTap the card for links and more.")
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

    def __init__(self, **kw):
        super().__init__(**kw)
        self.ctrl = PreviewController(self._on_preview)

    def show(self, entry, back):
        self.ctrl.stop()
        self.entry, self.back = entry, back
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=[dp(20), dp(16), dp(20), dp(14)], spacing=dp(10))
        root.add_widget(header("Song found", lambda: App.get_running_app().go(self.back)))

        card = Surface(bg=CARD, radius=22, outline=EDGE, size_hint_y=None, height=dp(120),
                       padding=dp(16), spacing=dp(16))
        card.add_widget(cover(entry["title"], 88))
        info = BoxLayout(orientation="vertical", spacing=dp(2))
        info.add_widget(label(entry["title"], 20, bold=True, height=30, one_line=True))
        info.add_widget(label(entry["artist"], 16, VIOLET_L, height=26, one_line=True))
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
            colour = next((c for key, c in SERVICES.items() if key in name), VIOLET_L)
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
        self.preview_btn.bind(on_release=lambda *_: self.ctrl.toggle(self.entry))
        root.add_widget(self.preview_btn)
        self.save_btn = RoundButton("", bg=VIOLET, fg=WHITE)
        self.save_btn.bind(on_release=lambda *_: self.toggle())
        root.add_widget(self.save_btn)
        self.refresh_save()
        self.add_widget(root)

    def on_leave(self, *a):
        self.ctrl.stop()

    def _on_preview(self, state, text):
        if not hasattr(self, "preview_btn"):
            return
        if state == "loading":
            self.preview_btn.text = "Loading preview..."
            self.note.text = ""
        elif state == "playing":
            self.preview_btn.text = "Stop preview"
            self.note.text = text
        elif state == "error":
            self.preview_btn.text = "Play 30-second preview"
            self.note.text = text
        elif state == "idle":
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
                           background_color=CARD, foreground_color=TEXT, cursor_color=VIOLET_L,
                           hint_text_color=DIM, padding=[dp(14), dp(14), dp(14), dp(12)])
            self.inputs[key] = ti
            grid.add_widget(ti)
        root.add_widget(scroll)
        save = RoundButton("Save", bg=VIOLET, fg=WHITE)
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
        return self.sm

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


if __name__ == "__main__":
    SongApp().run()
