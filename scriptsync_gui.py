"""
ScryptSink - desktop app (no command line needed)
By wishym1shy  (https://github.com/wishym1shy)

Add clips (and their scripts), press Sync, get a timed .srt next to each clip
plus a review sheet that tells you which lines to double-check.
"""
import json
import os
import queue
import subprocess
import sys
import threading
import logging
import time
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

import scriptsync_core as core

log = core.log

HERE = os.path.dirname(os.path.abspath(__file__))


def system_prefers_dark() -> bool:
    """Is Windows (or macOS) set to dark mode? Used until the user picks light or night themselves."""
    try:
        if sys.platform.startswith("win"):
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
        if sys.platform == "darwin":
            out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True,
                                 text=True, timeout=3)
            return out.stdout.strip().lower() == "dark"
    except Exception:
        log.debug("couldn't read the system's light/dark setting", exc_info=True)
    return False


def dark_title_bar(win, dark: bool):
    """Windows 10/11: match the window's title bar to night mode (no-op elsewhere)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):          # DWMWA_USE_IMMERSIVE_DARK_MODE (newer, then older Windows 10 builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value),
                                                           ctypes.sizeof(value)) == 0:
                break
    except Exception:
        log.debug("couldn't set the title bar colour", exc_info=True)


def theme_text_widget(t):
    """Colour a plain tk.Text (ttk doesn't style these)."""
    t.configure(background=P["field"], foreground=P["text"], insertbackground=P["text"],
                selectbackground=P["sel"], selectforeground=P["sel_text"], highlightthickness=1,
                highlightbackground=P["border"], highlightcolor=P["accent"], relief="flat", borderwidth=4)

MODELS = {
    "Fast  (base)": "base",
    "Balanced  (small) - recommended": "small",
    "Accurate  (medium)": "medium",
    "Most accurate  (large-v3-turbo)": "large-v3-turbo",
}
LANGS = {
    "Auto-detect": "auto",
    "English": "en",
    "Tagalog / Filipino": "tl",
    "Spanish": "es",
}
FRAME_RATES = {
    "Don't snap": 0.0, "23.976": 24000 / 1001, "24": 24.0, "25": 25.0, "29.97": 30000 / 1001,
    "30": 30.0, "50": 50.0, "59.94": 60000 / 1001, "60": 60.0,
}
AUTO_FPS = "Auto (match the clip)"

# Light and night colours. Every text/background pair here passes WCAG AA contrast (4.5:1 or more).
PALETTES = {
    "light": {
        "bg": "#f6f5f2", "panel": "#fbfaf8", "field": "#ffffff", "border": "#c9c5bc", "head": "#ebe8e1",
        "text": "#1f1f1f", "sub": "#5f5f5f", "disabled": "#8c8c8c", "btn": "#ece9e2", "btn_hover": "#e2ded5",
        "track": "#e3e0d8", "accent": "#d9822b", "accent_hover": "#e39448", "on_accent": "#1f1f1f",
        "sel": "#3d5a80", "sel_text": "#ffffff", "link": "#2f4f78",
        "ok": "#e6f4ea", "check": "#fff3d1", "bad": "#fbdada", "ok_text": "#1e6b3a", "check_text": "#7a5200",
        "bad_text": "#a1262b", "tip_bg": "#24292f", "tip_text": "#ffffff",
        "dot_idle": "#e0b42f", "dot_wait": "#d9822b", "dot_run": "#2e9d57", "dot_err": "#d1453b",
        "dot_ring": "#8a8578",
    },
    "night": {
        "bg": "#1e1f22", "panel": "#25272b", "field": "#2b2d31", "border": "#43464d", "head": "#26282c",
        "text": "#e8e8e8", "sub": "#a6a9b0", "disabled": "#6f737a", "btn": "#2f3136", "btn_hover": "#3a3d43",
        "track": "#3a3d43", "accent": "#e39a4e", "accent_hover": "#eeac68", "on_accent": "#1a1a1a",
        "sel": "#3d5a80", "sel_text": "#ffffff", "link": "#9cc0ee",
        "ok": "#1f3a2b", "check": "#463a12", "bad": "#4d2427", "ok_text": "#7fd49b", "check_text": "#f2c75c",
        "bad_text": "#ff9a9e", "tip_bg": "#e8e8e8", "tip_text": "#1a1a1a",
        "dot_idle": "#e8c34a", "dot_wait": "#e39a4e", "dot_run": "#4cc27a", "dot_err": "#ff6b6b",
        "dot_ring": "#6f737a",
    },
}
P = dict(PALETTES["light"])      # the palette in use; dialogs created later read it

# GitHub mark (github.com/logos), pre-rendered so no image library is needed: "dark" is for light
# backgrounds, "light" for dark ones (night mode). 26 px, and 52 px for high-DPI displays.
GITHUB_MARK = {
    ("dark", 26): (
    "iVBORw0KGgoAAAANSUhEUgAAABoAAAAaCAYAAACpSkzOAAADiElEQVR4nKRWW2wMYRQ+559pRV2CtGlJpKpTdldtXYKQICSa"
    "CCHuPHkTIcQLEX0Qt3ghiBCeeJW4JDREBBHBk8Ru2Z2VXSouEW1dKtrq7s7xzZTamd3tZfu9zD/nP+f7zvnP//8zOvWDqqm1"
    "QY3VSiJeRiwTYar4O/WZhN/jeVdYGhPR8Mu+eDjfxKSawAxd1y/AZR4NBCKPSPHOeCT0amBCgUCxIfopTO2gQUIAJj4dN0N7"
    "8ZrOK1Tp94/XpegWM8+mIUBIHndJ95qPptn2z6b+DQzDGAaRxqGK2EBVC4dz8XUMtSwhKhpxHiKzMrLaahHtx6ClX2ahVqxb"
    "gyW0LkNuUbU/ePy/OGD4ps8nVk9740S+JMxwuTNnGKOlqOSwCHUIWw81oaRttyylIbHFrKQ01akONDe/+N7DFUwQ8+S/PAJx"
    "/9tYOKb3JKROZDaLmXrXNh6Pt+OxJ08t97Ms7KzA5B4eZo3kKIYblH1OQLzAvRJcSX1s/T4hZLiFeX1VVW25Ukpb7fVli846"
    "IYXoMJ/J4ivWVmAzSL3LUSj9nbqOUYHo/KGftDlcQorqIcQTPTmFWmOxn1QgPn163oFWPHdTSo1iklKXkekXDRE4Gq0uSqZJ"
    "Cova6fEaS0MEdtE4NyenFTr+2qM+ZcKE2SVUKHBX4sarc+tITIHY9ORTXDIqtZYKhJHWVoNzuMsoFEVFVizLm6WhLBAYSYNE"
    "eXlwhCh1MIuO2FSclGsYp9wz7Btt6U+qfbULBiqCa2zxyLH0DP2Z5plKWt3Jq87pr/bVXUS527ANb6aF9ilFp5DFcnsOZ+Ip"
    "duY9i+TaG7OpyUUeqJuG62wLmlCP+Dm5U5Dz8Wh4p3N7d0vXITD+RiWrNEXb2zm1Ee8feorD9cR80PmmedGdtD90DflEENOV"
    "4tQRe+x8L9rb2n6OKa2wN8YSVDB3mPANTqUvkdLGwP0b7r7GN7Gmy16ir19bWsaVVqxBEypyFsNy6G301W1nmGmv9gXP4MLd"
    "DfIoMlnaHIl8pn6AmPuIWZpdjXU2YTbt7tX0Ohj+4Dnnf0GoHetyx64IPUglzNCu3EJ1D+yV8Mg4fcm0KG+g7YBDvBki35DF"
    "JvRgO8wzKR9Yinrpid7ZsV6RnEI2EtHQFU7+mor6DyCwA2SSX4fSjg987Rg7Nqcf9QPDmFlG9LssHo9Ecs1X1tT6dUu1JRLh"
    "L33x/AEAAP//ewu0tgAAAAZJREFUAwCJ5F7ziFQ53wAAAABJRU5ErkJggg=="),
    ("dark", 52): (
    "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"
    "AAAAAElFTkSuQmCC"),
    ("light", 26): (
    "iVBORw0KGgoAAAANSUhEUgAAABoAAAAaCAYAAACpSkzOAAADWElEQVR4nKxWXUgUURQ+Z2Z03V2ztR/6oaCC/un/IYooEKKH"
    "gqiIeus1lOwpCCWK6OexxJAg6K0HwV4qkB6iH9Ei6MGo1MCgghBT3NV2Vp25e/ruuJuz464/ax/M3jPnnnO+e8+9c85aNAP+"
    "jMl2N50+RiKH8bpaiJZrPRP1YfgJ6blpGs8WhPjTdHG40MTQuOxk170Pk700CwjJa8u0akD4eVZEIlKaSKk7EKtp7hAmuVsR"
    "ti4xsypIlEzKCofcp8S8h+YB7K7NDFsnKpgHpxBhJ6GE7XaAZDf9B4DsTSxsVWV3ZmQnErZq8pMw0zn8XobH71lEHYBDPS7K"
    "qX/+xAcTKff25DswbMu+NKkOn2N/LGot80SRinjKvc5CNpn0UoScjKMpaTrEBi+RMrOukjmu9XHb7cWwLhvJMMzNFWXc4xEN"
    "2U47VrB/kki6YtGSLVQE4rbzLnBTW2IR6zR734lSnZSTCbJjYbMc+RWaI+JJF2mkxX6dFTaXGyqdPh40xhVtLIbE8zW4Iahz"
    "RtVRRtrakLYDPr1aGDaRch6hIoAzjeA7HIZo+tTNuHW8OmDZWSyJBnxtBPkQiLleX+8lOTqmJM0XwgMB+jUGTiKVa0SVNF+w"
    "LApolCEsX3NsmDfoPFOR0LVSiHfk6Fh6sCPuDtiWDo+qk1QkcBGO4+MM+3Xg6DKwhR6auqp6POU0R8AniufqFD1zt0GG8Riy"
    "mzvFm1BK2lGa9tMsMZKSQ/B5i9RvDUw5ITJajFgZ9+ICPPSYiZ6gNm2C0AqH7ah/7bo8DSWda6gg26YEH5Ot8aRzA2XnvRL1"
    "Cj7b8qzhQSTCP7xahz600mH1DWIo07iuxFOqC5OrstaWae4oD/HHANEWpVTejprBKMrPWtSyPq9NRKP8C6u5NbErrk3YtBGB"
    "j2CHj3SLxngvSKKBtv0FZ9JZiAUxb2oST/ZPIE0NKEe1unpbEasqazQdcC4vMFQF9VhcY2XEqs2+W/7JykjJRThaWEq1Y6se"
    "yK1YyhB6kAunCwW48v3BafKTaBhBC/SOGgxnNQHGM1jaeaxvFxUAUlsyKdN37ZuJQdMSZcia0Y82Ymd1ujdNxCgI5dnAVvto"
    "33xGTDNgRGQpjdNSffB558dkM5XS4ALm/uni/AUAAP//Lv0oEQAAAAZJREFUAwArs2cfof3zjQAAAABJRU5ErkJggg=="),
    ("light", 52): (
    "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"
    "SUVORK5CYII="),
}


def settings_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = core.data_folder(base)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "settings.json")


