"""Runtime settings, read from environment variables and an optional .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

MICROS = 1_000_000  # all money is stored as integer micro-dollars


def to_micros(usd: float) -> int:
    return int(round(float(usd) * MICROS))


def to_usd(micros: int) -> float:
    return micros / MICROS


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    db_path: str
    base_url: str
    demo: bool
    villain: bool  # seed Shady, the model-swapping Runner, for integrity demos
    take_rate: float
    mystery_rate: float
    sim_latency_scale: float
    paypal_client_id: str
    paypal_secret: str
    paypal_api_base: str

    @property
    def paypal_live(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_secret)


def load_settings() -> Settings:
    _load_dotenv(Path.cwd() / ".env")
    env = os.environ.get
    return Settings(
        db_path=env("ERRAND_DB", str(Path.cwd() / ".errand" / "errand.db")),
        # Render injects RENDER_EXTERNAL_URL, so hosted deploys need no URL config at all
        base_url=(env("ERRAND_BASE_URL") or env("RENDER_EXTERNAL_URL") or "http://localhost:8000").rstrip("/"),
        demo=env("ERRAND_DEMO", "1") == "1",
        villain=env("ERRAND_VILLAIN", "0") == "1",
        take_rate=float(env("ERRAND_TAKE_RATE", "0.10")),
        mystery_rate=float(env("ERRAND_MYSTERY_RATE", "0.25")),
        sim_latency_scale=float(env("ERRAND_SIM_LATENCY_SCALE", "1.0")),
        paypal_client_id=env("PAYPAL_CLIENT_ID", ""),
        paypal_secret=env("PAYPAL_CLIENT_SECRET", ""),
        paypal_api_base=env("PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com").rstrip("/"),
    )


settings = load_settings()


def configure(**overrides) -> Settings:
    """Replace settings in place (used by tests and the CLI)."""
    global settings
    settings = replace(settings, **overrides)
    return settings


def get() -> Settings:
    return settings
