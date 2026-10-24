"""
Script Sync - core engine
=========================
By wishym1shy  (https://github.com/wishym1shy)

Takes a clip + the writer's script and produces an SRT whose text is the
writer's script (exactly as written) and whose timing comes from the audio.

How it works
------------
1. Listen: a speech model (faster-whisper) transcribes the clip with a
   timestamp for every spoken word. Its spelling does not matter.
2. Match: the script words are aligned to the spoken words (global sequence
   alignment, tolerant of mis-hearings, ad-libs and skipped words).
3. Time: every script word inherits the timestamp of the spoken word it was
   matched to. Words that were never heard get an interpolated time and are
   flagged.
4. Cue: the script's own line breaks become subtitle cues (split further only
   if too long). Doubtful cues are reported in a review file.

Only the standard library is needed for steps 2-4, so the logic can be tested
without any speech model installed.
"""
from __future__ import annotations

import difflib
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Optional

APP_NAME = "Script Sync"
APP_AUTHOR = "wishym1shy"
APP_VERSION = "0.1.0"

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mxf", ".mp3", ".wav", ".m4a"}
SCRIPT_EXTS = [".docx", ".txt", ".md", ".srt"]  # order = preference when auto-matching


# --------------------------------------------------------------------------
# Data types
# --------------------------------------------------------------------------
@dataclass
class AsrWord:
    text: str
    start: float
    end: float
    prob: float = 1.0


@dataclass
class Settings:
    # speech model
    model: str = "small"
    language: str = "auto"          # "auto" or a Whisper language code (en, tl, es ...)
    device: str = "auto"            # auto / cpu / cuda
    prime_vocab: bool = True        # hint names/brands from the script to the model
    use_cache: bool = True          # reuse a clip's transcript if nothing changed
    # script reading
    ignore_brackets: bool = True    # drop [stage directions]
    strip_speaker_labels: bool = False   # drop "Name:" at line start
    keep_script_lines: bool = True  # one cue per script line (split only if too long)
    # cue shape
    max_chars: int = 40             # max characters in one cue
    max_cue_seconds: float = 5.0    # split cues that stay on screen longer than this
    min_cue_seconds: float = 0.8    # never flash a cue shorter than this (if room)
    bridge_gap: float = 0.4         # keep a cue up through pauses shorter than this
    tail_hold: float = 0.12         # linger after the last word
    lead_in: float = 0.0            # show cue this much earlier than the first word
    min_gap: float = 0.04           # clear space between consecutive cues
    premiere_zero_fix: bool = True  # Premiere quirk: it drops a cue that starts at 00:00:00,000
    include_unheard: bool = False   # keep cues for text that was never heard (timing = guess)


@dataclass
class Wd:
    """One word of the script."""
    text: str
    toks: list
    line: int
    start: Optional[float] = None
    end: Optional[float] = None
    conf: float = 0.0
    anchored: bool = False
    heard_as: str = ""
    tok_kinds: list = field(default_factory=list)


@dataclass
class Cue:
    index: int
    start: float
    end: float
    text: str
    conf: float
    level: str                      # ok / check / bad
    notes: list
    line_no: int
    words: int = 0


@dataclass
class Job:
    video: str
    script_path: Optional[str] = None
    script_text: Optional[str] = None
    out_dir: Optional[str] = None

    def label(self):
        return os.path.basename(self.video)


@dataclass
class SyncResult:
    cues: list
    skipped: list                   # (line text, why)
    off_script: list                # (start, end, text)
    warnings: list
    match_pct: float
    n_ok: int
    n_check: int
    n_bad: int
    duration: float
    srt_path: str = ""
    report_path: str = ""
    srt_text: str = ""
    report_text: str = ""
    error: str = ""


class Cancelled(Exception):
    pass


class SyncError(Exception):
    """A problem the user can fix (message is shown as-is)."""


# --------------------------------------------------------------------------
# Script reading
# --------------------------------------------------------------------------
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_SRT_TIME = re.compile(r"\d{1,2}:\d\d:\d\d[,.]\d{1,3}\s*-->\s*\d{1,2}:\d\d:\d\d[,.]\d{1,3}")


