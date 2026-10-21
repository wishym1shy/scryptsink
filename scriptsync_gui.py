"""
Script Sync - desktop app (no command line needed)
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
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import scriptsync_core as core

HERE = os.path.dirname(os.path.abspath(__file__))

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
ACCENT = "#d9822b"
BG = "#f6f5f2"
TAGS = {"ok": "#e6f4ea", "check": "#fff3d1", "bad": "#fbdada"}


def settings_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "ScriptSync")
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


class PasteDialog(tk.Toplevel):
    def __init__(self, parent, title, initial=""):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.result = None
        self.geometry("620x440")
        ttk.Label(self, text="Paste the writer's script here (one subtitle line per line).",
                  padding=(12, 10, 12, 4)).pack(anchor="w")
        self.text = tk.Text(self, wrap="word", font=("Segoe UI", 11), undo=True)
        self.text.pack(fill="both", expand=True, padx=12)
        self.text.insert("1.0", initial)
        bar = ttk.Frame(self, padding=12)
        bar.pack(fill="x")
        ttk.Button(bar, text="Use this script", style="Accent.TButton", command=self.ok).pack(side="right")
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.text.focus_set()
        self.grab_set()

    def ok(self):
        self.result = self.text.get("1.0", "end").strip()
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{core.APP_NAME}")
        self.geometry("1120x840")
        self.minsize(940, 700)
        self.configure(bg=BG)
        self.entries = {}          # iid -> dict(job, result, status)
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self._build_style()
        self._build_ui()
        self._load_settings()
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ style
    def _build_style(self):
        st = ttk.Style(self)
        for theme in ("vista", "clam"):
            if theme in st.theme_names():
                st.theme_use(theme)
                break
        st.configure(".", background=BG)
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG)
        st.configure("TLabelframe", background=BG)
        st.configure("TLabelframe.Label", background=BG, font=("Segoe UI", 10, "bold"))
        st.configure("TCheckbutton", background=BG)
        st.configure("Title.TLabel", font=("Segoe UI", 17, "bold"))
        st.configure("Sub.TLabel", foreground="#666666")
        st.configure("Big.TLabel", font=("Segoe UI", 11, "bold"))
        st.configure("Accent.TButton", font=("Segoe UI", 11, "bold"), padding=(18, 8))
        st.map("Accent.TButton", foreground=[("disabled", "#999999")])
        st.configure("Treeview", rowheight=26, font=("Segoe UI", 10))
        st.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        st.configure("Horizontal.TProgressbar", thickness=14, background=ACCENT, troughcolor="#e3e0d8")

    # ------------------------------------------------------------ layout
    def _build_ui(self):
        head = ttk.Frame(self, padding=(16, 12, 16, 6))
        head.pack(fill="x")
        t = ttk.Frame(head)
        t.pack(side="left")
        ttk.Label(t, text="Script Sync", style="Title.TLabel").pack(anchor="w")
        ttk.Label(t, text="Writer's script + clip  →  timed subtitle file (.srt)",
                  style="Sub.TLabel").pack(anchor="w")
        ttk.Label(head, text=f"by {core.APP_AUTHOR}", style="Sub.TLabel").pack(side="right", anchor="s")

        # ---- queue
        qf = ttk.LabelFrame(self, text=" 1.  Clips and scripts ", padding=10)
        qf.pack(fill="x", padx=16, pady=(6, 6))
        bar = ttk.Frame(qf)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="+ Add clips…", command=self.add_clips).pack(side="left")
        ttk.Button(bar, text="+ Add a folder…", command=self.add_folder).pack(side="left", padx=6)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(bar, text="Choose script file…", command=self.set_script).pack(side="left")
        ttk.Button(bar, text="Paste script…", command=self.paste_script).pack(side="left", padx=6)
        ttk.Button(bar, text="Remove", command=self.remove_selected).pack(side="right")
        ttk.Button(bar, text="Clear all", command=self.clear_all).pack(side="right", padx=6)

        cols = ("clip", "script", "status", "match")
        self.tree = ttk.Treeview(qf, columns=cols, show="headings", height=4, selectmode="browse")
        for c, txt, w, anc in (("clip", "Clip", 300, "w"), ("script", "Script", 260, "w"),
                               ("status", "Status", 330, "w"), ("match", "Heard", 90, "center")):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor=anc, stretch=(c in ("clip", "status")))
        self.tree.pack(fill="x")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_selected())
        self.tree.bind("<Double-1>", lambda e: self.set_script())
        self.hint = ttk.Label(qf, style="Sub.TLabel", text=(
            "Tip: put the script next to the clip with the same name (clip.mp4 + clip.docx / .txt / .srt) "
            "and 'Add a folder' will pair them for you."))
        self.hint.pack(anchor="w", pady=(6, 0))
        for tag, color in (("missing", "#fbdada"), ("ok", "#e6f4ea"), ("review", "#fff3d1"),
                           ("error", "#fbdada")):
            self.tree.tag_configure(tag, background=color)

        # ---- settings
        sf = ttk.LabelFrame(self, text=" 2.  Settings ", padding=10)
        sf.pack(fill="x", padx=16, pady=6)
        r1 = ttk.Frame(sf)
        r1.pack(fill="x")
        ttk.Label(r1, text="Listening quality").grid(row=0, column=0, sticky="w")
        self.var_model = tk.StringVar(value=list(MODELS)[1])
        ttk.Combobox(r1, textvariable=self.var_model, values=list(MODELS), state="readonly",
                     width=32).grid(row=0, column=1, padx=(8, 22), sticky="w")
        ttk.Label(r1, text="Language").grid(row=0, column=2, sticky="w")
        self.var_lang = tk.StringVar(value="Auto-detect")
        ttk.Combobox(r1, textvariable=self.var_lang, values=list(LANGS), state="readonly",
                     width=18).grid(row=0, column=3, padx=(8, 22), sticky="w")
        ttk.Label(r1, text="Max characters per subtitle").grid(row=0, column=4, sticky="w")
        self.var_maxchars = tk.IntVar(value=40)
        ttk.Spinbox(r1, from_=12, to=120, textvariable=self.var_maxchars, width=5).grid(
            row=0, column=5, padx=8, sticky="w")

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
        self.v_mincue = tk.DoubleVar(value=0.8)
        self.v_bridge = tk.DoubleVar(value=0.4)
        self.v_maxsec = tk.DoubleVar(value=5.0)
        opts = [
            (self.v_brackets, "Ignore [bracketed notes] in the script"),
            (self.v_labels, "Script has speaker labels like  'Sam:'  (remove them)"),
            (self.v_lines, "Keep the writer's line breaks as subtitle breaks"),
            (self.v_zero, "Premiere fix: never start the first subtitle at 00:00:00,000"),
            (self.v_prime, "Tell the listener the names/brands in the script (helps spelling)"),
            (self.v_unheard, "Also include lines that were never heard (timing is a guess)"),
            (self.v_cache, "Re-use the saved transcript if the clip hasn't changed (faster)"),
        ]
        for i, (v, txt) in enumerate(opts):
            ttk.Checkbutton(self.adv, text=txt, variable=v).grid(row=i // 2, column=i % 2, sticky="w",
                                                                 padx=(0, 24), pady=1)
        nums = ttk.Frame(self.adv)
        nums.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        for lbl, var, lo, hi, inc in (("Shortest subtitle (sec)", self.v_mincue, 0.2, 3, 0.1),
                                      ("Hold through pauses up to (sec)", self.v_bridge, 0, 2, 0.1),
                                      ("Longest subtitle (sec)", self.v_maxsec, 2, 15, 0.5)):
            ttk.Label(nums, text=lbl).pack(side="left")
            ttk.Spinbox(nums, from_=lo, to=hi, increment=inc, textvariable=var, width=5).pack(
                side="left", padx=(6, 20))

        # ---- run
        rf = ttk.Frame(self, padding=(16, 8, 16, 2))
        rf.pack(fill="x")
        self.btn_run = ttk.Button(rf, text="▶  Sync", style="Accent.TButton", command=self.start)
        self.btn_run.pack(side="left")
        self.btn_cancel = ttk.Button(rf, text="Stop", command=self.stop, state="disabled")
        self.btn_cancel.pack(side="left", padx=8)
        pf = ttk.Frame(rf)
        pf.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.progress = ttk.Progressbar(pf, maximum=1000)
        self.progress.pack(fill="x")
        self.status = ttk.Label(pf, text="Add a clip and its script to begin.", style="Sub.TLabel")
        self.status.pack(anchor="w")

        # ---- review
        vf = ttk.LabelFrame(self, text=" 3.  Review ", padding=10)
        vf.pack(fill="both", expand=True, padx=16, pady=(8, 14))
        top = ttk.Frame(vf)
        top.pack(fill="x", pady=(0, 6))
        self.summary = ttk.Label(top, text="Select a finished clip to see its subtitles.", style="Big.TLabel")
        self.summary.pack(side="left")
        self.btn_rep = ttk.Button(top, text="Open review sheet", command=self.open_report, state="disabled")
        self.btn_rep.pack(side="right")
        self.btn_srt = ttk.Button(top, text="Show .srt in folder", command=self.open_srt, state="disabled")
        self.btn_srt.pack(side="right", padx=6)

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
        for lvl, color in TAGS.items():
            self.ctree.tag_configure(lvl, background=color)

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
        iid = self.tree.insert("", "end", values=("", "", "", ""))
        self.entries[iid] = {"iid": iid, "job": job, "result": None, "status": ""}
        self._refresh_row(self.entries[iid])

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
        st = e["status"] or ("Ready" if (job.script_text or job.script_path) else "Needs a script")
        tag = ""
        if not (job.script_text or job.script_path):
            tag = "missing"
        elif st.startswith("Done"):
            tag = "review" if "review" in st else "ok"
        elif st.startswith("Error") or st.startswith("Stopped"):
            tag = "error"
        vals = (job.label(), sc, st, match if match is not None else self.tree.set(e["iid"], "match"))
        self.tree.item(e["iid"], values=vals, tags=(tag,) if tag else ())

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
        missing = sum(1 for e in self.entries.values()
                      if not (e["job"].script_path or e["job"].script_text))
        if missing:
            self.status.config(text=f"{missing} clip(s) need a script: select the row, then "
                                    f"'Choose script file…' or 'Paste script…'.")
        else:
            self.status.config(text="Ready. Press Sync.")

    def _selected(self):
        sel = self.tree.selection()
        return self.entries.get(sel[0]) if sel else None

    def set_script(self):
        e = self._selected()
        if not e:
            messagebox.showinfo("Pick a clip", "Select a clip in the list first.")
            return
        p = filedialog.askopenfilename(
            title="Choose the writer's script",
            filetypes=[("Scripts", "*.docx *.txt *.md *.srt"), ("All files", "*.*")])
        if p:
            e["job"].script_path, e["job"].script_text = p, None
            e["result"] = None
            self._refresh_row(e, status="")
            self._after_add()

    def paste_script(self):
        e = self._selected()
        if not e:
            messagebox.showinfo("Pick a clip", "Select a clip in the list first.")
            return
        dlg = PasteDialog(self, f"Script for {e['job'].label()}", e["job"].script_text or "")
        self.wait_window(dlg)
        if dlg.result:
            e["job"].script_text, e["job"].script_path = dlg.result, None
            e["result"] = None
            self._refresh_row(e, status="")
            self._after_add()

    def remove_selected(self):
        e = self._selected()
        if e and not self._busy():
            self.tree.delete(e["iid"])
            del self.entries[e["iid"]]
            self.clear_review()

    def clear_all(self):
        if self._busy():
            return
        for iid in list(self.entries):
            self.tree.delete(iid)
        self.entries.clear()
        self.clear_review()
        self.status.config(text="Add a clip and its script to begin.")

    def choose_out(self):
        d = filedialog.askdirectory(title="Where should the .srt files go?")
        if d:
            self.var_out.set(d)

    # ------------------------------------------------------------ settings
    def current_settings(self) -> core.Settings:
        try:
            maxc = max(10, int(self.var_maxchars.get()))
        except (tk.TclError, ValueError):
            maxc = 40

        def num(v, d):
            try:
                return float(v.get())
            except (tk.TclError, ValueError):
                return d
        return core.Settings(
            model=MODELS.get(self.var_model.get(), "small"),
            language=LANGS.get(self.var_lang.get(), "auto"),
            max_chars=maxc,
            max_cue_seconds=num(self.v_maxsec, 5.0),
            min_cue_seconds=num(self.v_mincue, 0.8),
            bridge_gap=num(self.v_bridge, 0.4),
            ignore_brackets=self.v_brackets.get(),
            strip_speaker_labels=self.v_labels.get(),
            keep_script_lines=self.v_lines.get(),
            premiere_zero_fix=self.v_zero.get(),
            prime_vocab=self.v_prime.get(),
            include_unheard=self.v_unheard.get(),
            use_cache=self.v_cache.get(),
        )

    def _save_settings(self):
        data = {"model": self.var_model.get(), "lang": self.var_lang.get(), "maxc": self.var_maxchars.get(),
                "out": self.var_out.get(), "brackets": self.v_brackets.get(), "labels": self.v_labels.get(),
                "lines": self.v_lines.get(), "zero": self.v_zero.get(), "prime": self.v_prime.get(),
                "unheard": self.v_unheard.get(), "cache": self.v_cache.get(),
                "mincue": self.v_mincue.get(), "bridge": self.v_bridge.get(), "maxsec": self.v_maxsec.get()}
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
            for k, v in (("brackets", self.v_brackets), ("labels", self.v_labels), ("lines", self.v_lines),
                         ("zero", self.v_zero), ("prime", self.v_prime), ("unheard", self.v_unheard),
                         ("cache", self.v_cache)):
                if k in d:
                    v.set(bool(d[k]))
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
        s = self.current_settings()
        out = self.var_out.get().strip() or None
        for e in todo:
            e["job"].out_dir = out
            e["result"] = None
            self._refresh_row(e, status="Waiting…", match="")
        self._save_settings()
        self.cancel.clear()
        self.btn_run.config(state="disabled")
        self.btn_cancel.config(state="normal")
        self.worker = threading.Thread(target=self._work, args=(todo, s), daemon=True)
        self.worker.start()

    def stop(self):
        self.cancel.set()
        self.status.config(text="Stopping after the current step…")

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
            except Exception as ex:  # unexpected
                traceback.print_exc()
                self.q.put(("row", e["iid"], f"Error: {type(ex).__name__}: {ex}", None))
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
                    self.status.config(text=f"{e['job'].label() if e else ''}  —  {msg}")
                elif kind == "row":
                    _, iid, st, match = m
                    e = self.entries.get(iid)
                    if e:
                        self._refresh_row(e, status=st, match=match or "")
                        if st.startswith("Error"):
                            self.summary.config(text=st)
                elif kind == "done":
                    _, iid, res = m
                    e = self.entries.get(iid)
                    if e:
                        e["result"] = res
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
                    self.status.config(text=f"Finished: {done} of {m[1]} clip(s) synced."
                                       if not self.cancel.is_set() else "Stopped.")
        except queue.Empty:
            pass
        self.after(100, self._poll)

    # ------------------------------------------------------------ review
    def clear_review(self):
        self.ctree.delete(*self.ctree.get_children())
        self.summary.config(text="Select a finished clip to see its subtitles.")
        self.extra.config(text="")
        self.btn_rep.config(state="disabled")
        self.btn_srt.config(state="disabled")

    def show_selected(self):
        e = self._selected()
        if not e:
            return
        if e["result"]:
            self.show_result(e)
        else:
            self.clear_review()
            if e["status"].startswith("Error"):
                self.summary.config(text=e["status"])

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
        if r.skipped:
            bits.append(f"Left out ({len(r.skipped)}): " + "  •  ".join(t for t, _ in r.skipped[:4]) +
                        ("  …" if len(r.skipped) > 4 else "") + "   [never heard in the audio]")
        if r.off_script:
            bits.append(f"Spoken but not in script ({len(r.off_script)}): " + "  •  ".join(
                f"{core.short_tc(a)} \"{t[:40]}\"" for a, _b, t in r.off_script[:3]))
        self.extra.config(text="\n".join(bits))
        self.btn_rep.config(state="normal")
        self.btn_srt.config(state="normal")

    def open_report(self):
        e = self._selected() or next((x for x in self.entries.values() if x["result"]), None)
        if e and e["result"]:
            open_path(e["result"].report_path)

    def open_srt(self):
        e = self._selected() or next((x for x in self.entries.values() if x["result"]), None)
        if e and e["result"]:
            reveal(e["result"].srt_path)

    def _on_close(self):
        self._save_settings()
        self.cancel.set()
        self.destroy()


def main():
    if sys.platform.startswith("win"):          # crisp text on high-DPI screens
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    App().mainloop()


if __name__ == "__main__":
    main()
