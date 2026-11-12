"""Cut the demo: eased camera zooms, captions, an original synthesized soundtrack and sound effects.

Reads demo/out/raw.webm and demo/out/timeline.json (from record.py), writes demo/out/errand-demo.mp4.
Everything audible is generated here with NumPy, so there is nothing to license.

    demo/.venv/Scripts/python demo/edit.py
"""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np

OUT = Path(__file__).resolve().parent / "out"
FPS = 30
SR = 44100
ZOOM_S = 0.9          # seconds per camera move
XF = 0.7              # cross-fade between scenes, seconds
FAST = 8              # time-lapse factor for model think time
FONT = "C\\:/Windows/Fonts/segoeuib.ttf"


# ---------------------------------------------------------------- camera

def ease(k: float) -> float:
    k = min(1.0, max(0.0, k))
    return 4 * k * k * k if k < 0.5 else 1 - (-2 * k + 2) ** 3 / 2


def camera_track(events: list[dict], w: int, h: int):
    """Return f(t) -> (cx, cy, scale), easing between targets set by zoom events."""
    keys = [(0.0, (w / 2, h / 2, 1.0), ZOOM_S)]
    for e in events:
        if e["kind"] != "zoom":
            continue
        if e["box"] is None:
            target = (w / 2, h / 2, 1.0)
        else:
            x, y, bw, bh = e["box"]
            s = max(1.0, min(e["scale"], w / max(bw, 1), h / max(bh, 1)))
            target = (x + bw / 2, y + bh / 2, s)
        keys.append((e["t"], target, 0.001 if e.get("snap") else ZOOM_S))

    def at(t: float):
        cur = keys[0][1]
        for i, (t0, target, dur) in enumerate(keys[1:], 1):
            if t < t0:
                break
            prev = cur
            k = ease((t - t0) / dur)
            cur = tuple(p + (q - p) * k for p, q in zip(prev, target))
        cx, cy, s = cur
        hw, hh = w / (2 * s), h / (2 * s)
        cx, cy = min(max(cx, hw), w - hw), min(max(cy, hh), h - hh)
        return cx, cy, s

    return at


def fast_spans(events: list[dict]) -> list[tuple[float, float]]:
    """(start, end) spans, in recorded time, that play as a time-lapse."""
    spans, start = [], None
    for e in events:
        if e["kind"] == "fast" and e["on"] and start is None:
            start = e["t"]
        elif e["kind"] == "fast" and not e["on"] and start is not None:
            if e["t"] - start > 0.5:
                spans.append((start, e["t"]))
            start = None
    return spans


def cut_spans(events: list[dict]) -> list[tuple[float, float]]:
    """(cut, cutin) spans in recorded time: page loads between scenes, dropped and replaced by a cross-fade."""
    spans, start = [], None
    for e in events:
        if e["kind"] == "cut":
            start = e["t"]
        elif e["kind"] == "cutin" and start is not None:
            spans.append((start, e["t"]))
            start = None
    return spans


def retime(t: float, spans: list[tuple[float, float]], cuts: list[tuple[float, float]] = ()) -> float:
    """Recorded time -> time in the cut."""
    out = t
    for a, b in spans:
        if t > a:
            out -= (min(t, b) - a) * (1 - 1 / FAST)
    for a, b in cuts:
        if t > a:
            out -= min(t, b) - a
    return out


