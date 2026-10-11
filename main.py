"""Song Detector - Android app (Kivy). Logic lives in core.py."""
import os
import threading
import time
from urllib.parse import quote_plus

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Rectangle, RoundedRectangle
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

# ---------- colours (Neon Dark Theme) ----------
BG = (0.04, 0.02, 0.08, 1)
CARD = (0.10, 0.08, 0.18, 1)
TEXT = (0.95, 0.95, 1, 1)
DIM = (0.55, 0.50, 0.75, 1)
AMBER = (0.70, 0.45, 1.0, 1)
REC = (0.55, 0.30, 1.0, 1)
DARK = (0.05, 0.03, 0.10, 1)
CLEAR = (0, 0, 0, 0)

COVERS = [
    (0.45, 0.25, 0.95, 1),
    (0.55, 0.30, 1.0, 1),
    (0.35, 0.55, 1.0, 1),
    (0.70, 0.35, 0.95, 1),
    (0.40, 0.70, 1.0, 1),
    (0.60, 0.40, 1.0, 1)
]

SERVICES = {
    "YouTube": (1, 0.25, 0.25, 1),
    "Spotify": (0.12, 0.84, 0.38, 1),
    "Apple Music": (0.98, 0.34, 0.5, 1),
    "Boomplay": (0.2, 0.6, 1, 1),
    "Audiomack": (1, 0.62, 0.1, 1),
    "Search": (0.62, 0.68, 0.78, 1)
}


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
                    Color(0.55, 0.30, 1.0, 0.35 * (1 - p))
                    Ellipse(pos=(cx - rr, cy - rr), size=(2 * rr, 2 * rr))
            else:
                rr = r * 1.35
                Color(0.55, 0.30, 1.0, 0.18)
                Ellipse(pos=(cx - rr, cy - rr), size=(2 * rr, 2 * rr))
            if self.disabled:
                Color(0.4, 0.2, 0.7, 0.6)
            elif self.state == "down":
                Color(0.45, 0.22, 0.85, 1)
            else:
                Color(*REC)
            Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
            Color(1, 1, 1, 1)
            w, h = r * 0.36, r * 0.7
            RoundedRectangle(pos=(cx - w / 2, cy - h * 0.35), size=(w, h), radius=[w / 2])
            Rectangle(pos=(cx - r * 0.04, cy - r * 0.5), size=(r * 0.08, r * 0.25))
            Rectangle(pos=(cx - r * 0.2, cy - r * 0.55), size=(r * 0.4, r * 0.07))


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
        except Exception:
            return False

    def stop(self):
        if self.mp:
            try:
                self.mp.stop()
            except Exception:
                pass
            self.mp.release()
            self.mp = None


PLAYER = Player()


