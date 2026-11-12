"""Cut the demo: eased camera zooms, captions, voiceover, an original synthesized soundtrack and sound effects.

Reads demo/out/raw.webm and demo/out/timeline.json (from record.py), writes demo/out/errand-demo.mp4.
Everything audible is generated here with NumPy, so there is nothing to license.

    demo/.venv/Scripts/python demo/edit.py [--audio-only]   (--audio-only reuses out/zoomed.mp4)
"""

from __future__ import annotations

import json
import subprocess
import sys
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
    """A slow, soothing 70 BPM bed: soft sine pads (Fmaj9, Em7, Dm9, Cmaj9), a round bass and a quiet
    music-box arpeggio. No drums, so it sits well under a voice."""
    bpm, out = 70, np.zeros(int(dur * SR) + 4 * SR)
    beat = 60 / bpm
    bar = 4 * beat
    chords = [[53, 57, 60, 64, 67], [52, 55, 59, 62, 67], [50, 53, 57, 60, 64], [48, 52, 55, 59, 62]]
    bass = [41, 40, 38, 36]
    arp = [0, 2, 3, 4, 3, 2, 1, 2]
    t, i = 0.0, 0
    while t < dur:
        c = chords[i % 4]
        start = int(t * SR)
        n = int(bar * 1.25 * SR)  # pads overlap the next bar a little, so changes melt together
        pad = sum(tone(note(m), bar * 1.25) + 0.5 * tone(note(m) * 1.004, bar * 1.25) for m in c) / len(c)
        pad = pad[:n] * env(n, 0.9, 1.2) * 0.16
        out[start:start + n] += pad[: len(out[start:start + n])]
        bn = int(bar * SR)
        b = (tone(note(bass[i % 4]), bar) + 0.25 * tone(note(bass[i % 4]) * 2, bar))[:bn] * env(bn, 0.08, 0.8) * 0.2
        out[start:start + bn] += b[: len(out[start:start + bn])]
        for k, idx in enumerate(arp):  # eighth-note music box, one octave up
            bt = start + int(k * beat / 2 * SR)
            m = int(1.4 * SR)
            f = note(c[idx] + 12)
            bell = (tone(f, 1.4) + 0.3 * tone(f * 2, 1.4))[:m] * np.exp(-np.linspace(0, 6, m)) * env(m, 0.006, 0.1)
            out[bt:bt + m] += (bell * 0.05)[: len(out[bt:bt + m])]
        t += bar
        i += 1
    out = out[: int(dur * SR)]
    out *= env(len(out), 2.0, 3.0)
    return out


def sfx(name: str) -> np.ndarray:
    """Soft, purely tonal cues that sit inside the jingle."""
    if name == "click":
        n = int(0.09 * SR)
        return (tone(880, 0.09) + 0.5 * tone(1320, 0.09))[:n] * np.exp(-np.linspace(0, 9, n)) * 0.09
    if name == "tick":  # one call added to the bill
        n = int(0.06 * SR)
        return tone(1760, 0.06)[:n] * np.exp(-np.linspace(0, 12, n)) * 0.05
    if name == "ding":
        n = int(1.6 * SR)
        d = np.exp(-np.linspace(0, 4.5, n)) * env(n, 0.004, 0.2)
        return (tone(1046.5, 1.6) * 0.6 + tone(1568, 1.6) * 0.3 + tone(2093, 1.6) * 0.08)[:n] * d * 0.14
    if name == "coin":  # two quick rising notes
        parts = []
        for f, d in ((1318.5, 0.08), (1975.5, 0.5)):
            n = int(d * SR)
            x = (tone(f, d) + 0.25 * tone(f * 2, d))[:n]
            parts.append(x * np.exp(-np.linspace(0, 6, n)) * env(n, 0.003, 0.05))
        return np.concatenate(parts) * 0.10
    if name == "drop":  # the bill falls: a soft descending glide
        n = int(0.7 * SR)
        f = np.linspace(880, 440, n)
        return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.02, 0.4) * np.exp(-np.linspace(0, 2.5, n)) * 0.10
    if name == "swell":  # scene change: a gentle rising airy chord
        n = int(0.8 * SR)
        x = sum(tone(note(m), 0.8)[:n] for m in (72, 76, 79)) / 3
        return x * np.sin(np.linspace(0, np.pi, n)) ** 2 * 0.045
    if name == "outro":  # closing chord on the end card
        n = int(4.0 * SR)
        x = sum(tone(note(m), 4.0)[:n] * w for m, w in ((48, 1), (55, 0.8), (64, 0.7), (67, 0.6), (71, 0.5), (74, 0.4)))
        return x / 4 * env(n, 0.02, 2.5) * np.exp(-np.linspace(0, 1.5, n)) * 0.22
    return np.zeros(1)


