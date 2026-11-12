"""Generate the voiceover: one clip per line, placed at a time in the final cut (seconds).

Each line must end before the next one starts; a line that runs long is re-spoken a little faster.
Writes demo/out/voice/NN.mp3 and demo/out/voice/lines.json, which edit.py mixes in.

    demo/.venv/Scripts/python demo/voice.py
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import edge_tts

OUT = Path(__file__).resolve().parent / "out" / "voice"
VOICE = "en-US-AndrewMultilingualNeural"
END = 144.5

# (start in the final cut, text). Starts follow the captions in edit.py's timeline.
LINES = [
    (0.8, "Meet Errand."),
    (5.4, "AI agents run on frontier models. And every single call is billed at frontier prices."),
    (14.8, "But most of those calls are small, well-defined jobs."),
    (18.9, "You're paying a genius to do arithmetic."),
    (22.5, "Errand sends those jobs to cheap specialists. The bill drops by half."),
    (28.0, "One call to Errand, and every answer is checked before anyone gets paid."),
    (36.4, "Here's a real coding agent, running locally, with one new tool: Errand."),
    (45.5, "Each function goes out with its tests."),
    (49.3, "Errand runs the tests. Only passing code gets paid."),
    (58.8, "A different specialist this time. Each job cost a fraction of a cent."),
    (65.8, "And the verified code lands in your project."),
    (70.4, "Every errand your agent sends shows up on your dashboard."),
    (75.6, "No right answer? You pay nothing."),
    (81.0, "You can also send one yourself, with the answer you expect."),
    (87.9, "The payment is held, the answer is checked, and then the specialist gets paid."),
    (93.4, "Top up with PayPal."),
    (95.9, "That's the real PayPal sandbox checkout. Only a human can approve it."),
    (100.5, "Every PayPal step is logged, with its sandbox ID."),
    (107.2, "And specialists cash out through PayPal Payouts, live on the hosted demo."),
    (116.0, "We ran real open models through Errand, on checked tasks."),
    (121.5, "Picking the right model for each job beats any single model."),
    (127.1, "Specialists are ranked by how often they're right."),
    (130.8, "One line connects Claude Code, Cursor, VS Code, and more."),
    (136.6, "Errand is open source, and open to funding. Come try it."),
]


def duration(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


async def speak(text: str, rate: int, dst: Path) -> float:
    await edge_tts.Communicate(text, VOICE, rate=f"{rate:+d}%").save(str(dst))
    return duration(dst)


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    out = []
    for i, (start, text) in enumerate(LINES):
        room = (LINES[i + 1][0] if i + 1 < len(LINES) else END) - start - 0.25
        dst = OUT / f"{i:02d}.mp3"
        rate = 0
        d = await speak(text, rate, dst)
        while d > room and rate < 20:
            rate += 5
            d = await speak(text, rate, dst)
        flag = "  OVER" if d > room else ""
        print(f"{start:6.1f}  {d:4.1f}s / {room:4.1f}s  rate {rate:+d}%{flag}  {text}")
        out.append({"t": start, "file": dst.name, "dur": round(d, 2), "text": text})
    (OUT / "lines.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