class Home(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.busy = False
        root = BoxLayout(orientation="vertical", padding=[dp(20), dp(16), dp(20), dp(14)], spacing=dp(10))

        top = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(12))
        top.add_widget(Logo(52, pos_hint={"center_y": 0.5}))
        names = BoxLayout(orientation="vertical")
        names.add_widget(label("Wenzosong Detector", 22, bold=True, height=32, one_line=True))
        names.add_widget(label("Find any song in seconds", 13, DIM, height=22))
        top.add_widget(names)
        root.add_widget(top)

        self.counter = label("", 14, DIM, height=22)
        root.add_widget(self.counter)

        self.listen = ListenButton()
        self.listen.bind(on_release=lambda *_: self.start())
        root.add_widget(self.listen)

        self.status = label("Play a song near your phone, then tap the button.", 15, TEXT, height=48, halign="center")
        root.add_widget(self.status)

        root.add_widget(label("Or search by name", 14, DIM, height=24, halign="center"))

        search_box = Surface(bg=CARD, radius=16, size_hint_y=None, height=dp(56), padding=[dp(12), dp(6)], spacing=dp(10))
        self.search_input = TextInput(
            hint_text="Type song or artist name...",
            multiline=False, size_hint_y=None, height=dp(44), font_size=dp(15),
            background_normal="", background_active="", background_color=(0, 0, 0, 0),
            foreground_color=TEXT, cursor_color=AMBER, hint_text_color=DIM,
            padding=[dp(6), dp(10), dp(6), dp(10)]
        )
        search_box.add_widget(self.search_input)
        search_btn = RoundButton("Search", bg=AMBER, fg=DARK, height=44, size_hint_x=None, width=dp(90))
        search_btn.bind(on_release=self.do_search)
        search_box.add_widget(search_btn)
        root.add_widget(search_box)

        tabs = Surface(bg=CARD, radius=20, size_hint_y=None, height=dp(64), padding=dp(6), spacing=dp(6))
        for name, target in (("History", "history"), ("Library", "library"), ("Settings", "settings")):
            t = RoundButton(name, bg=CLEAR, fg=DIM, height=52)
            t.bind(on_release=lambda _b, tg=target: App.get_running_app().go(tg))
            tabs.add_widget(t)
        root.add_widget(tabs)
        self.add_widget(root)

    def do_search(self, *args):
        query = self.search_input.text.strip()
        if not query:
            self.set_status("Please type a song or artist name.")
            return
        open_url("https://www.google.com/search?q=" + quote_plus(query + " song"))
        self.set_status(f"Searching for: {query}")

    def on_pre_enter(self, *a):
        s = core.get_settings()
        if not (s["audd_token"] or s["acr_key"]):
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
        ask_mic(self._after_permission)

    def _after_permission(self, ok):
        if not ok:
            self.set_status("Microphone is blocked. Allow it in Android Settings.")
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
        except Exception as err:
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

        card = Surface(bg=CARD, radius=20, size_hint_y=None, height=dp(130), padding=dp(16), spacing=dp(16))
        cover_widget = cover(entry["title"], 90)
        if entry.get("image"):
            try:
                from kivy.uix.image import AsyncImage
                cover_widget = AsyncImage(source=entry["image"], size_hint=(None, None), size=(dp(90), dp(90)))
            except Exception:
                pass
        card.add_widget(cover_widget)
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
            row = Row(bg=CARD, radius=14, size_hint_y=None, height=dp(56), padding=[dp(16), 0, dp(16), 0], spacing=dp(14))
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

        buttons = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(12))
        share_btn = RoundButton("Share", bg=CARD, fg=TEXT)
        share_btn.bind(on_release=lambda *_: self.share_song())
        buttons.add_widget(share_btn)
        self.save_btn = RoundButton("", bg=AMBER, fg=DARK)
        self.save_btn.bind(on_release=lambda *_: self.toggle())
        buttons.add_widget(self.save_btn)
        root.add_widget(buttons)

        self.refresh_save()
        self.add_widget(root)

    def share_song(self):
        text = f"🎵 {self.entry['title']} - {self.entry['artist']}\nDetected with Wenzosong Detector"
        if platform == "android":
            try:
                from jnius import autoclass
                Intent = autoclass("android.content.Intent")
                String = autoclass("java.lang.String")
                activity = autoclass("org.kivy.android.PythonActivity").mActivity
                intent = Intent(Intent.ACTION_SEND)
                intent.setType("text/plain")
                intent.putExtra(Intent.EXTRA_TEXT, String(text))
                activity.startActivity(Intent.createChooser(intent, String("Share song")))
            except Exception as e:
                self.note.text = f"Could not share: {e}"
        else:
            print(text)

    def on_leave(self, *a):
        self.stop_preview()

    def toggle_preview(self):
        if self.loading:
            return
        if PLAYER.is_playing():
            self.stop_preview()
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
                error = "No preview available for this song."
            else:
                preview.download(url, path)
        except Exception:
            error = "Could not load the preview."
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
        except Exception as err:
            self._preview_failed(f"Could not play: {err}")
            return
        self.preview_btn.text = "Stop preview"
        self.note.text = "Playing 30-second preview"
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