def extra_cues(events: list[dict]) -> list[dict]:
    """Cues computed from the cut: ticks as the problem bill counts up, its drop, swells on scene changes,
    coins on money moments and a closing chord."""
    caps = [e for e in events if e["kind"] == "caption"]
    cues = []
    problem = next((e["t"] for e in caps if e["text"].startswith("Agents run on")), None)
    if problem is not None:  # mirrors PROBLEM_HTML (play starts just before the cut-in): a call every 0.62s
        cues += [{"kind": "sfx", "name": "tick", "t": problem + 1.5 + 0.62 * k} for k in range(10)]
        cues.append({"kind": "sfx", "name": "drop", "t": problem + 16.7})
    cuts = [e["t"] for e in events if e["kind"] == "cut"]
    cues += [{"kind": "sfx", "name": "swell", "t": max(0.0, t - 0.3)} for t in cuts[1:-1]]
    for e in caps:
        if e["text"].startswith(("No right answer", "Specialists cash out")):
            cues.append({"kind": "sfx", "name": "coin", "t": e["t"] + 0.6})
    if cuts:
        cues.append({"kind": "sfx", "name": "outro", "t": cuts[-1] + 0.4})
    return cues


def load_voice(dur: float) -> np.ndarray:
    """demo/out/voice (from voice.py) as one mono track, or silence if there is none."""
    track = np.zeros(int(dur * SR))
    meta = OUT / "voice" / "lines.json"
    if not meta.exists():
        return track
    for line in json.loads(meta.read_text(encoding="utf-8")):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(OUT / "voice" / line["file"]), "-ac", "1",
                              "-ar", str(SR), "-f", "f32le", "-"], capture_output=True, check=True).stdout
        v = np.frombuffer(raw, dtype="<f4").astype(np.float64)
        i = int(line["t"] * SR)
        seg = track[i:i + len(v)]
        seg += v[: len(seg)]
    peak = np.max(np.abs(track))
    return track / peak * 0.85 if peak else track


def duck(voice: np.ndarray, depth: float = 0.35) -> np.ndarray:
    """Gain for the music: drops to `depth` while the voice speaks, easing down fast and back up slowly."""
    hop = SR // 100
    frames = np.abs(voice[: len(voice) // hop * hop]).reshape(-1, hop).max(axis=1) > 0.02
    hold = np.convolve(frames.astype(float), np.ones(40), "same") > 0  # bridge gaps under 0.4s
    out, cur = np.empty(len(frames)), 1.0
    for k, on in enumerate(hold):
        target = depth if on else 1.0
        cur += (target - cur) * (0.16 if target < cur else 0.06)
        out[k] = cur
    gain = np.repeat(out, hop)
    return np.pad(gain, (0, len(voice) - len(gain)), constant_values=1.0)


def mix_audio(events: list[dict], dur: float, dst: Path) -> None:
    music = soundtrack(dur)
    fx = np.zeros_like(music)
    cache: dict[str, np.ndarray] = {}
    for e in events + extra_cues(events):
        name = e.get("name") if e["kind"] == "sfx" else None
        if not name:
            continue
        s = cache.setdefault(name, sfx(name))
        i = int(e["t"] * SR)
        seg = fx[i:i + len(s)]
        seg += s[: len(seg)]
    voice = load_voice(dur)
    music = music / max(1e-9, np.max(np.abs(music))) * 0.32
    g = duck(voice)
    mix = music * g + fx * (0.6 + 0.4 * g) + voice
    mix /= max(1.0, np.max(np.abs(mix)) / 0.95)
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
    if "--audio-only" not in sys.argv:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(OUT / "raw.webm"), "-r", str(FPS), "-c:v",
                        "libx264", "-crf", "14", "-preset", "veryfast", "-an", str(cfr)], check=True)
    spans, cuts = fast_spans(events), cut_spans(events)
    if "--audio-only" in sys.argv and (OUT / "zoomed.mp4").exists():  # reuse the rendered picture
        dur = int(cv2.VideoCapture(str(OUT / "zoomed.mp4")).get(cv2.CAP_PROP_FRAME_COUNT)) / FPS
    else:
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
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart",
                    str(OUT / "errand-demo.mp4")], check=True)
    print(f"wrote {OUT / 'errand-demo.mp4'} ({dur:.1f}s)")


if __name__ == "__main__":
    main()