def render_video(src: Path, dst: Path, events: list[dict], spans: list[tuple[float, float]],
                 cuts: list[tuple[float, float]] = ()) -> float:
    cap = cv2.VideoCapture(str(src))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cam = camera_track(events, w, h)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                            "-pix_fmt", "yuv420p", str(dst)], stdin=subprocess.PIPE)
    n = kept = 0
    held, fade_left = None, 0
    last = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = n / FPS
        n += 1
        if any(a <= t < b for a, b in cuts):
            if held is None:
                held = last  # the last frame of the outgoing scene
            continue
        if held is not None and fade_left == 0:
            fade_left = int(XF * FPS)
        if any(a <= t < b for a, b in spans) and n % FAST:
            continue  # time-lapse: keep one frame in FAST
        cx, cy, s = cam(t)
        if s > 1.001:
            m = np.float32([[s, 0, w / 2 - s * cx], [0, s, h / 2 - s * cy]])
            frame = cv2.warpAffine(frame, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        last = frame
        if fade_left and held is not None:
            k = 1 - fade_left / int(XF * FPS)
            k = k * k * (3 - 2 * k)
            frame = cv2.addWeighted(held, 1 - k, frame, k, 0)
            fade_left -= 1
            if fade_left == 0:
                held = None
        enc.stdin.write(frame.tobytes())
        kept += 1
    cap.release()
    enc.stdin.close()
    enc.wait()
    return kept / FPS


# ---------------------------------------------------------------- audio

def env(n: int, attack: float, release: float) -> np.ndarray:
    a, r = max(1, int(attack * SR)), max(1, int(release * SR))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)[: n]
    e[-r:] *= np.linspace(1, 0, min(r, n))
    return e


def tone(freq: float, dur: float, kind: str = "sine") -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    ph = 2 * np.pi * freq * t
    if kind == "tri":
        return 2 / np.pi * np.arcsin(np.sin(ph))
    return np.sin(ph)


def note(n: int) -> float:  # MIDI note -> Hz
    return 440.0 * 2 ** ((n - 69) / 12)


def soundtrack(dur: float) -> np.ndarray:
    """A warm, unobtrusive 92 BPM loop: Am9, Fmaj7, Cmaj7, G6 pads, round bass, soft kick and hats."""
    bpm, out = 92, np.zeros(int(dur * SR) + SR)
    beat = 60 / bpm
    bar = 4 * beat
    chords = [[57, 60, 64, 67, 71], [53, 57, 60, 64, 69], [48, 55, 59, 64, 67], [55, 59, 62, 64, 67]]
    bass = [45, 41, 48, 43]
    t = 0.0
    i = 0
    rng = np.random.default_rng(3)
    while t < dur:
        c = chords[i % 4]
        start = int(t * SR)
        pad = sum(0.6 * tone(note(m), bar, "tri") + 0.4 * tone(note(m) * 1.003, bar) for m in c) / len(c)
        pad *= env(len(pad), 0.35, 0.6) * 0.22
        b = tone(note(bass[i % 4]), bar * 0.95) * env(int(bar * 0.95 * SR), 0.02, 0.4) * 0.28
        seg = out[start:start + len(pad)]
        seg += pad[: len(seg)]
        out[start:start + len(b)] += b[: len(out[start:start + len(b)])]
        for k in range(4):
            bt = start + int(k * beat * SR)
            if k in (0, 2):  # soft kick
                n = int(0.22 * SR)
                f = np.linspace(110, 45, n)
                kick = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-np.linspace(0, 9, n)) * 0.45
                out[bt:bt + n] += kick[: len(out[bt:bt + n])]
            hs = bt + int(beat * SR / 2)  # off-beat hat
            n = int(0.05 * SR)
            hat = np.diff(rng.normal(0, 1, n + 1)) * np.exp(-np.linspace(0, 8, n)) * 0.035
            out[hs:hs + n] += hat[: len(out[hs:hs + n])]
        t += bar
        i += 1
    out = out[: int(dur * SR)]
    out *= env(len(out), 1.2, 2.5)
    return out


def sfx(name: str) -> np.ndarray:
    """Soft, purely tonal cues that sit inside the jingle (no noise-based whooshes)."""
    if name == "click":
        n = int(0.09 * SR)
        return (tone(880, 0.09) + 0.5 * tone(1320, 0.09)) * np.exp(-np.linspace(0, 9, n)) * 0.10
    if name == "ding":
        n = int(1.6 * SR)
        d = np.exp(-np.linspace(0, 4.5, n)) * env(n, 0.004, 0.2)
        return (tone(1046.5, 1.6) * 0.6 + tone(1568, 1.6) * 0.3 + tone(2093, 1.6) * 0.08) * d * 0.16
    return np.zeros(1)


