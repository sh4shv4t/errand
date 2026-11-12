"""Tighten the finished demo for social: speed up the gaps between voiceover lines a lot, the lines a little.

Reads demo/out/errand-demo.mp4 and demo/out/voice/lines.json, writes demo/out/errand-demo-fast.mp4.
atempo keeps the pitch, so the voice and music sound natural.

    demo/.venv/Scripts/python demo/tighten.py [voice_speed] [gap_speed]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
PAD = 0.15


def duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def segments(lines: list[dict], end: float, voice: float, gap: float) -> list[tuple[float, float, float]]:
    spoken = []
    for ln in lines:
        a, b = max(0.0, ln["t"] - PAD), min(end, ln["t"] + ln["dur"] + PAD)
        if spoken and a <= spoken[-1][1]:
            spoken[-1][1] = max(spoken[-1][1], b)
        else:
            spoken.append([a, b])
    out, cur = [], 0.0
    for a, b in spoken:
        if a - cur > 0.05:
            out.append((cur, a, gap))
        out.append((a, b, voice))
        cur = b
    if end - cur > 0.05:
        out.append((cur, end, gap))
    return out


def main() -> None:
    voice = float(sys.argv[1]) if len(sys.argv) > 1 else 1.1
    gap = float(sys.argv[2]) if len(sys.argv) > 2 else 1.7
    src, dst = OUT / "errand-demo.mp4", OUT / "errand-demo-fast.mp4"
    lines = json.loads((OUT / "voice" / "lines.json").read_text(encoding="utf-8"))
    segs = segments(lines, duration(src), voice, gap)
    parts, labels = [], []
    for i, (a, b, s) in enumerate(segs):
        parts.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=(PTS-STARTPTS)/{s}[v{i}]")
        parts.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,atempo={s}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append("".join(labels) + f"concat=n={len(segs)}:v=1:a=1[v][a]")
    graph = OUT / "tighten.filter"
    graph.write_text(";\n".join(parts), encoding="utf-8")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex_script", str(graph),
                    "-map", "[v]", "-map", "[a]", "-r", "30", "-c:v", "libx264", "-crf", "19", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)],
                   check=True)
    print(f"wrote {dst} ({duration(dst):.1f}s from {duration(src):.1f}s, {len(segs)} segments)")


if __name__ == "__main__":
    main()