def _read_text_file(path: str) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _read_docx(path: str) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as e:
        raise SyncError(f"Couldn't open the Word file '{os.path.basename(path)}' ({e}).")
    root = ET.fromstring(xml)
    lines = []
    for p in root.iter(_W + "p"):
        buf = []
        for el in p.iter():
            if el.tag == _W + "t" and el.text:
                buf.append(el.text)
            elif el.tag == _W + "tab":
                buf.append(" ")
            elif el.tag in (_W + "br", _W + "cr"):
                buf.append("\n")
        lines.append("".join(buf))
    return "\n".join(lines)


def _srt_to_lines(text: str) -> str:
    """Use the text of each SRT cue as one script line; ignore its timing."""
    out = []
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n")):
        rows = [r for r in block.strip().split("\n") if r.strip()]
        if not rows:
            continue
        if rows and re.fullmatch(r"\d+", rows[0].strip()):
            rows = rows[1:]
        if rows and _SRT_TIME.search(rows[0]):
            rows = rows[1:]
        if rows:
            out.append(" ".join(r.strip() for r in rows))
    return "\n".join(out)


def read_script_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        text = _read_docx(path)
    else:
        text = _read_text_file(path)
    if ext == ".srt" or _SRT_TIME.search(text):
        text = _srt_to_lines(text)
    return text


_ZW = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
_LABEL = re.compile(r"^\s*[A-Z][\w.'\-]*(?:\s[A-Z][\w.'\-]*)?\s*:\s+")


def parse_script(text: str, s: Settings) -> list:
    """Raw script text -> list of cleaned lines (strings)."""
    text = text.translate(_ZW).replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")
    if _SRT_TIME.search(text):
        text = _srt_to_lines(text)
    lines = []
    for ln in text.split("\n"):
        if s.ignore_brackets:
            ln = re.sub(r"\[[^\]]*\]", " ", ln)
        if s.strip_speaker_labels:
            ln = _LABEL.sub("", ln)
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln and re.search(r"\w", ln):
            lines.append(ln)
    if not s.keep_script_lines and lines:
        lines = [" ".join(lines)]
    return lines


# --------------------------------------------------------------------------
# Tokenising for matching (spelling-insensitive; numbers spoken out)
# --------------------------------------------------------------------------
_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
         "fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_SEP = re.compile(r"[\u2014\u2013/\u2026]+|\.{2,}")
_PIECE = re.compile(r"\d+(?:\.\d+)?|[^\W\d_]+|[$%]")
FILLERS = {"um", "uh", "uhm", "umm", "hmm", "mm", "mmm", "ah", "er", "erm", "huh"}