def mix_audio(events: list[dict], dur: float, dst: Path) -> None:
    music = soundtrack(dur)
    fx = np.zeros_like(music)
    cache: dict[str, np.ndarray] = {}
    for e in events:
        name = e.get("name") if e["kind"] == "sfx" else None
        if not name:
            continue
        s = cache.setdefault(name, sfx(name))
        i = int(e["t"] * SR)
        seg = fx[i:i + len(s)]
        seg += s[: len(seg)]
    mix = music + fx
    mix /= max(1.0, np.max(np.abs(mix)) / 0.89)
    pcm = (np.stack([mix, mix], axis=1) * 32767).astype("<i2")
    with wave.open(str(dst), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- captions and final mux

def caption_filter(events: list[dict]) -> str:
    """Lower-third captions: a dark pill with a thin light ring, so they read on paper and on Forest alike.
    A caption ends early if the next one starts, so two never overlap."""
    parts = []
    caps = [e for e in events if e["kind"] == "caption"]
    for i, e in enumerate(caps):
        a = e["t"] + 0.2
        b = a + e["dur"]
        if i + 1 < len(caps):
            b = min(b, caps[i + 1]["t"] + 0.1)
        f = OUT / "captions" / f"{i:02d}.txt"
        f.parent.mkdir(exist_ok=True)
        f.write_text(e["text"], encoding="utf-8")
        path = str(f).replace("\\", "/").replace(":", "\\:")
        alpha = f"if(lt(t,{a}+0.25),(t-{a})/0.25,if(gt(t,{b}-0.3),({b}-t)/0.3,1))"
        common = (f"fontfile='{FONT}':textfile='{path}':fontsize=44:x=(w-text_w)/2:y=h-text_h-110:"
                  f"alpha='{alpha}':enable='between(t,{a},{b})'")
        parts.append(f"drawtext={common}:fontcolor=0xF4F0E6@0:box=1:boxcolor=0xF4F0E6@0.9:boxborderw=30|44")
        parts.append(f"drawtext={common}:fontcolor=0xF4F0E6:box=1:boxcolor=0x0B2A21@0.94:boxborderw=26|40")
    return ",".join(parts) or "null"


def main() -> None:
    timeline = json.loads((OUT / "timeline.json").read_text(encoding="utf-8"))
    events = timeline["events"]
    cfr = OUT / "cfr.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(OUT / "raw.webm"), "-r", str(FPS), "-c:v", "libx264",
                    "-crf", "14", "-preset", "veryfast", "-an", str(cfr)], check=True)
    spans, cuts = fast_spans(events), cut_spans(events)
    print(f"zooming ({len(spans)} time-lapse spans, {len(cuts)} cross-fades)...")
    dur = render_video(cfr, OUT / "zoomed.mp4", events, spans, cuts)
    events = [e | {"t": round(retime(e["t"], spans, cuts), 3)} for e in events]  # cues follow the cut
    print("mixing audio...")
    mix_audio(events, dur, OUT / "audio.wav")
    print("captions and mux...")
    badge = "".join(
        f",drawtext=fontfile='{FONT}':text='8× speed':fontsize=30:fontcolor=0x0B2A21:box=1:boxcolor=0xE0F354@0.95:"
        f"boxborderw=12|18:x=w-text_w-60:y=50:enable='between(t,{retime(a, spans, cuts):.2f},{retime(b, spans, cuts):.2f})'"
        for a, b in spans)
    vf = caption_filter(events) + badge + f",fade=t=in:st=0:d=0.6,fade=t=out:st={dur - 1.2:.2f}:d=1.2"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(OUT / "zoomed.mp4"), "-i", str(OUT / "audio.wav"),
                    "-vf", vf, "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
                    str(OUT / "errand-demo.mp4")], check=True)
    print(f"wrote {OUT / 'errand-demo.mp4'} ({dur:.1f}s)")


if __name__ == "__main__":
    main()