class ListScreen(Screen):
    def __init__(self, mode, **kw):
        super().__init__(**kw)
        self.mode = mode

    def on_pre_enter(self, *a):
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=[dp(20), dp(16), dp(20), dp(14)], spacing=dp(12))
        root.add_widget(header(f"{self.mode.capitalize()}", lambda: App.get_running_app().go("home")))

        scroll, grid = scroll_list()

        if self.mode == "library":
            # ===== Saved songs (from detection) =====
            saved = list(reversed(core.get_library()))
            grid.add_widget(label("Saved Songs", 16, AMBER, height=30, bold=True))

            if not saved:
                grid.add_widget(label("No saved songs yet.", 14, DIM, height=28))
            else:
                for e in saved:
                    row = Row(bg=CARD, radius=16, size_hint_y=None, height=dp(76), padding=dp(10), spacing=dp(14))
                    row.add_widget(cover(e["title"], 54))
                    info = BoxLayout(orientation="vertical", spacing=dp(2))
                    info.add_widget(label(e["title"], 16, bold=True, height=26, one_line=True))
                    info.add_widget(label(e["artist"], 13, DIM, height=22, one_line=True))
                    row.add_widget(info)
                    row.bind(on_release=lambda _r, entry=e: App.get_running_app().open_song(entry, self.mode))
                    grid.add_widget(row)

            # ===== Local Music on phone =====
            grid.add_widget(label("", 10, height=20))  # space
            grid.add_widget(label("On this phone", 16, AMBER, height=30, bold=True))

            local_songs = self.scan_local_music()
            if not local_songs:
                grid.add_widget(label("No local music found yet.\nDownload some songs and they will appear here.", 14, DIM))
            else:
                for song in local_songs:
                    row = Row(bg=CARD, radius=16, size_hint_y=None, height=dp(70), padding=dp(12), spacing=dp(12))
                    row.add_widget(label("🎵", 22, height=50, size_hint_x=None, width=dp(40)))
                    info = BoxLayout(orientation="vertical")
                    info.add_widget(label(song["title"], 15, bold=True, height=26, one_line=True))
                    info.add_widget(label(song["path"], 11, DIM, height=20, one_line=True))
                    row.add_widget(info)
                    row.bind(on_release=lambda _r, p=song["path"]: self.play_local(p))
                    grid.add_widget(row)

        else:
            # History mode (normal)
            items = list(reversed(core.get_history()))
            if not items:
                grid.add_widget(label("Nothing here yet.", 16, DIM))
            for e in items:
                row = Row(bg=CARD, radius=16, size_hint_y=None, height=dp(76), padding=dp(10), spacing=dp(14))
                row.add_widget(cover(e["title"], 54))
                info = BoxLayout(orientation="vertical", spacing=dp(2))
                info.add_widget(label(e["title"], 16, bold=True, height=26, one_line=True))
                sub = e["artist"] + (f"  -  {e['date']}" if self.mode == "history" else "")
                info.add_widget(label(sub, 13, DIM, height=22, one_line=True))
                row.add_widget(info)
                row.bind(on_release=lambda _r, entry=e: App.get_running_app().open_song(entry, self.mode))
                grid.add_widget(row)

            if items:
                clear = RoundButton("Clear history", bg=CARD, fg=REC)
                clear.bind(on_release=lambda *_: (core.clear_history(), self.on_pre_enter()))
                root.add_widget(clear)

        root.add_widget(scroll)
        self.add_widget(root)

    def scan_local_music(self):
        """Scan common folders for music files."""
        songs = []
        extensions = (".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg")

        # Common music locations on Android
        possible_paths = [
            "/storage/emulated/0/Music",
            "/storage/emulated/0/Download",
            "/storage/emulated/0/Downloads",
            "/storage/emulated/0/Telegram",
            "/storage/emulated/0/WhatsApp/Media/WhatsApp Audio",
            "/storage/emulated/0/Movies",
            "/sdcard/Music",
            "/sdcard/Download",
        ]

        for folder in possible_paths:
            if not os.path.exists(folder):
                continue
            try:
                for root_dir, dirs, files in os.walk(folder):
                    for file in files:
                        if file.lower().endswith(extensions):
                            full_path = os.path.join(root_dir, file)
                            title = os.path.splitext(file)[0]
                            songs.append({
                                "title": title,
                                "path": full_path
                            })
            except Exception:
                continue

        # Remove duplicates and sort
        unique = {s["path"]: s for s in songs}
        return sorted(unique.values(), key=lambda x: x["title"].lower())

    def play_local(self, path):
        try:
            PLAYER.play(path)
            self.note_text = f"Playing: {os.path.basename(path)}"
        except Exception as e:
            print("Could not play:", e)


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
        root.add_widget(label("Your keys stay on this phone.", 14, DIM))
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
        return self.sm

    def go(self, name):
        self.sm.current = name

    def open_song(self, entry, back):
        self.sm.get_screen("song").show(entry, back)
        self.sm.current = "song"

    def on_key(self, window, key, *args):
        if key == 27:
            if self.sm.current == "song":
                self.sm.current = self.sm.get_screen("song").back
                return True
            if self.sm.current != "home":
                self.sm.current = "home"
                return True
        return False


if __name__ == "__main__":
    SongApp().run()