def open_path(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Couldn't open", str(e))


def reveal(path):
    """Open the folder containing path (selecting the file where the OS supports it)."""
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except Exception as e:
        messagebox.showerror("Couldn't open", str(e))


class _Tooltip:
    """Small hover hint for a widget."""

    def __init__(self, widget, text):
        self.widget, self.text, self.tip = widget, text, None
        widget.bind("<Enter>", self.show, add="+")
        widget.bind("<Leave>", self.hide, add="+")

    def show(self, _e=None):
        if self.tip:
            return
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        tk.Label(self.tip, text=self.text, bg=P["tip_bg"], fg=P["tip_text"], padx=8, pady=4,
                 font=("Segoe UI", 9)).pack()
        self.tip.update_idletasks()
        # right-aligned under the widget, so it stays inside the window
        x = self.widget.winfo_rootx() + self.widget.winfo_width() - self.tip.winfo_width()
        self.tip.wm_geometry(f"+{max(x, 0)}+{y}")

    def hide(self, _e=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class PasteDialog(tk.Toplevel):
    """Paste (or edit) a script. With allow_import, a button picks a script file instead:
    afterwards .result is the text (or None) and .result_path the chosen file (or None)."""

    def __init__(self, parent, title, initial="", allow_import=False):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.configure(bg=P["bg"])
        self.result = None
        self.result_path = None
        # Pack order matters: tkinter hands out space in the order widgets are packed. The buttons
        # go in first (docked to the bottom) so the text box can only take what is left, and the
        # buttons can never be pushed off-screen (they used to be, until the window was enlarged).
        bar = ttk.Frame(self, padding=12)
        bar.pack(side="bottom", fill="x")
        ttk.Button(bar, text="Use this script", style="Accent.TButton", command=self.ok).pack(side="right")
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        ttk.Label(bar, text="Ctrl+Enter", style="Sub.TLabel").pack(side="right", padx=(0, 6))
        if allow_import:
            ttk.Button(bar, text="Import .txt / .srt instead\u2026", command=self.import_file).pack(side="left")
        ttk.Label(self, text="Paste the writer's script here (one subtitle line per line).",
                  padding=(12, 10, 12, 4)).pack(side="top", anchor="w")
        tf = ttk.Frame(self)
        tf.pack(side="top", fill="both", expand=True, padx=12)
        # Small requested size: the window size decides the real size, the text box just fills it.
        self.text = tk.Text(tf, wrap="word", font=("Segoe UI", 11), undo=True, width=40, height=8)
        theme_text_widget(self.text)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.insert("1.0", initial)
        self.bind("<Control-Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self._place(parent)
        dark_title_bar(self, P is not None and P["bg"] == PALETTES["night"]["bg"])
        self.text.focus_set()
        self.grab_set()

    def _place(self, parent):
        """Size the window for the screen's scaling (fonts grow on high-DPI displays) and centre it
        over the main window, never larger than the screen."""
        self.update_idletasks()
        px = float(self.tk.call("tk", "scaling")) / (96 / 72)      # 1.0 at 100% display scaling
        w = min(int(640 * px), self.winfo_screenwidth() - 40)
        h = min(int(460 * px), self.winfo_screenheight() - 80)
        self.minsize(min(int(420 * px), w), min(int(260 * px), h))
        x = parent.winfo_rootx() + max((parent.winfo_width() - w) // 2, 0)
        y = parent.winfo_rooty() + max((parent.winfo_height() - h) // 3, 0)
        self.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")

    def ok(self):
        self.result = self.text.get("1.0", "end").strip()
        self.destroy()

    def import_file(self):
        p = filedialog.askopenfilename(
            parent=self, title="Choose the writer's script",
            filetypes=[("Scripts", "*.txt *.srt *.docx *.md"), ("All files", "*.*")])
        if p:
            self.result_path = p
            self.destroy()


class LineBreaksDialog(PasteDialog):
    """Same window as Paste script, with its own instructions."""

    def __init__(self, parent, title, initial, prompt):
        super().__init__(parent, title, initial)
        for w in self.winfo_children():
            if isinstance(w, ttk.Label):
                w.configure(text=prompt, wraplength=560, justify="left")
                break


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{core.APP_NAME}")
        self.px = float(self.tk.call("tk", "scaling")) / (96 / 72)    # 1.0 at 100% display scaling
        w = min(int(1120 * self.px), self.winfo_screenwidth() - 40)
        h = min(int(880 * self.px), self.winfo_screenheight() - 80)
        self.geometry(f"{w}x{h}")
        self.minsize(min(int(940 * self.px), w), min(int(640 * self.px), h))
        self.entries = {}          # iid -> dict(job, result, status)
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.style = ttk.Style(self)
        self.appearance = None     # "light" / "night" once the user picks one; None = follow the system
        self._themed = []          # (widget, function) for plain tk widgets that ttk styles don't reach
        self._run_info = None      # the batch in progress, for the status bar
        self._outcome = None       # how the last batch ended, shown until the clip list changes
        self.apply_theme("night" if system_prefers_dark() else "light")
        self._build_ui()
        self._load_settings()
        self.apply_theme(self.appearance or self.theme)     # again, now that every widget exists
        self.v_fps.trace_add("write", lambda *_: [self._refresh_row(e) for e in self.entries.values()])
        self.bind("<Control-Return>", lambda e: self.start())
        self.after(100, self._poll)
        self.after(50, lambda: dark_title_bar(self, self.theme == "night"))
        self._update_status()
        self._show_panel()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ theme
    def apply_theme(self, name):
        """Restyle everything for 'light' or 'night'. Uses ttk's 'clam' theme in both modes: Windows'
        native theme can't be recoloured, and one look in both modes is easier to read."""
        self.theme = name
        P.clear()
        P.update(PALETTES[name])
        st = self.style
        if "clam" in st.theme_names():
            st.theme_use("clam")
        f = ("Segoe UI", 10)
        row_h = tkfont.Font(self, font=f).metrics("linespace") + int(10 * self.px)
        self.configure(bg=P["bg"])
        st.configure(".", background=P["bg"], foreground=P["text"], fieldbackground=P["field"],
                     bordercolor=P["border"], lightcolor=P["bg"], darkcolor=P["bg"], troughcolor=P["track"],
                     selectbackground=P["sel"], selectforeground=P["sel_text"], insertcolor=P["text"],
                     focuscolor=P["accent"], font=f)
        st.map(".", foreground=[("disabled", P["disabled"])])
        st.configure("TFrame", background=P["bg"])
        st.configure("TLabel", background=P["bg"], foreground=P["text"])
        st.configure("Sub.TLabel", foreground=P["sub"])
        st.configure("Title.TLabel", font=("Segoe UI", 22, "bold"))
        st.configure("Version.TLabel", foreground=P["sub"], font=("Segoe UI", 10))
        st.configure("Section.TLabel", font=("Segoe UI", 13, "bold"))
        st.configure("Big.TLabel", font=("Segoe UI", 11, "bold"))
        for w in ("TCheckbutton", "TRadiobutton"):
            st.configure(w, background=P["bg"], foreground=P["text"], indicatorbackground=P["field"],
                         indicatorforeground=P["text"], upperbordercolor=P["border"], lowerbordercolor=P["border"])
            st.map(w, background=[("active", P["bg"])], indicatorbackground=[("pressed", P["btn"])])
        st.configure("TButton", background=P["btn"], foreground=P["text"], bordercolor=P["border"],
                     lightcolor=P["btn"], darkcolor=P["btn"], padding=(10, 4), focusthickness=1)
        st.map("TButton", background=[("disabled", P["bg"]), ("pressed", P["btn_hover"]), ("active", P["btn_hover"])],
               foreground=[("disabled", P["disabled"])], lightcolor=[("active", P["btn_hover"])],
               darkcolor=[("active", P["btn_hover"])])
        st.configure("Accent.TButton", background=P["accent"], foreground=P["on_accent"], bordercolor=P["accent"],
                     lightcolor=P["accent"], darkcolor=P["accent"], font=("Segoe UI", 11, "bold"), padding=(20, 8))
        st.map("Accent.TButton", background=[("disabled", P["btn"]), ("pressed", P["accent_hover"]),
                                             ("active", P["accent_hover"])],
               foreground=[("disabled", P["disabled"])], lightcolor=[("active", P["accent_hover"])],
               darkcolor=[("active", P["accent_hover"])])
        st.configure("Icon.TButton", font=("Segoe UI Symbol", 13), padding=(6, 1), width=2)
        for w in ("TEntry", "TSpinbox", "TCombobox"):
            st.configure(w, fieldbackground=P["field"], foreground=P["text"], bordercolor=P["border"],
                         lightcolor=P["field"], darkcolor=P["field"], arrowcolor=P["text"], insertcolor=P["text"],
                         background=P["btn"])
            st.map(w, fieldbackground=[("readonly", P["field"]), ("disabled", P["bg"])],
                   foreground=[("disabled", P["disabled"])], bordercolor=[("focus", P["accent"])],
                   selectbackground=[("readonly", P["field"])], selectforeground=[("readonly", P["text"])])
        st.configure("Treeview", background=P["field"], fieldbackground=P["field"], foreground=P["text"],
                     bordercolor=P["border"], lightcolor=P["field"], darkcolor=P["field"], rowheight=row_h, font=f)
        st.map("Treeview", background=[("selected", P["sel"])], foreground=[("selected", P["sel_text"])])
        st.configure("Treeview.Heading", background=P["head"], foreground=P["text"], bordercolor=P["border"],
                     lightcolor=P["head"], darkcolor=P["head"], relief="flat", font=("Segoe UI", 10, "bold"))
        st.map("Treeview.Heading", background=[("active", P["btn_hover"])])
        st.configure("Horizontal.TProgressbar", background=P["accent"], troughcolor=P["track"],
                     bordercolor=P["track"], lightcolor=P["accent"], darkcolor=P["accent"], thickness=int(8 * self.px))
        st.configure("Vertical.TScrollbar", background=P["btn"], troughcolor=P["bg"], bordercolor=P["border"],
                     arrowcolor=P["text"], lightcolor=P["btn"], darkcolor=P["btn"])
        st.map("Vertical.TScrollbar", background=[("active", P["btn_hover"])])
        st.configure("TSeparator", background=P["border"])
        st.configure("Panel.TFrame", background=P["panel"], bordercolor=P["border"], relief="solid", borderwidth=1)
        st.configure("PanelIn.TFrame", background=P["panel"])
        st.configure("Panel.TLabel", background=P["panel"], foreground=P["text"])
        st.configure("PanelSub.TLabel", background=P["panel"], foreground=P["sub"])
        st.configure("PanelBold.TLabel", background=P["panel"], foreground=P["text"], font=("Segoe UI", 10, "bold"))
        st.configure("PanelTitle.TLabel", background=P["panel"], foreground=P["text"], font=("Segoe UI", 12, "bold"))
        for lvl in ("ok", "check", "bad"):
            st.configure(f"Panel{lvl.title()}.TLabel", background=P["panel"], foreground=P[f"{lvl}_text"],
                         font=("Segoe UI", 10, "bold"))
        st.configure("Status.TFrame", background=P["head"])
        st.configure("Status.TLabel", background=P["head"], foreground=P["text"], font=("Segoe UI", 10, "bold"))
        st.configure("StatusSub.TLabel", background=P["head"], foreground=P["sub"])
        st.configure("StatusLink.TLabel", background=P["head"], foreground=P["link"],
                     font=("Segoe UI", 10, "underline"))
        # dropdown lists of comboboxes are plain tk listboxes
        for opt, key in (("background", "field"), ("foreground", "text"), ("selectBackground", "sel"),
                         ("selectForeground", "sel_text")):
            self.option_add(f"*TCombobox*Listbox.{opt}", P[key])
        self._restyle_widgets(self)
        for w, fn in list(self._themed):
            try:
                fn(w)
            except tk.TclError:
                self._themed.remove((w, fn))
        for tree in ("tree", "ctree"):
            if hasattr(self, tree):
                self._tag_colours()
        if hasattr(self, "_gh_lbl"):
            self._gh_img = self._github_image()
            self._gh_lbl.configure(image=self._gh_img)
        if hasattr(self, "btn_theme"):
            night = name == "night"
            self.btn_theme.configure(text="\u2600" if night else "\u263e")
            self._theme_tip.text = "Switch to light mode" if night else "Switch to night mode"
        if hasattr(self, "_status_dot"):
            self._update_status()

    def _restyle_widgets(self, w):
        """Combobox dropdowns already created keep their old colours: recolour them."""
        for child in w.winfo_children():
            if isinstance(child, ttk.Combobox):
                try:
                    pop = self.tk.call("ttk::combobox::PopdownWindow", child)
                    self.tk.call(f"{pop}.f.l", "configure", "-background", P["field"], "-foreground", P["text"],
                                 "-selectbackground", P["sel"], "-selectforeground", P["sel_text"])
                except tk.TclError:
                    pass
            self._restyle_widgets(child)

    def _tag_colours(self):
        for tag, key in (("missing", "bad"), ("ok", "ok"), ("review", "check"), ("error", "bad")):
            self.tree.tag_configure(tag, background=P[key], foreground=P["text"])
        if hasattr(self, "ctree"):
            for lvl in ("ok", "check", "bad"):
                self.ctree.tag_configure(lvl, background=P[lvl], foreground=P["text"])

    def toggle_theme(self):
        self.appearance = "light" if self.theme == "night" else "night"
        log.info("appearance: %s", self.appearance)
        self.apply_theme(self.appearance)
        dark_title_bar(self, self.theme == "night")
        self._save_settings()

    def _theme_tk(self, widget, fn):
        """Register a plain tk widget to be recoloured on every theme change (and colour it now)."""
        self._themed.append((widget, fn))
        fn(widget)
        return widget

    def _section(self, number, title, **pack):
        """A numbered section title ("(1) Clips and scripts") and the frame for its contents."""
        outer = ttk.Frame(self, padding=(16, 6, 16, 0))
        outer.pack(**pack)
        head = ttk.Frame(outer)
        head.pack(fill="x", pady=(0, 6))
        d = int(24 * self.px)
        badge = tk.Canvas(head, width=d, height=d, highlightthickness=0, borderwidth=0)

        def paint(c, d=d, number=number):
            c.configure(background=P["bg"])
            c.delete("all")
            c.create_oval(2, 2, d - 2, d - 2, outline=P["accent"], width=max(2, int(2 * self.px)))
            c.create_text(d / 2, d / 2, text=str(number), fill=P["text"], font=("Segoe UI", 10, "bold"))
        self._theme_tk(badge, paint)
        badge.pack(side="left")
        ttk.Label(head, text=title, style="Section.TLabel").pack(side="left", padx=(8, 0))
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        return body

    # ------------------------------------------------------------ layout
    def _build_ui(self):
        head = ttk.Frame(self, padding=(16, 10, 16, 2))
        head.pack(fill="x")
        ttk.Label(head, text=core.APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(head, text=f"v{core.APP_VERSION}", style="Version.TLabel").pack(side="left", anchor="s",
                                                                                padx=(8, 0), pady=(0, 7))
        self._github_link(head).pack(side="right", anchor="center")
        self.btn_theme = ttk.Button(head, style="Icon.TButton", command=self.toggle_theme)
        self.btn_theme.pack(side="right", padx=(0, 8))
        self._theme_tip = _Tooltip(self.btn_theme, "")

        # ---- status bar (packed now so it keeps its place at the bottom)
        self._build_status_bar()

        # ---- clips: list on the left, the selected clip on the right
        qf = self._section(1, "Clips and scripts", fill="x")
        left = ttk.Frame(qf)
        left.pack(side="left", fill="y")
        bar = ttk.Frame(left)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="+ Add clips…", command=self.add_clips).pack(side="left")
        ttk.Button(bar, text="+ Add a folder…", command=self.add_folder).pack(side="left", padx=6)
        ttk.Button(bar, text="Remove", command=self.remove_selected).pack(side="right")
        ttk.Button(bar, text="Clear all", command=self.clear_all).pack(side="right", padx=6)
        cols = ("clip", "status")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=5, selectmode="browse")
        self.tree.heading("clip", text="Clip")
        self.tree.heading("status", text="Status")
        self.tree.column("clip", width=int(250 * self.px), anchor="w", stretch=True)
        self.tree.column("status", width=int(170 * self.px), anchor="w", stretch=False)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_selected())
        self.tree.bind("<Double-1>", lambda e: self.edit_script())
        self.tree.bind("<Return>", lambda e: self.edit_script())
        self.tree.bind("<Delete>", lambda e: self.remove_selected())

        self.panel = ttk.Frame(qf, style="Panel.TFrame", padding=(14, 10))
        self.panel.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self._build_clip_panel()
        self._build_empty_panel()

        # ---- settings
        sf = self._section(2, "Settings", fill="x")
        r1 = ttk.Frame(sf)
        r1.pack(fill="x")
        ttk.Label(r1, text="Listening quality").grid(row=0, column=0, sticky="w")
        self.var_model = tk.StringVar(value=list(MODELS)[1])
        ttk.Combobox(r1, textvariable=self.var_model, values=list(MODELS), state="readonly",
                     width=30).grid(row=0, column=1, padx=(8, 16), sticky="w")
        ttk.Label(r1, text="Language").grid(row=0, column=2, sticky="w")
        self.var_lang = tk.StringVar(value="Auto-detect")
        ttk.Combobox(r1, textvariable=self.var_lang, values=list(LANGS), state="readonly",
                     width=16).grid(row=0, column=3, padx=(8, 16), sticky="w")
        ttk.Label(r1, text="Max characters").grid(row=0, column=4, sticky="w")
        self.var_maxchars = tk.IntVar(value=40)
        ttk.Spinbox(r1, from_=12, to=120, textvariable=self.var_maxchars, width=5).grid(
            row=0, column=5, padx=8, sticky="w")
        ttk.Label(r1, text="Max words").grid(row=0, column=6, sticky="w", padx=(6, 0))
        self.var_maxwords = tk.IntVar(value=0)
        ttk.Spinbox(r1, from_=0, to=20, textvariable=self.var_maxwords, width=4).grid(
            row=0, column=7, padx=8, sticky="w")

        r2 = ttk.Frame(sf)
        r2.pack(fill="x", pady=(10, 0))
        ttk.Label(r2, text="Save to  (blank = beside each clip)").pack(side="left")
        self.var_out = tk.StringVar(value="")
        self.out_entry = ttk.Entry(r2, textvariable=self.var_out)
        self.out_entry.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(r2, text="Choose folder\u2026", command=self.choose_out).pack(side="left")
        ttk.Button(r2, text="Clear", command=lambda: self.var_out.set("")).pack(side="left", padx=(6, 0))

        self.adv_open = tk.BooleanVar(value=False)
        ttk.Checkbutton(sf, text="More options", variable=self.adv_open, command=self._toggle_adv).pack(
            anchor="w", pady=(6, 0))
        self.adv = ttk.Frame(sf)
        self.v_brackets = tk.BooleanVar(value=True)
        self.v_labels = tk.BooleanVar(value=False)
        self.v_lines = tk.BooleanVar(value=True)
        self.v_zero = tk.BooleanVar(value=True)
        self.v_prime = tk.BooleanVar(value=True)
        self.v_unheard = tk.BooleanVar(value=False)
        self.v_cache = tk.BooleanVar(value=True)
        self.v_words = tk.BooleanVar(value=False)
        self.v_mincue = tk.DoubleVar(value=0.8)
        self.v_bridge = tk.DoubleVar(value=0.4)
        self.v_maxsec = tk.DoubleVar(value=5.0)
        self.v_fps = tk.StringVar(value="30")
        opts = [
            (self.v_brackets, "Ignore [bracketed notes] in the script"),
            (self.v_labels, "Script has speaker labels like  'Sam:'  (remove them)"),
            (self.v_lines, "Keep the writer's line breaks as subtitle breaks"),
            (self.v_zero, "Premiere fix: never start the first subtitle at 00:00:00,000"),
            (self.v_prime, "Tell the listener the names/brands in the script (helps spelling)"),
            (self.v_unheard, "Also include lines that were never heard (timing is a guess)"),
            (self.v_cache, "Re-use the saved transcript if the clip hasn't changed (faster)"),
            (self.v_words, "Also save every word's timing (.words.json / .words.srt) for other tools"),
        ]
        for i, (v, txt) in enumerate(opts):
            ttk.Checkbutton(self.adv, text=txt, variable=v).grid(row=i // 2, column=i % 2, sticky="w",
                                                                 padx=(0, 24), pady=1)
        nums = ttk.Frame(self.adv)
        nums.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        mf = ttk.Frame(self.adv)
        mf.grid(row=6, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.v_modeldir = tk.StringVar(value=os.environ.get("SCRIPTSYNC_MODEL_DIR", ""))
        ttk.Label(mf, text="Speech model folder  (blank = default)").pack(side="left")
        ttk.Entry(mf, textvariable=self.v_modeldir, width=48).pack(side="left", padx=8)
        ttk.Button(mf, text="Choose folder\u2026", command=self.choose_model_dir).pack(side="left")
        ttk.Button(mf, text="Clear", command=lambda: self.v_modeldir.set("")).pack(side="left", padx=(6, 0))
        ttk.Label(self.adv, style="Sub.TLabel", text=(
            f"Default: {core.default_model_dir()}   (models are 150 MB-1.6 GB; changing the folder downloads "
            "them again)")
                  ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(2, 0))
        tf = ttk.Frame(self.adv)
        tf.grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(tf, text="Troubleshooting").pack(side="left")
        ttk.Button(tf, text="Open log folder", command=self.open_logs).pack(side="left", padx=8)
        ttk.Button(tf, text="Copy diagnostic info", command=self.copy_diagnostics).pack(side="left")
        for lbl, var, lo, hi, inc in (("Shortest subtitle (sec)", self.v_mincue, 0.2, 3, 0.1),
                                      ("Hold through pauses up to (sec)", self.v_bridge, 0, 2, 0.1),
                                      ("Longest subtitle (sec)", self.v_maxsec, 2, 15, 0.5)):
            ttk.Label(nums, text=lbl).pack(side="left")
            ttk.Spinbox(nums, from_=lo, to=hi, increment=inc, textvariable=var, width=5).pack(
                side="left", padx=(6, 20))
        ttk.Label(nums, text="Frame rate for audio-only clips").pack(side="left")
        ttk.Combobox(nums, textvariable=self.v_fps, values=list(FRAME_RATES), state="readonly",
                     width=10).pack(side="left", padx=(6, 0))

        # ---- run
        rf = ttk.Frame(self, padding=(16, 10, 16, 2))
        rf.pack(fill="x")
        self.btn_run = ttk.Button(rf, text="▶  Sync", style="Accent.TButton", command=self.start)
        self.btn_run.pack(side="left")
        self.btn_cancel = ttk.Button(rf, text="Stop", command=self.stop, state="disabled")
        self.btn_cancel.pack(side="left", padx=8)
        self.progress = ttk.Progressbar(rf, maximum=1000)
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 0))

        # ---- review
        vf = self._section(3, "Review", fill="both", expand=True, pady=(0, 10))
        top = ttk.Frame(vf)
        top.pack(fill="x", pady=(0, 6))
        self.summary = ttk.Label(top, text="Select a finished clip to see its subtitles.", style="Big.TLabel")
        self.summary.pack(side="left")
        self.btn_rep = ttk.Button(top, text="Open review sheet", command=self.open_report, state="disabled")
        self.btn_rep.pack(side="right")
        self.btn_srt = ttk.Button(top, text="Show .srt in folder", command=self.open_srt, state="disabled")
        self.btn_srt.pack(side="right", padx=6)
        self.btn_breaks = ttk.Button(top, text="Apply line breaks\u2026", command=self.apply_line_breaks,
                                     state="disabled")
        self.btn_breaks.pack(side="right", padx=(6, 0))
        self.btn_prompt = ttk.Button(top, text="Copy AI prompt", command=self.copy_prompt,
                                     state="disabled")
        self.btn_prompt.pack(side="right")

        self.extra = ttk.Label(vf, style="Sub.TLabel", wraplength=1000, justify="left")
        self.extra.pack(side="bottom", anchor="w", pady=(6, 0))
        cf = ttk.Frame(vf)
        cf.pack(fill="both", expand=True)
        cols = ("n", "time", "flag", "text", "notes")
        self.ctree = ttk.Treeview(cf, columns=cols, show="headings", selectmode="browse")
        for c, txt, w, anc, st in (("n", "#", 40, "center", False), ("time", "Time", 200, "w", False),
                                   ("flag", "Check?", 70, "center", False), ("text", "Subtitle", 380, "w", True),
                                   ("notes", "What to look at", 380, "w", True)):
            self.ctree.heading(c, text=txt)
            self.ctree.column(c, width=w, anchor=anc, stretch=st)
        sb = ttk.Scrollbar(cf, orient="vertical", command=self.ctree.yview)
        self.ctree.configure(yscrollcommand=sb.set)
        self.ctree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self._tag_colours()

    def _github_image(self):
        # 52 px from 150% display scaling up (which can come out as 1.4999.. here, hence 1.4);
        # the white mark in night mode
        return tk.PhotoImage(data=GITHUB_MARK[("light" if self.theme == "night" else "dark",
                                               52 if self.px >= 1.4 else 26)])

    def _github_link(self, parent):
        """The GitHub mark, top right: opens the project page."""
        self._gh_img = self._github_image()
        lbl = self._gh_lbl = ttk.Label(parent, image=self._gh_img, cursor="hand2", padding=4)
        lbl.bind("<Button-1>", lambda e: webbrowser.open(core.APP_URL))
        _Tooltip(lbl, f"{core.APP_NAME} on GitHub \u2014 by {core.APP_AUTHOR}")
        return lbl

    # ------------------------------------------------------------ selected-clip panel
    def _build_clip_panel(self):
        b = self.clip_box = ttk.Frame(self.panel, style="PanelIn.TFrame")
        b.columnconfigure(1, weight=1)
        top = ttk.Frame(b, style="PanelIn.TFrame")
        top.grid(row=0, column=0, columnspan=3, sticky="we", pady=(0, 8))
        self.p_title = ttk.Label(top, style="PanelTitle.TLabel")
        self.p_title.pack(side="left")
        self.p_info = ttk.Label(top, style="PanelSub.TLabel")
        self.p_info.pack(side="left", padx=(10, 0))

        def key(row, text):
            ttk.Label(b, text=text, style="PanelSub.TLabel", width=11).grid(row=row, column=0, sticky="w", pady=3)
        key(1, "Script")
        self.p_script = ttk.Label(b, style="PanelBold.TLabel")
        self.p_script.grid(row=1, column=1, sticky="w")
        ttk.Button(b, text="Edit or replace…", command=self.edit_script).grid(row=1, column=2, sticky="e")
        key(2, "Frame rate")
        self.var_clip_fps = tk.StringVar(value=AUTO_FPS)
        self.cb_clip_fps = ttk.Combobox(b, textvariable=self.var_clip_fps, state="readonly", width=30,
                                        values=[AUTO_FPS] + list(FRAME_RATES))
        self.cb_clip_fps.grid(row=2, column=1, columnspan=2, sticky="w", pady=3)
        self.cb_clip_fps.bind("<<ComboboxSelected>>", lambda e: self.set_clip_fps())
        key(3, "Last sync")
        self.p_last = ttk.Label(b, style="Panel.TLabel")
        self.p_last.grid(row=3, column=1, sticky="w")
        self.p_show = ttk.Button(b, text="Show in folder", command=lambda: reveal(self._last_output))
        self.p_show.grid(row=3, column=2, sticky="e")
        b.rowconfigure(4, weight=1)
        bottom = ttk.Frame(b, style="PanelIn.TFrame")
        bottom.grid(row=5, column=0, columnspan=3, sticky="we", pady=(8, 0))
        self.p_result = ttk.Label(bottom, style="PanelBold.TLabel")
        self.p_result.pack(side="left")
        self.p_result_more = ttk.Label(bottom, style="PanelSub.TLabel")
        self.p_result_more.pack(side="left", padx=(8, 0))
        self.p_resync = ttk.Button(bottom, command=self.resync_selected)
        self.p_resync.pack(side="right")

    def _build_empty_panel(self):
        b = self.empty_box = ttk.Frame(self.panel, style="PanelIn.TFrame")
        ttk.Label(b, text="Add the clips you want subtitles for", style="PanelTitle.TLabel").pack(pady=(14, 6))
        ttk.Label(b, style="PanelSub.TLabel", justify="center", wraplength=int(520 * self.px), text=(
            "A script saved next to its clip with the same name (clip.mp4 + clip.docx / .txt / .srt) is paired "
            "automatically. Otherwise double-click a clip to paste its script.")).pack()
        row = ttk.Frame(b, style="PanelIn.TFrame")
        row.pack(pady=(12, 0))
        ttk.Button(row, text="+ Add clips…", style="Accent.TButton", command=self.add_clips).pack(side="left")
        ttk.Button(row, text="+ Add a folder…", command=self.add_folder).pack(side="left", padx=8)

    def _show_panel(self):
        """Fill the right-hand panel for the selected clip (or the 'add clips' prompt)."""
        e = self._selected()
        if not e:
            self.clip_box.pack_forget()
            self.empty_box.pack(fill="both", expand=True)
            return
        self.empty_box.pack_forget()
        self.clip_box.pack(fill="both", expand=True)
        job = e["job"]
        self.p_title.configure(text=job.label())
        pr = e.get("probe")
        if pr:
            bits = [self._clock(pr["duration"])] if pr.get("duration") else []
            bits.append(f"{pr['width']}\u00d7{pr['height']}" if pr.get("width") else "audio only")
            self.p_info.configure(text=" \u00b7 ".join(bits))
        else:
            self.p_info.configure(text="")
        if job.script_text:
            sc = "(pasted text)"
        elif job.script_path:
            sc = os.path.basename(job.script_path)
        else:
            sc = "None yet: double-click the clip or use Edit or replace…"
        if job.line_breaks and (job.script_text or job.script_path):
            sc += "  + your line breaks"
        self.p_script.configure(text=sc, style="PanelBold.TLabel" if (job.script_text or job.script_path)
                                else "PanelBad.TLabel")
        self._sync_fps_box(e)
        last = e["result"].srt_path if e["result"] else next(
            iter(core.previous_outputs(job.video, self.var_out.get().strip() or None)), "")
        name = os.path.basename(last) if last else "Not synced yet"
        if len(name) > 46:                      # keep the date/time end visible
            name = name[:20] + "\u2026" + name[-25:]
        self.p_last.configure(text=name)
        self.p_show.configure(state="normal" if last else "disabled")
        self._last_output = last
        r = e["result"]
        if r:
            flagged = r.n_check + r.n_bad
            self.p_result.configure(text=f"{flagged} to review" if flagged else "Done",
                                    style="PanelCheck.TLabel" if flagged else "PanelOk.TLabel")
            self.p_result_more.configure(text=f"\u00b7 {r.match_pct:.0f}% heard \u00b7 {len(r.cues)} subtitles")
        elif e["status"].startswith(("Error", "Stopped")):
            self.p_result.configure(text=e["status"], style="PanelBad.TLabel")
            self.p_result_more.configure(text="")
        else:
            self.p_result.configure(text=e["status"] or ("Ready" if (job.script_text or job.script_path)
                                                          else "Needs a script"), style="PanelBold.TLabel")
            self.p_result_more.configure(text="")
        again = bool(r) or e.get("synced_before")
        self.p_resync.configure(text="\u21bb  Resync this clip" if again else "\u25b6  Sync this clip",
                                state="normal" if (job.script_text or job.script_path) and not self._busy()
                                else "disabled")

    def edit_script(self):
        """Double-click / Edit or replace…: paste or edit the script, or import a file instead."""
        e = self._selected()
        if not e:
            return
        if self._busy():
            messagebox.showinfo("Syncing", "Wait for the current sync to finish (or press Stop) first.")
            return
        job = e["job"]
        initial = job.script_text or ""
        if not initial and job.script_path:
            try:
                initial = core.read_script_file(job.script_path)
            except (OSError, core.SyncError) as ex:
                log.warning("couldn't read the script to edit it: %s", ex)
        dlg = PasteDialog(self, f"Script for {job.label()}", initial, allow_import=True)
        self.wait_window(dlg)
        if dlg.result_path:
            job.script_path, job.script_text = dlg.result_path, None
        elif dlg.result and not (job.script_path and dlg.result == initial.strip()):
            job.script_text, job.script_path = dlg.result, None
        else:
            return                                   # cancelled, emptied or unchanged
        job.line_breaks = None
        e["result"] = None
        self._refresh_row(e, status="")
        self._list_changed()
        self._show_panel()

    def resync_selected(self):
        e = self._selected()
        if e and not self._busy() and (e["job"].script_path or e["job"].script_text):
            self._run([e], self.current_settings())

    def _toggle_adv(self):
        if self.adv_open.get():
            self.adv.pack(anchor="w", pady=(4, 0))
        else:
            self.adv.pack_forget()

    # ------------------------------------------------------------ queue ops
    def _add_entry(self, video, script=None, text=None):
        for e in self.entries.values():
            if os.path.abspath(e["job"].video) == os.path.abspath(video):
                if script and not e["job"].script_path and not e["job"].script_text:
                    e["job"].script_path = script
                    self._refresh_row(e)
                return
        job = core.Job(video=video, script_path=script, script_text=text)
        iid = self.tree.insert("", "end", values=("", "", "", "", ""))
        synced_before = bool(core.previous_outputs(video, self.var_out.get().strip() or None))
        self.entries[iid] = {"iid": iid, "job": job, "result": None, "status": "",
                             "synced_before": synced_before}
        self._refresh_row(self.entries[iid])
        if not self.tree.selection():
            self.tree.selection_set(iid)
        # read the clip's frame rate, length and size in the background (ffmpeg takes a moment per clip)
        threading.Thread(target=lambda: self.q.put(("probe", iid, core.probe_clip(video))), daemon=True).start()

    def set_clip_fps(self):
        e = self._selected()
        if not e:
            return
        v = self.var_clip_fps.get()
        e["job"].fps = None if v.startswith("Auto") else FRAME_RATES.get(v, 0.0)
        self._refresh_row(e)

    def _refresh_row(self, e, status=None, match=None):
        job = e["job"]
        if status is not None:
            e["status"] = status
        if job.script_text:
            sc = "(pasted text)"
        elif job.script_path:
            sc = os.path.basename(job.script_path)
        else:
            sc = "⚠ none yet - choose or paste one"
        if job.line_breaks and (job.script_text or job.script_path):
            sc += "  + your line breaks"
        ready = "Ready (synced before)" if e.get("synced_before") else "Ready"
        st = e["status"] or (ready if (job.script_text or job.script_path) else "Needs a script")
        tag = ""
        if not (job.script_text or job.script_path):
            tag = "missing"
        elif st.startswith("Done"):
            tag = "review" if "review" in st else "ok"
        elif st.startswith("Error") or st.startswith("Stopped"):
            tag = "error"
        self.tree.item(e["iid"], values=(job.label(), st), tags=(tag,) if tag else ())
        self._update_run_button()
        if self.tree.selection() == (e["iid"],):
            self._show_panel()

    def _update_run_button(self):
        """'Resync' (restart icon) once every clip that would run has been synced before;
        'Sync' while there's at least one clip that never has."""
        todo = [e for e in self.entries.values() if e["job"].script_path or e["job"].script_text]
        again = bool(todo) and all(e["result"] or e.get("synced_before") for e in todo)
        self.btn_run.config(text="\u21bb  Resync" if again else "\u25b6  Sync")

    def add_clips(self):
        exts = " ".join("*" + x for x in sorted(core.VIDEO_EXTS))
        paths = filedialog.askopenfilenames(title="Choose clips",
                                            filetypes=[("Video / audio", exts), ("All files", "*.*")])
        for p in paths:
            self._add_entry(p, core.find_script_for(p))
        self._after_add()

    def add_folder(self):
        d = filedialog.askdirectory(title="Choose a folder of clips (scripts alongside)")
        if not d:
            return
        pairs = core.scan_folder(d)
        if not pairs:
            messagebox.showinfo("Nothing found", "No video files were found in that folder.")
            return
        for v, s in pairs:
            self._add_entry(v, s)
        self._after_add()

    def _after_add(self):
        self._list_changed()

    def _list_changed(self):
        """The clip list or a script changed: the status bar shows the list's state again."""
        self._outcome = None
        self._update_status()

    # ------------------------------------------------------------ status bar
    def _build_status_bar(self):
        bar = ttk.Frame(self, style="Status.TFrame", padding=(16, 5))
        bar.pack(side="bottom", fill="x")
        ttk.Separator(self).pack(side="bottom", fill="x")
        d = int(12 * self.px)
        self._dot_key = "dot_idle"
        self._status_dot = tk.Canvas(bar, width=d, height=d, highlightthickness=0, borderwidth=0)

        def paint(c, d=d):
            c.configure(background=P["head"])
            c.delete("all")
            c.create_oval(1, 1, d - 1, d - 1, fill=P[self._dot_key], outline=P["dot_ring"])
        self._paint_dot = paint
        self._theme_tk(self._status_dot, paint)
        self._status_dot.pack(side="left")
        self._status_state = ttk.Label(bar, style="Status.TLabel")
        self._status_state.pack(side="left", padx=(8, 10))
        self._status_detail = ttk.Label(bar, style="StatusSub.TLabel")
        self._status_detail.pack(side="left", fill="x", expand=True)
        self._status_right = ttk.Label(bar, style="StatusSub.TLabel")
        self._status_right.pack(side="right")
        self._status_right.bind("<Button-1>", lambda e: self._status_click())

    @staticmethod
    def _clock(secs):
        secs = int(max(secs, 0))
        return f"{secs // 60}:{secs % 60:02d}"

    def _status(self):
        """-> (dot colour key, state, detail, right-hand text, clickable?) for the status bar."""
        ri = self._run_info
        if ri:
            now = time.monotonic()
            e = self.entries.get(ri["cur"]) if ri["cur"] else None
            k = ri["order"].index(ri["cur"]) + 1 if ri["cur"] in ri["order"] else 1
            if self.cancel.is_set():
                detail = "Stopping after the current step…"
            elif e:
                detail = f"Clip {k} of {ri['n']} · {e['job'].label()} · {ri['msg']} ({int(ri['frac'] * 100)}%)"
            else:
                detail = f"Starting {ri['n']} clip(s)…"
            right = f"{ri['last'][0]} took {self._clock(ri['last'][1])}" if ri["last"] else ""
            return "dot_run", f"Running…  {self._clock(now - ri['t0'])}", detail, right, False
        if self._outcome:
            return self._outcome
        if not self.entries:
            return "dot_idle", "Standing by", "Add clips to begin.", "", False
        missing = [e for e in self.entries.values() if not (e["job"].script_path or e["job"].script_text)]
        if missing:
            first = missing[0]["job"].label()
            more = f" and {len(missing) - 1} more" if len(missing) > 1 else ""
            return ("dot_wait", "Clips loaded",
                    f"Waiting for a script: {first}{more}. Double-click a clip to add its script.",
                    "", False)
        n = len(self.entries)
        return "dot_wait", "Ready", f"{n} clip(s) ready. Press {self.btn_run.cget('text').split()[-1]} or Ctrl+Enter.", \
            "", False

    def _update_status(self):
        key, state, detail, right, link = self._status()
        if key != self._dot_key:
            self._dot_key = key
            self._paint_dot(self._status_dot)
        self._status_state.configure(text=state)
        self._status_detail.configure(text=detail)
        self._status_right.configure(text=right, style="StatusLink.TLabel" if link else "StatusSub.TLabel",
                                     cursor="hand2" if link else "")

    def _tick(self):
        if self._run_info:
            self._update_status()
            self.after(1000, self._tick)

    def _status_click(self):
        if not (self._outcome and self._outcome[4]):
            return
        errs = self._outcome_errors
        text = "\n\n".join(f"{name}:\n{msg}" for name, msg in errs)
        if messagebox.askyesno("What went wrong", f"{text}\n\nOpen the log folder for the full details?"):
            self.open_logs()

    def _finish_status(self, total):
        ri, self._run_info = self._run_info, None
        if not ri:
            return
        took = time.monotonic() - ri["t0"]
        self._outcome_errors = ri["errors"]
        if self.cancel.is_set():
            cur = self.entries.get(ri["cur"])
            during = f" during {cur['job'].label()}" if cur else ""
            self._outcome = ("dot_err", "Stopped", f"You pressed Stop{during}. {ri['synced']} of {total} clip(s) synced.",
                             f"after {self._clock(took)}", False)
        elif ri["errors"]:
            name, msg = ri["errors"][0]
            more = f" (+{len(ri['errors']) - 1} more)" if len(ri["errors"]) > 1 else ""
            self._outcome = ("dot_err", "Error", f"{name}: {msg}{more}" +
                             (f" · {ri['synced']} other clip(s) synced" if ri["synced"] else ""), "Details…", True)
        else:
            review = f" · {ri['flagged']} subtitle(s) to review" if ri["flagged"] else ""
            avg = f"avg {self._clock(took / ri['synced'])} per clip" if ri["synced"] > 1 else ""
            self._outcome = ("dot_run", f"Finished in {self._clock(took)}",
                             f"{ri['synced']} of {total} clip(s) synced{review}", avg, False)
        self._update_status()

    def _clip_finished(self, iid):
        ri = self._run_info
        if ri and iid in ri["clip_t0"]:
            e = self.entries.get(iid)
            ri["last"] = (e["job"].label() if e else "", time.monotonic() - ri["clip_t0"][iid])

    def _selected(self):
        sel = self.tree.selection()
        return self.entries.get(sel[0]) if sel else None

    def remove_selected(self):
        e = self._selected()
        if e and not self._busy():
            self.tree.delete(e["iid"])
            del self.entries[e["iid"]]
            self.clear_review()
            self._update_run_button()
            self._list_changed()

    def clear_all(self):
        if self._busy():
            return
        for iid in list(self.entries):
            self.tree.delete(iid)
        self.entries.clear()
        self.clear_review()
        self._update_run_button()
        self._list_changed()

    def choose_out(self):
        d = filedialog.askdirectory(title="Where should the .srt files go?")
        if d:
            self.var_out.set(d)

    # ------------------------------------------------------------ troubleshooting
    def open_logs(self):
        d = core.log_dir()
        os.makedirs(d, exist_ok=True)
        open_path(d)

    def copy_diagnostics(self):
        self.clipboard_clear()
        self.clipboard_append(core.diagnostics())
        messagebox.showinfo("Diagnostic info copied", (
            "Version, system details and the end of the log are on the clipboard, ready to paste into a "
            "GitHub issue.\n\nFolder paths are hidden, but clip names are included: read it before "
            "posting it publicly."))

    def report_callback_exception(self, exc, val, tb):
        """Errors in button handlers etc. (tkinter would print them to a console nobody sees)."""
        log.error("unexpected error in the window", exc_info=(exc, val, tb))
        messagebox.showerror("Something went wrong", (
            f"{exc.__name__}: {val}\n\nThe details are in the log (More options > Open log folder). "
            "Please include it if you report this."))

    def choose_model_dir(self):
        d = filedialog.askdirectory(title="Where should the speech model files be kept?")
        if not d:
            return
        try:
            self.v_modeldir.set(core.check_model_dir(d))
        except core.SyncError as e:
            messagebox.showerror("Can't use that folder", str(e))

    # ------------------------------------------------------------ settings
    def current_settings(self) -> core.Settings:
        try:
            maxc = max(10, int(self.var_maxchars.get()))
        except (tk.TclError, ValueError):
            maxc = 40
        try:
            maxw = max(0, int(self.var_maxwords.get()))
        except (tk.TclError, ValueError):
            maxw = 0

        def num(v, d):
            try:
                return float(v.get())
            except (tk.TclError, ValueError):
                return d
        return core.Settings(
            model=MODELS.get(self.var_model.get(), "small"),
            language=LANGS.get(self.var_lang.get(), "auto"),
            max_chars=maxc,
            max_words=maxw,
            export_words=self.v_words.get(),
            max_cue_seconds=num(self.v_maxsec, 5.0),
            min_cue_seconds=num(self.v_mincue, 0.8),
            bridge_gap=num(self.v_bridge, 0.4),
            fps=FRAME_RATES.get(self.v_fps.get(), 30.0),
            ignore_brackets=self.v_brackets.get(),
            strip_speaker_labels=self.v_labels.get(),
            keep_script_lines=self.v_lines.get(),
            premiere_zero_fix=self.v_zero.get(),
            prime_vocab=self.v_prime.get(),
            include_unheard=self.v_unheard.get(),
            use_cache=self.v_cache.get(),
            model_dir=self.v_modeldir.get().strip(),
        )

    def _save_settings(self):
        data = {"model": self.var_model.get(), "lang": self.var_lang.get(), "maxc": self.var_maxchars.get(),
                "out": self.var_out.get(), "brackets": self.v_brackets.get(), "labels": self.v_labels.get(),
                "lines": self.v_lines.get(), "zero": self.v_zero.get(), "prime": self.v_prime.get(),
                "unheard": self.v_unheard.get(), "cache": self.v_cache.get(),
                "mincue": self.v_mincue.get(), "bridge": self.v_bridge.get(), "maxsec": self.v_maxsec.get(),
                "fps": self.v_fps.get(), "modeldir": self.v_modeldir.get(), "appearance": self.appearance,
                "maxwords": self.var_maxwords.get(), "words": self.v_words.get()}
        try:
            json.dump(data, open(settings_path(), "w"))
        except Exception:
            pass

    def _load_settings(self):
        try:
            d = json.load(open(settings_path()))
        except Exception:
            return
        try:
            if d.get("model") in MODELS:
                self.var_model.set(d["model"])
            if d.get("lang") in LANGS:
                self.var_lang.set(d["lang"])
            self.var_maxchars.set(int(d.get("maxc", 40)))
            self.var_out.set(d.get("out", ""))
            self.var_maxwords.set(int(d.get("maxwords", 0)))
            for k, v in (("brackets", self.v_brackets), ("labels", self.v_labels), ("lines", self.v_lines),
                         ("zero", self.v_zero), ("prime", self.v_prime), ("unheard", self.v_unheard),
                         ("cache", self.v_cache), ("words", self.v_words)):
                if k in d:
                    v.set(bool(d[k]))
            if d.get("fps") in FRAME_RATES:
                self.v_fps.set(d["fps"])
            if d.get("appearance") in PALETTES:
                self.appearance = d["appearance"]
            if d.get("modeldir"):
                self.v_modeldir.set(d["modeldir"])
            for k, v in (("mincue", self.v_mincue), ("bridge", self.v_bridge), ("maxsec", self.v_maxsec)):
                if k in d:
                    v.set(float(d[k]))
        except Exception:
            pass

    # ------------------------------------------------------------ running
    def _busy(self):
        return self.worker is not None and self.worker.is_alive()

    def start(self):
        if self._busy():
            return
        todo = [e for e in self.entries.values() if e["job"].script_path or e["job"].script_text]
        if not self.entries:
            messagebox.showinfo("Nothing to do", "Add a clip and its script first.")
            return
        if not todo:
            messagebox.showinfo("Scripts needed", "None of the clips has a script yet.")
            return
        self._run(todo, self.current_settings())

    def _run(self, todo, s):
        out = self.var_out.get().strip() or None
        for e in todo:
            e["job"].out_dir = out
            e["result"] = None
            self._refresh_row(e, status="Waiting…", match="")
        self._save_settings()
        self.cancel.clear()
        self.btn_run.config(state="disabled")
        self.btn_cancel.config(state="normal")
        log.info("batch start: %d clip(s)", len(todo))
        self._batch_t0 = time.monotonic()
        self._outcome = None
        self._run_info = {"t0": self._batch_t0, "order": [e["iid"] for e in todo], "n": len(todo), "cur": None,
                          "msg": "", "frac": 0.0, "clip_t0": {}, "last": None, "errors": [], "synced": 0,
                          "flagged": 0}
        self.worker = threading.Thread(target=self._work, args=(todo, s), daemon=True)
        self.worker.start()
        self._update_status()
        self.after(1000, self._tick)

    def stop(self):
        log.info("Stop pressed")
        self.cancel.set()
        self._update_status()

    def _work(self, todo, s):
        n = len(todo)
        for k, e in enumerate(todo):
            if self.cancel.is_set():
                self.q.put(("row", e["iid"], "Stopped", None))
                continue

            def prog(frac, msg, k=k, e=e):
                self.q.put(("prog", e["iid"], (k + frac) / n, msg, frac))

            try:
                res = core.run_job(e["job"], s, prog, self.cancel)
                self.q.put(("done", e["iid"], res))
            except core.Cancelled:
                self.q.put(("row", e["iid"], "Stopped", None))
            except core.SyncError as ex:
                self.q.put(("row", e["iid"], f"Error: {ex}", None))
            except Exception as ex:  # unexpected; run_job has already logged the traceback
                self.q.put(("row", e["iid"], f"Error: {type(ex).__name__}: {ex} (details in the log)", None))
        self.q.put(("finished", n))

    def _poll(self):
        try:
            while True:
                m = self.q.get_nowait()
                kind = m[0]
                if kind == "prog":
                    _, iid, overall, msg, frac = m
                    self.progress["value"] = overall * 1000
                    e = self.entries.get(iid)
                    if e:
                        self._refresh_row(e, status=f"{msg}…  {int(frac * 100)}%")
                    ri = self._run_info
                    if ri:
                        ri["clip_t0"].setdefault(iid, time.monotonic())
                        ri["cur"], ri["msg"], ri["frac"] = iid, msg, frac
                        self._update_status()
                elif kind == "row":
                    _, iid, st, match = m
                    e = self.entries.get(iid)
                    if e:
                        self._refresh_row(e, status=st, match=match or "")
                        if st.startswith("Error"):
                            self.summary.config(text=st)
                            if self._run_info:
                                self._run_info["errors"].append((e["job"].label(), st[len("Error: "):]))
                        self._clip_finished(iid)
                elif kind == "probe":
                    _, iid, info = m
                    e = self.entries.get(iid)
                    if e:
                        e["probe"], e["detected_fps"] = info, info["fps"]
                        self._refresh_row(e)
                elif kind == "done":
                    _, iid, res = m
                    e = self.entries.get(iid)
                    if e:
                        e["result"] = res
                        e["synced_before"] = True
                        if self._run_info:
                            self._run_info["synced"] += 1
                            self._run_info["flagged"] += res.n_check + res.n_bad
                        self._clip_finished(iid)
                        flagged = res.n_check + res.n_bad
                        st = "Done ✔" if not flagged and not res.warnings else \
                            f"Done - {flagged} to review" if flagged else "Done - see warning"
                        self._refresh_row(e, status=st, match=f"{res.match_pct:.0f}%")
                        if self.tree.selection() == (iid,) or not self.tree.selection():
                            self.show_result(e)
                elif kind == "finished":
                    self.btn_run.config(state="normal")
                    self.btn_cancel.config(state="disabled")
                    self.progress["value"] = 0 if self.cancel.is_set() else 1000
                    done = sum(1 for e in self.entries.values() if e["result"])
                    log.info("batch %s in %.1f s: %d of %d clip(s) synced",
                             "stopped" if self.cancel.is_set() else "finished",
                             time.monotonic() - getattr(self, "_batch_t0", time.monotonic()), done, m[1])
                    self._finish_status(m[1])
                    self._show_panel()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # ------------------------------------------------------------ review
    def clear_review(self):
        self.ctree.delete(*self.ctree.get_children())
        self.summary.config(text="Select a finished clip to see its subtitles.")
        self.extra.config(text="")
        for b in (self.btn_rep, self.btn_srt, self.btn_breaks, self.btn_prompt):
            b.config(state="disabled")

    def show_selected(self):
        e = self._selected()
        self._show_panel()
        if not e:
            self.clear_review()
            return
        if e["result"]:
            self.show_result(e)
        else:
            self.clear_review()
            if e["status"].startswith("Error"):
                self.summary.config(text=e["status"])

    def _sync_fps_box(self, e):
        if not e:
            return
        f = e["job"].fps
        if f is None:
            d = e.get("detected_fps")
            auto = f"Auto ({core.fps_name(d)}, from the clip)" if d else (
                f"Auto (no video: {self.v_fps.get()})" if "detected_fps" in e else AUTO_FPS)
            self.cb_clip_fps.configure(values=[auto] + list(FRAME_RATES))
            self.var_clip_fps.set(auto)
            return
        self.cb_clip_fps.configure(values=[AUTO_FPS] + list(FRAME_RATES))
        self.var_clip_fps.set(next((k for k, v in FRAME_RATES.items() if abs(v - f) < 1e-6), AUTO_FPS))

    def show_result(self, e):
        r = e["result"]
        self.ctree.delete(*self.ctree.get_children())
        for c in r.cues:
            self.ctree.insert("", "end", tags=(c.level,), values=(
                c.index, f"{core.short_tc(c.start)} → {core.short_tc(c.end)}",
                {"ok": "OK", "check": "CHECK", "bad": "BAD"}[c.level], c.text, " | ".join(c.notes)))
        self.summary.config(text=f"{len(r.cues)} subtitles:  {r.n_ok} OK   {r.n_check} check   {r.n_bad} bad   "
                                 f"—  {r.match_pct:.0f}% of the script was heard")
        bits = list(r.warnings)
        if r.fps_source:
            bits.append(f"Frame rate: {core.fps_name(r.fps)} ({r.fps_source})")
        if r.skipped:
            bits.append(f"Left out ({len(r.skipped)}): " + "  •  ".join(t for t, _ in r.skipped[:4]) +
                        ("  …" if len(r.skipped) > 4 else "") + "   [never heard in the audio]")
        if r.off_script:
            bits.append(f"Spoken but not in script ({len(r.off_script)}): " + "  •  ".join(
                f"{core.short_tc(a)} \"{t[:40]}\"" for a, _b, t in r.off_script[:3]))
        self.extra.config(text="\n".join(bits))
        for b in (self.btn_rep, self.btn_srt, self.btn_breaks, self.btn_prompt):
            b.config(state="normal")
        if r.words_json_path:
            bits.append(f"Word timings saved: {os.path.basename(r.words_json_path)}, "
                        f"{os.path.basename(r.words_srt_path)}")
            self.extra.config(text="\n".join(bits))

    def _result_entry(self):
        e = self._selected() or next((x for x in self.entries.values() if x["result"]), None)
        return e if e and e["result"] else None

    def _script_raw(self, job):
        if job.script_text and job.script_text.strip():
            return job.script_text
        return core.read_script_file(job.script_path)

    def copy_prompt(self):
        """Put a ready-made prompt + this clip's script on the clipboard for any AI tool.
        The app itself never calls an AI service and needs no API key."""
        e = self._result_entry()
        if not e:
            return
        s = self.current_settings()
        try:
            lines = core.parse_script(self._script_raw(e["job"]), s)
        except (OSError, core.SyncError) as ex:
            messagebox.showerror("Couldn't read the script", str(ex))
            return
        self.clipboard_clear()
        self.clipboard_append(core.llm_prompt(lines, s))
        messagebox.showinfo("Prompt copied", (
            "A prompt with this clip's script is on the clipboard.\n\n"
            "1. Paste it into the AI tool you already use.\n"
            "2. Copy its answer (the script with new line breaks).\n"
            "3. Click 'Apply line breaks…' and paste it there.\n\n"
            f"{core.APP_NAME} checks that no words were changed and re-times it from the saved transcript."))

    def apply_line_breaks(self):
        e = self._result_entry()
        if not e or self._busy():
            return
        r = e["result"]
        initial = e["job"].line_breaks or "\n".join(r.layout)
        dlg = LineBreaksDialog(self, f"Line breaks for {e['job'].label()}", initial, (
            "One subtitle per line. Move the line breaks here, or paste the script re-cut by an AI tool. "
            "Only the breaks may change: every word and punctuation mark must stay as written. "
            "Leave it empty to go back to automatic cuts."))
        self.wait_window(dlg)
        if dlg.result is None:
            return
        s = self.current_settings()
        if dlg.result:
            try:
                core.check_line_breaks(self._script_raw(e["job"]), dlg.result, s)
            except (OSError, core.SyncError) as ex:
                messagebox.showerror("Line breaks not applied", str(ex))
                return
        e["job"].line_breaks = dlg.result or None
        self._run([e], s)

    def open_report(self):
        e = self._result_entry()
        if e:
            open_path(e["result"].report_path)

    def open_srt(self):
        e = self._result_entry()
        if e:
            reveal(e["result"].srt_path)

    def _on_close(self):
        self._save_settings()
        self.cancel.set()
        self.destroy()


def _install_crash_logging():
    """Uncaught errors anywhere end up in the log instead of a console nobody sees (pythonw)."""
    def hook(exc, val, tb):
        log.critical("uncaught error", exc_info=(exc, val, tb))
    sys.excepthook = hook

    def thread_hook(args):
        if args.exc_type is not SystemExit:
            log.error("uncaught error in a background thread (%s)",
                      getattr(args.thread, "name", "?"), exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
    threading.excepthook = thread_hook


def main():
    core.setup_logging()
    _install_crash_logging()
    if sys.platform.startswith("win"):          # crisp text on high-DPI screens
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            log.debug("DPI awareness not available", exc_info=True)
    log.info("app start: %s", "; ".join(f"{k}={v}" for k, v in core.system_info().items()))
    app = App()
    log.info("window: %s, display scaling %.0f%%", app.geometry().split("+")[0],
             float(app.tk.call("tk", "scaling")) / (96 / 72) * 100)
    try:
        app.mainloop()
    finally:
        log.info("app closed")
        logging.shutdown()


if __name__ == "__main__":
    main()
