from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"


@dataclass(frozen=True)
class TeamConfig:
    id: str
    name: str
    short_name: str
    abbreviation: str
    sport: str
    league: str
    espn_id: str
    accent: str


@dataclass(frozen=True)
class AppConfig:
    timezone: str
    driver: str
    display_mode: str
    mock_path: Path
    state_path: Path
    live_seconds: int
    idle_seconds: int
    error_backoff_seconds: int
    espn_base_url: str
    teams: tuple[TeamConfig, ...]

    @property
    def root(self) -> Path:
        return ROOT


def _as_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    with config_path.open(encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh) or {}

    display = raw.get("display") or {}
    poll = raw.get("poll") or {}
    espn = raw.get("espn") or {}
    teams_raw = raw.get("teams") or []

    teams = tuple(
        TeamConfig(
            id=str(t["id"]),
            name=str(t["name"]),
            short_name=str(t.get("short_name") or t["name"]),
            abbreviation=str(t["abbreviation"]),
            sport=str(t["sport"]),
            league=str(t["league"]),
            espn_id=str(t["espn_id"]),
            accent=str(t.get("accent") or "blue"),
        )
        for t in teams_raw
    )
    if not teams:
        raise ValueError("config.yaml must define at least one team")

    return AppConfig(
        timezone=str(raw.get("timezone") or "America/Chicago"),
        driver=str(display.get("driver") or "epd7in3f"),
        display_mode=str(display.get("mode") or "auto"),
        mock_path=_as_path(display.get("mock_path") or "out/preview.png"),
        state_path=_as_path(display.get("state_path") or "out/last_state.json"),
        live_seconds=int(poll.get("live_seconds") or 60),
        idle_seconds=int(poll.get("idle_seconds") or 900),
        error_backoff_seconds=int(poll.get("error_backoff_seconds") or 120),
        espn_base_url=str(
            espn.get("base_url")
            or "https://site.web.api.espn.com/apis/site/v2/sports"
        ).rstrip("/"),
        teams=teams,
    )