def _int_words(n: int) -> list:
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        return [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    if n < 1000:
        return [_ONES[n // 100], "hundred"] + (_int_words(n % 100) if n % 100 else [])
    for div, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (10 ** 3, "thousand")):
        if n >= div:
            return _int_words(n // div) + [name] + (_int_words(n % div) if n % div else [])
    return [str(n)]


def _number_words(num: str) -> list:
    if "." in num:
        a, b = num.split(".", 1)
        return _number_words(a) + ["point"] + [_ONES[int(d)] for d in b]
    n = int(num)
    return _int_words(n) if n < 10 ** 15 else [num]


def tokens_for(word: str) -> list:
    w = word.lower().replace("\u2019", "'").replace("\u2018", "'")
    w = re.sub(r"(?<=\d),(?=\d)", "", w)
    w = re.sub(r"(?<=\d)-(?=\d)", "/", w)
    out = []
    for part in (p for p in _SEP.split(w) if p):
        part = part.replace("'", "").replace("-", "")
        pieces = _PIECE.findall(part)
        i = 0
        while i < len(pieces):
            p = pieces[i]
            if p[0].isdigit():
                out.extend(_number_words(p))
                if i > 0 and pieces[i - 1] == "$":
                    out.append("dollars")
                if i + 1 < len(pieces) and pieces[i + 1] == "%":
                    out.append("percent")
                    i += 1
                elif i + 1 < len(pieces) and pieces[i + 1] == "k":
                    out.append("thousand")
                    i += 1
            elif p in "$%":
                pass
            else:
                out.append(p)
            i += 1
    return out


# --------------------------------------------------------------------------
# Alignment
# --------------------------------------------------------------------------
_ratio_cache: dict = {}


def _ratio(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if abs(len(a) - len(b)) > max(3, 0.5 * max(len(a), len(b))):
        return 0.0
    key = (a, b)
    r = _ratio_cache.get(key)
    if r is None:
        r = difflib.SequenceMatcher(None, a, b).ratio()
        if len(_ratio_cache) > 200_000:
            _ratio_cache.clear()
        _ratio_cache[key] = r
    return r


def _pair(a: str, b: str):
    """-> (score, kind) for aligning script token a with spoken token b."""
    if a == b:
        return 3.0, "exact"
    r = _ratio(a, b)
    if r >= 0.75:
        return 2.0 * r, "fuzzy"        # 1.5 .. 2.0
    if r >= 0.5:
        return -0.5, "sub"             # looks a bit like it: treat as a mis-hearing
    return -2.5, "sub"                 # unrelated: worse than two gaps, so never paired by choice


_GAP = -1.0
_MAX_CELLS = 4_000_000


def _nw(S, A, i0, i1, j0, j1, match, kind):
    n, m = i1 - i0, j1 - j0
    if n == 0 or m == 0 or n * m > _MAX_CELLS:
        return
    H = [[0.0] * (m + 1) for _ in range(n + 1)]
    P = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        H[i][0] = i * _GAP
        P[i][0] = 1
    for j in range(1, m + 1):
        H[0][j] = j * _GAP
        P[0][j] = 2
    for i in range(1, n + 1):
        si = S[i0 + i - 1]
        Hi, Hp, Pi = H[i], H[i - 1], P[i]
        for j in range(1, m + 1):
            sc, _k = _pair(si, A[j0 + j - 1])
            d = Hp[j - 1] + sc
            u = Hp[j] + _GAP
            l = Hi[j - 1] + _GAP
            if d >= u and d >= l:
                Hi[j], Pi[j] = d, 0
            elif u >= l:
                Hi[j], Pi[j] = u, 1
            else:
                Hi[j], Pi[j] = l, 2
    i, j = n, m
    while i > 0 or j > 0:
        mv = P[i][j]
        if i > 0 and j > 0 and mv == 0:
            _sc, k = _pair(S[i0 + i - 1], A[j0 + j - 1])
            match[i0 + i - 1] = j0 + j - 1
            kind[i0 + i - 1] = k
            i -= 1
            j -= 1
        elif i > 0 and (mv == 1 or j == 0):
            i -= 1
        else:
            j -= 1


def align_tokens(S: list, A: list):
    """Global alignment of script tokens S to spoken tokens A.
    Returns (match, kind): match[i] = index into A or None."""
    match = [None] * len(S)
    kind = [None] * len(S)
    if not S or not A:
        return match, kind
    blocks = []
    if len(S) > 12 and len(A) > 12:
        sm = difflib.SequenceMatcher(None, S, A, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size >= 3]
    pi = pj = 0
    for b in blocks:
        _nw(S, A, pi, b.a, pj, b.b, match, kind)
        for k in range(b.size):
            match[b.a + k] = b.b + k
            kind[b.a + k] = "exact"
        pi, pj = b.a + b.size, b.b + b.size
    _nw(S, A, pi, len(S), pj, len(A), match, kind)
    return match, kind


_KIND_CONF = {"exact": 1.0, "fuzzy": 0.85, "sub": 0.35, None: 0.0}


def _natural_dur(w: Wd) -> float:
    n = sum(len(t) for t in w.toks) or 3
    return min(0.9, max(0.12, 0.10 + 0.06 * n))


def align_script(lines: list, asr: list, audio_duration: float):
    """lines: cleaned script lines. asr: list[AsrWord].
    Returns (words, off_script) where words is list[Wd] with times and confidence."""
    # ---- script words
    words: list = []
    for li, line in enumerate(lines):
        pending_prefix = ""
        line_words: list = []
        for raw in line.split():
            toks = tokens_for(raw)
            if not toks:                       # punctuation-only chunk: glue to neighbour
                if line_words:
                    line_words[-1].text += " " + raw
                else:
                    pending_prefix += raw + " "
                continue
            line_words.append(Wd(text=pending_prefix + raw, toks=toks, line=li))
            pending_prefix = ""
        words.extend(line_words)

    script_set = {t for w in words for t in w.toks}
    S, S_word = [], []
    for wi, w in enumerate(words):
        for t in w.toks:
            S.append(t)
            S_word.append(wi)

    # ---- spoken tokens (with per-token times)
    A, A_start, A_end, A_word = [], [], [], []
    for ai, aw in enumerate(asr):
        toks = tokens_for(aw.text)
        toks = [t for t in toks if t not in FILLERS or t in script_set]
        if not toks:
            continue
        dur = max(aw.end - aw.start, 0.02)
        for k, t in enumerate(toks):
            A.append(t)
            A_start.append(aw.start + dur * k / len(toks))
            A_end.append(aw.start + dur * (k + 1) / len(toks))
            A_word.append(ai)

    match, kind = align_tokens(S, A)

    # ---- per-word timing and confidence
    tok_cursor = 0
    for wi, w in enumerate(words):
        starts, ends, heard, kinds = [], [], [], []
        for _t in w.toks:
            j = match[tok_cursor]
            k = kind[tok_cursor]
            kinds.append(k)
            if j is not None:
                starts.append(A_start[j])
                ends.append(A_end[j])
                heard.append(asr[A_word[j]].text.strip())
            tok_cursor += 1
        w.tok_kinds = kinds
        w.conf = sum(_KIND_CONF[k] for k in kinds) / len(kinds)
        if starts:
            w.anchored = True
            w.start, w.end = min(starts), max(ends)
            seen = []
            for h in heard:
                if h not in seen:
                    seen.append(h)
            w.heard_as = " ".join(seen)

    # ---- interpolate words that were never heard
    n = len(words)
    i = 0
    total = max(audio_duration, 0.0)
    while i < n:
        if words[i].anchored:
            i += 1
            continue
        j = i
        while j < n and not words[j].anchored:
            j += 1
        run = words[i:j]
        t0 = words[i - 1].end if i > 0 else None
        t1 = words[j].start if j < n else None
        dsum = sum(_natural_dur(w) for w in run)
        if t0 is not None and t1 is not None:
            window = max(t1 - t0, 0.0)
            f = window / dsum if window <= 1.5 * dsum else 1.0
            cur = t0
        elif t1 is not None:                       # before the first heard word
            f = 1.0
            cur = max(0.0, t1 - dsum)
            if cur + dsum > t1:
                f = max(t1 / dsum, 0.05)
        elif t0 is not None:                       # after the last heard word
            f = 1.0
            cur = t0
        else:                                      # nothing heard at all
            f = 1.0
            cur = 0.0
        for w in run:
            d = _natural_dur(w) * f
            w.start, w.end = cur, cur + d
            cur += d
        i = j

    # ---- monotonic clean-up
    prev = 0.0
    for w in words:
        w.start = max(w.start, prev)
        if w.end < w.start + 0.02:
            w.end = w.start + 0.02
        prev = w.start

    # ---- spoken-but-not-in-script runs (ad-libs)
    used_asr = {A_word[j] for j in match if j is not None}
    off = []
    run = []
    for ai, aw in enumerate(asr):
        toks = tokens_for(aw.text)
        meaningful = [t for t in toks if t not in FILLERS]
        if ai in used_asr or not meaningful:
            if run and ai in used_asr:
                off.append(run)
                run = []
            continue
        run.append(aw)
    if run:
        off.append(run)
    off_script = []
    for r in off:
        if len(r) >= 4:
            off_script.append((r[0].start, r[-1].end, " ".join(x.text.strip() for x in r)))
    return words, off_script


# --------------------------------------------------------------------------
# Cues
# --------------------------------------------------------------------------
def _split_words(ws: list, s: Settings) -> list:
    """Split one line's words into chunks that fit the cue limits."""
    n = len(ws)
    lens = [len(w.text) for w in ws]

    def chars(i, j):
        return sum(lens[i:j]) + (j - i - 1)

    def secs(i, j):
        return max(w.end for w in ws[i:j]) - ws[i].start

    if chars(0, n) <= s.max_chars and secs(0, n) <= s.max_cue_seconds:
        return [ws]
    k = max(math.ceil(chars(0, n) / s.max_chars), math.ceil(secs(0, n) / s.max_cue_seconds), 2)
    target = chars(0, n) / k
    INF = float("inf")
    best = [INF] * (n + 1)
    back = [0] * (n + 1)
    best[0] = 0.0
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            single = (j - i == 1)
            if not single and (chars(i, j) > s.max_chars or secs(i, j) > s.max_cue_seconds):
                if chars(i, j) > s.max_chars:
                    break
                continue
            if best[i] == INF:
                continue
            c = 1000.0 + 0.1 * (chars(i, j) - target) ** 2
            if re.search(r"[.!?;:,\u2014]['\")\u201d]*$", ws[j - 1].text):
                c -= 30
            if j < n:
                gap = ws[j].start - ws[j - 1].end
                c -= 50 * min(max(gap, 0.0), 1.0)
            if best[i] + c < best[j]:
                best[j] = best[i] + c
                back[j] = i
    out, j = [], n
    while j > 0:
        i = back[j]
        out.append(ws[i:j])
        j = i
    return out[::-1]


def _level(conf: float) -> str:
    return "ok" if conf >= 0.9 else ("check" if conf >= 0.55 else "bad")


def build_cues(words: list, lines: list, s: Settings, audio_duration: float):
    by_line: dict = {}
    for w in words:
        by_line.setdefault(w.line, []).append(w)
    cues, skipped = [], []
    for li in sorted(by_line):
        ws = by_line[li]
        for chunk in _split_words(ws, s):
            if not s.include_unheard and not any(w.anchored for w in chunk):
                skipped.append((" ".join(w.text for w in chunk), "not heard in the audio"))
                continue
            conf = sum(w.conf for w in chunk) / len(chunk)
            notes = []
            missing = [w.text for w in chunk if not w.anchored]
            if missing:
                notes.append("not heard: " + " ".join(missing))
            diff = [f'audio said "{w.heard_as}" for "{w.text}"' for w in chunk
                    if w.anchored and w.conf < 0.85]
            if diff:
                notes.append("; ".join(diff[:4]) + (" ..." if len(diff) > 4 else ""))
            cues.append(Cue(0, min(w.start for w in chunk), max(w.end for w in chunk),
                            " ".join(w.text for w in chunk), conf, _level(conf), notes, li,
                            len(chunk)))
    cues.sort(key=lambda c: c.start)
    _finalize_times(cues, s, audio_duration)
    for i, c in enumerate(cues, 1):
        c.index = i
    return cues, skipped


def _finalize_times(cues: list, s: Settings, duration: float):
    n = len(cues)
    for i, c in enumerate(cues):
        c.start = max(0.0, c.start - s.lead_in)
    for i, c in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < n else None
        end = c.end
        limit = (nxt - s.min_gap) if nxt is not None else float("inf")
        if nxt is not None and nxt - c.end <= s.bridge_gap:
            end = max(end, limit)                         # hold through short pauses
        else:
            end = c.end + s.tail_hold
        if end - c.start < s.min_cue_seconds:
            end = c.start + s.min_cue_seconds
        end = min(end, limit)
        if duration and nxt is None:
            end = min(end, duration)
        if end < c.start + 0.05:
            end = c.start + 0.05
        c.end = end
    if s.premiere_zero_fix and cues and cues[0].start < 0.067:
        cues[0].start = 0.067
        if cues[0].end < cues[0].start + 0.05:
            cues[0].end = cues[0].start + 0.05


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def srt_time(t: float) -> str:
    ms = max(0, int(round(t * 1000)))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    sec, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def short_tc(t: float) -> str:
    ms = max(0, int(round(t * 1000)))
    m, ms = divmod(ms, 60_000)
    sec, ms = divmod(ms, 1000)
    return f"{m:02d}:{sec:02d}.{ms:03d}"


def make_srt(cues: list) -> str:
    parts = []
    for c in cues:
        parts.append(f"{c.index}\r\n{srt_time(c.start)} --> {srt_time(c.end)}\r\n{c.text}\r\n")
    return "\r\n".join(parts)


def make_report(job_label: str, script_label: str, res: SyncResult, s: Settings,
                n_lines: int, n_words: int, lang: str) -> str:
    L = []
    L.append(f"{APP_NAME.upper()} - REVIEW REPORT")
    L.append("=" * 60)
    L.append(f"Clip:    {job_label}")
    L.append(f"Script:  {script_label}  ({n_lines} lines, {n_words} words)")
    L.append(f"Made:    {time.strftime('%Y-%m-%d %H:%M')}  |  model {s.model}  |  language {lang}")
    L.append(f"Heard:   {res.match_pct:.0f}% of the script's words were found in the audio")
    L.append(f"Cues:    {len(res.cues)} total  =  {res.n_ok} OK, {res.n_check} CHECK, {res.n_bad} BAD")
    L.append("")
    for w in res.warnings:
        L.append(f"!! {w}")
    if res.warnings:
        L.append("")
    flagged = [c for c in res.cues if c.level != "ok"]
    L.append("NEEDS YOUR EYES")
    L.append("-" * 60)
    if not flagged:
        L.append("Nothing flagged. Still spot-check sync against the audio.")
    for c in sorted(flagged, key=lambda c: (c.level != "bad", c.start)):
        L.append(f"[{c.level.upper()}] #{c.index}  {short_tc(c.start)} - {short_tc(c.end)}")
        L.append(f"    \"{c.text}\"")
        for n in c.notes:
            L.append(f"    - {n}")
    L.append("")
    L.append("NOT IN THE SRT (script text that was never heard)")
    L.append("-" * 60)
    if not res.skipped:
        L.append("None.")
    for text, why in res.skipped:
        L.append(f"- \"{text}\"  ({why})")
    L.append("")
    L.append("SPOKEN BUT NOT IN THE SCRIPT (ad-libs, extra takes, intro chatter)")
    L.append("-" * 60)
    if not res.off_script:
        L.append("None.")
    for a, b, t in res.off_script:
        L.append(f"{short_tc(a)} - {short_tc(b)}  \"{t}\"")
    L.append("")
    L.append("Reminder: the SRT supplies text and timing only. Style it in your editor.")
    L.append("Made with Script Sync by wishym1shy")
    return "\r\n".join(L) + "\r\n"


# --------------------------------------------------------------------------
# Speech recognition
# --------------------------------------------------------------------------
def cache_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".cache")
    d = os.path.join(base, "ScriptSync", "cache")
    os.makedirs(d, exist_ok=True)
    return d


def find_ffmpeg() -> Optional[str]:
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def vocab_hint(lines: list, limit: int = 40) -> str:
    """Names / brands / numbers from the script to prime the speech model's spelling."""
    seen, out = set(), []
    for line in lines:
        toks = line.split()
        for i, t in enumerate(toks):
            core = re.sub(r"^\W+|\W+$", "", t)
            if len(core) < 3 or core.lower() in seen:
                continue
            starts_sentence = i == 0 or re.search(r"[.!?]['\")]*$", toks[i - 1])
            if (core[0].isupper() and not starts_sentence) or any(ch.isdigit() for ch in core) \
                    or (core.isupper() and len(core) > 2):
                seen.add(core.lower())
                out.append(core)
                if len(out) >= limit:
                    return ", ".join(out)
    return ", ".join(out)


_model_cache: dict = {}


def _load_whisper(model: str, device: str, progress):
    key = (model, device)
    if key in _model_cache:
        return _model_cache[key]
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise SyncError("The speech engine (faster-whisper) isn't installed. "
                        "Run the launcher again or: pip install faster-whisper")
    progress(0.02, f"Loading speech model '{model}' (first time downloads it - this can take a few minutes)")
    ctype = "int8" if device == "cpu" else "float16"
    m = WhisperModel(model, device=device, compute_type=ctype)
    _model_cache[key] = m
    return m


def decode_audio(path: str):
    """Clip -> mono 16 kHz float32 numpy array, using ffmpeg.

    We do this ourselves instead of letting faster-whisper open the file: its built-in
    loader goes through PyAV and calls av.open(..., metadata_errors=...), which crashes
    ("open() got an unexpected keyword argument 'metadata_errors'") when the installed
    PyAV is older than that faster-whisper expects. A numpy array skips that code entirely.
    """
    ff = find_ffmpeg()
    if not ff:
        raise SyncError("ffmpeg wasn't found. Re-run the launcher so it can install it "
                        "(pip install imageio-ffmpeg), or install ffmpeg yourself.")
    try:
        import numpy as np
    except ImportError:
        raise SyncError("numpy isn't installed. Re-run the launcher to finish setup.")
    kw = {"creationflags": 0x08000000} if os.name == "nt" else {}   # no console flash on Windows
    p = subprocess.run([ff, "-v", "error", "-nostdin", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
                        "-f", "f32le", "-"], capture_output=True, **kw)
    if p.returncode != 0 or not p.stdout:
        why = (p.stderr.decode("utf-8", "replace").strip().splitlines() or ["no audio stream?"])[-1]
        raise SyncError(f"Couldn't read the audio from '{os.path.basename(path)}': {why}")
    return np.frombuffer(p.stdout, dtype=np.float32)


def _auto_device() -> str:
    """Use an NVIDIA GPU when CTranslate2 can see one, otherwise the CPU."""
    try:
        import ctranslate2
        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except Exception:
        return "cpu"


def _whisper_transcribe(path, s: Settings, hint: str, progress, cancel):
    progress(0.01, "Reading the audio")
    audio = decode_audio(path)

    def run(device):
        model = _load_whisper(s.model, device, progress)
        progress(0.10, "Listening to the clip")
        segs, info = model.transcribe(
            audio, language=None if s.language == "auto" else s.language,
            word_timestamps=True, beam_size=5, condition_on_previous_text=False,
            initial_prompt=(f"Names and terms: {hint}." if hint else None))
        words = []
        dur = len(audio) / 16000.0
        for seg in segs:
            if cancel and cancel.is_set():
                raise Cancelled()
            for w in (seg.words or []):
                words.append(AsrWord(w.word.strip(), float(w.start), float(w.end),
                                     float(getattr(w, "probability", 1.0) or 1.0)))
            if dur:
                progress(0.10 + 0.75 * min(seg.end / dur, 1.0), "Listening to the clip")
        return words, dur, info.language

    dev = s.device if s.device != "auto" else _auto_device()
    try:
        return run(dev)
    except (Cancelled, SyncError):
        raise
    except Exception as e:
        if dev == "cpu":
            raise
        # GPU libraries missing/unusable -> retry on CPU
        _model_cache.pop((s.model, dev), None)
        progress(0.05, f"GPU not usable ({type(e).__name__}); using CPU")
        return run("cpu")


def _load_plugin():
    path = os.environ.get("SCRIPTSYNC_ASR_PLUGIN")
    if not path:
        return None
    spec = importlib.util.spec_from_file_location("scriptsync_asr_plugin", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def transcribe(path: str, s: Settings, lines: list, progress, cancel):
    """-> (list[AsrWord], duration, language). Uses the cache when allowed."""
    hint = vocab_hint(lines) if s.prime_vocab else ""
    plugin = _load_plugin()
    st = os.stat(path)
    key = hashlib.sha1(
        f"{os.path.abspath(path)}|{st.st_size}|{int(st.st_mtime)}|{s.model}|{s.language}|{hint}|"
        f"{'plugin' if plugin else 'fw'}".encode()).hexdigest()
    cpath = os.path.join(cache_dir(), key + ".json")
    if s.use_cache and os.path.exists(cpath):
        try:
            d = json.load(open(cpath, encoding="utf-8"))
            progress(0.85, "Using the saved transcript for this clip")
            return [AsrWord(**w) for w in d["words"]], d["duration"], d.get("language", "")
        except Exception:
            pass
    if plugin:
        words, dur, lang = plugin.transcribe(path, s.language, hint, progress, cancel)
        words = [w if isinstance(w, AsrWord) else AsrWord(*w) for w in words]
    else:
        words, dur, lang = _whisper_transcribe(path, s, hint, progress, cancel)
    try:
        json.dump({"words": [w.__dict__ for w in words], "duration": dur, "language": lang},
                  open(cpath, "w", encoding="utf-8"))
    except OSError:
        pass
    return words, dur, lang


# --------------------------------------------------------------------------
# Public entry points
# --------------------------------------------------------------------------
def sync_words(lines: list, asr: list, duration: float, s: Settings) -> SyncResult:
    """Pure alignment + cue building (no audio, no files)."""
    if not asr:
        raise SyncError("No speech was detected in this clip.")
    words, off = align_script(lines, asr, duration)
    if not duration:
        duration = max(w.end for w in asr)
    cues, skipped = build_cues(words, lines, s, duration)
    heard = sum(1 for w in words if w.anchored and w.conf >= 0.85) / max(len(words), 1)
    pct = 100.0 * sum(w.conf for w in words) / max(len(words), 1)
    warnings = []
    if heard < 0.4:
        warnings.append("Less than 40% of the script was found in the audio. Is this the right "
                        "script for this clip, is the language set correctly, or is there loud music?")
    res = SyncResult(
        cues=cues, skipped=skipped, off_script=off, warnings=warnings, match_pct=pct,
        n_ok=sum(c.level == "ok" for c in cues), n_check=sum(c.level == "check" for c in cues),
        n_bad=sum(c.level == "bad" for c in cues), duration=duration)
    res.srt_text = make_srt(cues)
    return res


def run_job(job: Job, s: Settings, progress: Callable = None, cancel=None) -> SyncResult:
    progress = progress or (lambda f, m: None)
    if not os.path.exists(job.video):
        raise SyncError(f"Can't find the clip: {job.video}")
    if job.script_text is not None and job.script_text.strip():
        raw, script_label = job.script_text, "(pasted text)"
    elif job.script_path:
        if not os.path.exists(job.script_path):
            raise SyncError(f"Can't find the script: {job.script_path}")
        raw, script_label = read_script_file(job.script_path), os.path.basename(job.script_path)
    else:
        raise SyncError("No script was given for this clip.")
    lines = parse_script(raw, s)
    if not lines:
        raise SyncError("The script is empty after cleaning (is everything in [brackets]?).")
    asr, dur, lang = transcribe(job.video, s, lines, progress, cancel)
    if cancel and cancel.is_set():
        raise Cancelled()
    progress(0.88, "Matching the script to the audio")
    res = sync_words(lines, asr, dur, s)
    n_words = sum(len(l.split()) for l in lines)
    res.report_text = make_report(job.label(), script_label, res, s, len(lines), n_words,
                                  lang or s.language)
    out_dir = job.out_dir or os.path.dirname(os.path.abspath(job.video))
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(job.video))[0]
    res.srt_path = os.path.join(out_dir, stem + ".synced.srt")
    res.report_path = os.path.join(out_dir, stem + ".review.txt")
    progress(0.96, "Writing files")
    try:
        with open(res.srt_path, "w", encoding="utf-8", newline="") as f:
            f.write(res.srt_text)
        with open(res.report_path, "w", encoding="utf-8", newline="") as f:
            f.write(res.report_text)
    except OSError as e:
        raise SyncError(f"Couldn't save to '{out_dir}': {e.strerror or e}")
    progress(1.0, "Done")
    return res


# --------------------------------------------------------------------------
# Finding script files for clips
# --------------------------------------------------------------------------
def find_script_for(video: str) -> Optional[str]:
    d, name = os.path.split(os.path.abspath(video))
    stem = os.path.splitext(name)[0].lower()
    try:
        files = os.listdir(d)
    except OSError:
        return None
    cands = []
    for f in files:
        fs, ext = os.path.splitext(f)
        if ext.lower() not in SCRIPT_EXTS or f.startswith("~$"):
            continue
        if f.lower().endswith((".synced.srt",)):
            continue
        if fs.lower() == stem:
            cands.append((0, SCRIPT_EXTS.index(ext.lower()), f))
        elif fs.lower().startswith(stem) or stem.startswith(fs.lower()):
            cands.append((1, SCRIPT_EXTS.index(ext.lower()), f))
    if not cands:
        return None
    cands.sort()
    return os.path.join(d, cands[0][2])


def scan_folder(folder: str) -> list:
    """-> list of (video_path, script_path_or_None) for every clip in a folder."""
    out = []
    for f in sorted(os.listdir(folder)):
        p = os.path.join(folder, f)
        if os.path.isfile(p) and os.path.splitext(f)[1].lower() in VIDEO_EXTS:
            out.append((p, find_script_for(p)))
    return out


# --------------------------------------------------------------------------
# Command line (for power users):  python scriptsync_core.py clip.mp4 script.docx
# --------------------------------------------------------------------------
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Sync a writer's script to a clip's audio -> SRT")
    ap.add_argument("video")
    ap.add_argument("script", help=".docx / .txt / .md / .srt")
    ap.add_argument("-o", "--out", help="output folder (default: next to the clip)")
    ap.add_argument("--model", default="small")
    ap.add_argument("--language", default="auto")
    ap.add_argument("--max-chars", type=int, default=40)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(argv)
    s = Settings(model=a.model, language=a.language, max_chars=a.max_chars, use_cache=not a.no_cache)

    def prog(f, m):
        print(f"[{int(f * 100):3d}%] {m}", file=sys.stderr)

    try:
        res = run_job(Job(a.video, a.script, None, a.out), s, prog)
    except SyncError as e:
        print("Error:", e, file=sys.stderr)
        return 1
    print(res.srt_path)
    print(res.report_path)
    print(f"{len(res.cues)} cues: {res.n_ok} OK, {res.n_check} CHECK, {res.n_bad} BAD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
