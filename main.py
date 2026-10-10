"""Song Detector - Android app (Kivy). Logic lives in core.py."""
import os
import threading
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import platform

import core

SECONDS = 10
BG = (0.086, 0.118, 0.18, 1)
PANEL = (0.12, 0.165, 0.25, 1)
TEXT = (0.93, 0.945, 0.97, 1)
DIM = (0.56, 0.63, 0.74, 1)
AMBER = (1, 0.72, 0.3, 1)
REC = (1, 0.35, 0.37, 1)
DARK = (0.1, 0.1, 0.1, 1)


# ---------- small helpers ----------
def button(text, bg=PANEL, fg=TEXT, height=52, **kw):
    return Button(text=text, background_normal="", background_color=bg, color=fg,
                  size_hint_y=None, height=dp(height), font_size=dp(16), bold=True, **kw)


def label(text, size=16, color=TEXT, bold=False, height=None, halign="left"):
    lab = Label(text=text, font_size=dp(size), color=color, bold=bold, halign=halign, valign="middle")
    lab.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    if height:
        lab.size_hint_y = None
        lab.height = dp(height)
    else:
        lab.size_hint_y = None
        lab.bind(texture_size=lambda w, s: setattr(w, "height", s[1] + dp(6)))
    return lab


def scroll_list():
    scroll = ScrollView()
    grid = GridLayout(cols=1, spacing=dp(8), size_hint_y=None)
    grid.bind(minimum_height=grid.setter("height"))
    scroll.add_widget(grid)
    return scroll, grid


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


# ---------- screens ----------
class Home(Screen):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.busy = False
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(14))
        root.add_widget(label("Song Detector", 28, bold=True, height=48))
        self.counter = label("", 14, DIM, height=22)
        root.add_widget(self.counter)
        self.listen = Button(text="Tap to listen", font_size=dp(24), bold=True,
                             background_normal="", background_color=REC, color=(1, 1, 1, 1),
                             size_hint_y=None, height=dp(200))
        self.listen.bind(on_release=lambda *_: self.start())
        root.add_widget(self.listen)
        self.status = label("Play a song near your phone, then tap the button.", 16, TEXT, height=80, halign="center")
        root.add_widget(self.status)
        root.add_widget(BoxLayout())  # spacer
        row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(10))
        for name, target in (("History", "history"), ("Library", "library"), ("Settings", "settings")):
            b = button(name)
            b.bind(on_release=lambda _b, t=target: App.get_running_app().go(t))
            row.add_widget(b)
        root.add_widget(row)
        self.add_widget(root)

    def on_pre_enter(self, *a):
        s = core.get_settings()
        if not (s["audd_token"] or s["acr_key"]):
            self.counter.text = "Open Settings and add your AudD token or ACRCloud keys first."
        elif s["audd_token"] or not s["acr_key"]:
            self.counter.text = f"AudD detections today: {core.usage_today()} of {core.AUDD_DAILY_LIMIT}"
        else:
            self.counter.text = ""

    def set_status(self, text):
        self.status.text = text

    def start(self):
        if self.busy:
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

    def show(self, entry, back):
        self.entry, self.back = entry, back
        self.clear_widgets()
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(10))
        root.add_widget(label(entry["title"], 24, bold=True))
        root.add_widget(label(entry["artist"], 18, AMBER))
        if entry.get("album"):
            root.add_widget(label(entry["album"], 14, DIM))
        scroll, grid = scroll_list()
        for name, url in core.sources(entry):
            b = button(name)
            b.bind(on_release=lambda _b, u=url: open_url(u))
            grid.add_widget(b)
        self.save_btn = button("", AMBER, DARK)
        self.save_btn.bind(on_release=lambda *_: self.toggle())
        grid.add_widget(self.save_btn)
        self.refresh_save()
        root.add_widget(scroll)
        back_btn = button("Back")
        back_btn.bind(on_release=lambda *_: App.get_running_app().go(self.back))
        root.add_widget(back_btn)
        self.add_widget(root)

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
        items = list(reversed(core.get_history() if self.mode == "history" else core.get_library()))
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(10))
        root.add_widget(label(self.mode.capitalize() + f" ({len(items)})", 24, bold=True, height=44))
        scroll, grid = scroll_list()
        if not items:
            grid.add_widget(label("Nothing here yet.", 16, DIM))
        for e in items:
            when = f"\n{e['date']}" if self.mode == "history" else ""
            b = button(f"{e['title']} - {e['artist']}{when}", height=64)
            b.bind(on_release=lambda _b, entry=e: App.get_running_app().open_song(entry, self.mode))
            grid.add_widget(b)
        root.add_widget(scroll)
        if self.mode == "history" and items:
            clear = button("Clear history", PANEL, REC)
            clear.bind(on_release=lambda *_: (core.clear_history(), self.on_pre_enter()))
            root.add_widget(clear)
        back = button("Back")
        back.bind(on_release=lambda *_: App.get_running_app().go("home"))
        root.add_widget(back)
        self.add_widget(root)


class SettingsScreen(Screen):
    FIELDS = (("audd_token", "AudD token"), ("acr_host", "ACRCloud host (like identify-eu-west-1.acrcloud.com)"),
              ("acr_key", "ACRCloud access key"), ("acr_secret", "ACRCloud access secret"))

    def on_pre_enter(self, *a):
        self.clear_widgets()
        s = core.get_settings()
        root = BoxLayout(orientation="vertical", padding=dp(20), spacing=dp(10))
        root.add_widget(label("Settings", 24, bold=True, height=44))
        root.add_widget(label("Your keys stay on this phone. Paste them here once.", 14, DIM))
        self.inputs = {}
        for key, hint in self.FIELDS:
            ti = TextInput(text=s[key], hint_text=hint, multiline=False, size_hint_y=None, height=dp(48),
                           write_tab=False, font_size=dp(15))
            self.inputs[key] = ti
            root.add_widget(ti)
        root.add_widget(BoxLayout())
        save = button("Save", AMBER, DARK)
        save.bind(on_release=lambda *_: self.save())
        root.add_widget(save)
        back = button("Back")
        back.bind(on_release=lambda *_: App.get_running_app().go("home"))
        root.add_widget(back)
        self.add_widget(root)

    def save(self):
        core.save_settings({k: ti.text for k, ti in self.inputs.items()})
        App.get_running_app().go("home")


class SongApp(App):
    title = "Song Detector"

    def build(self):
        core.DATA_DIR = self.user_data_dir
        Window.clearcolor = BG
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
