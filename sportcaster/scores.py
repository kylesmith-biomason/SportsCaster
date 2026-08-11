from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

import requests

from .config import AppConfig, TeamConfig

Status = Literal["pre", "in", "post", "unknown"]

_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (compatible; SportCaster/0.1; "
            "+https://github.com/local/sportcaster)"
        ),
        "Accept": "application/json",
        "Referer": "https://www.espn.com/",
    }
)


@dataclass
class Side:
    name: str
    abbreviation: str
    score: int | None
    home_away: Literal["home", "away"]
    winner: bool | None = None


@dataclass
class GameState:
    event_id: str
    status: Status
    detail: str
    short_detail: str
    start_time: str  # ISO-8601 UTC
    our_side: Side
    opponent: Side
    venue: str | None = None

    @property
    def is_live(self) -> bool:
        return self.status == "in"

    @property
    def is_final(self) -> bool:
        return self.status == "post"

    @property
    def is_upcoming(self) -> bool:
        return self.status == "pre"

    def matchup_label(self) -> str:
        opp = self.opponent.name
        if self.our_side.home_away == "home":
            return f"vs {opp}"
        return f"@ {opp}"

    def score_line(self, our_short: str) -> str:
        ours = self.our_side.score if self.our_side.score is not None else "-"
        theirs = self.opponent.score if self.opponent.score is not None else "-"
        return f"{our_short} {ours}  {self.opponent.abbreviation} {theirs}"

    def result_line(self, our_short: str) -> str:
        if self.our_side.score is None or self.opponent.score is None:
            return f"Last: {self.matchup_label()}"
        ours = self.our_side.score
        theirs = self.opponent.score
        if ours > theirs:
            outcome = "W"
        elif ours < theirs:
            outcome = "L"
        else:
            outcome = "T"
        return f"Last: {outcome} {ours}-{theirs} {self.matchup_label()}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameState:
        return cls(
            event_id=str(data["event_id"]),
            status=data["status"],
            detail=str(data.get("detail") or ""),
            short_detail=str(data.get("short_detail") or ""),
            start_time=str(data["start_time"]),
            our_side=Side(**data["our_side"]),
            opponent=Side(**data["opponent"]),
            venue=data.get("venue"),
        )


@dataclass
class TeamBoard:
    team_id: str
    team_name: str
    short_name: str
    abbreviation: str
    accent: str
    current_or_last: GameState | None
    next_game: GameState | None

    @property
    def is_live(self) -> bool:
        return bool(self.current_or_last and self.current_or_last.is_live)

    def fingerprint(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "current_or_last": (
                self.current_or_last.to_dict() if self.current_or_last else None
            ),
            "next_game": self.next_game.to_dict() if self.next_game else None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "team_name": self.team_name,
            "short_name": self.short_name,
            "abbreviation": self.abbreviation,
            "accent": self.accent,
            "current_or_last": (
                self.current_or_last.to_dict() if self.current_or_last else None
            ),
            "next_game": self.next_game.to_dict() if self.next_game else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TeamBoard:
        cur = data.get("current_or_last")
        nxt = data.get("next_game")
        return cls(
            team_id=str(data["team_id"]),
            team_name=str(data["team_name"]),
            short_name=str(data["short_name"]),
            abbreviation=str(data["abbreviation"]),
            accent=str(data.get("accent") or "blue"),
            current_or_last=GameState.from_dict(cur) if cur else None,
            next_game=GameState.from_dict(nxt) if nxt else None,
        )


@dataclass
class BoardSnapshot:
    fetched_at: str
    boards: list[TeamBoard]

    @property
    def any_live(self) -> bool:
        return any(b.is_live for b in self.boards)

    def fingerprint(self) -> list[dict[str, Any]]:
        return [b.fingerprint() for b in self.boards]

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched_at": self.fetched_at,
            "boards": [b.to_dict() for b in self.boards],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BoardSnapshot:
        return cls(
            fetched_at=str(data.get("fetched_at") or ""),
            boards=[TeamBoard.from_dict(b) for b in data.get("boards") or []],
        )


def format_start_time(iso_utc: str, tz_name: str) -> str:
    """Format ESPN start time for the display, e.g. 'Tue Aug 11 · 6:45 PM CDT'."""
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(ZoneInfo(tz_name))
    hour = local.strftime("%I").lstrip("0") or "0"
    minute = local.strftime("%M")
    ampm = local.strftime("%p")
    tz_abbr = local.tzname() or ""
    try:
        date_part = local.strftime("%a %b %-d")
    except ValueError:
        date_part = local.strftime("%a %b %d").replace(" 0", " ")
    return f"{date_part} · {hour}:{minute} {ampm} {tz_abbr}".strip()


def _score_value(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("displayValue", raw.get("value"))
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _parse_event(event: dict[str, Any], team: TeamConfig) -> GameState | None:
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    comp = competitions[0]
    competitors = comp.get("competitors") or []
    if len(competitors) < 2:
        return None

    our = None
    opp = None
    for c in competitors:
        tid = str((c.get("team") or {}).get("id") or c.get("id") or "")
        abbr = str((c.get("team") or {}).get("abbreviation") or "")
        if tid == team.espn_id or abbr.upper() == team.abbreviation.upper():
            our = c
        else:
            opp = c
    if our is None or opp is None:
        return None

    status_block = (comp.get("status") or {}).get("type") or {}
    state = str(status_block.get("state") or "unknown")
    if state not in ("pre", "in", "post"):
        state = "unknown"

    our_team = our.get("team") or {}
    opp_team = opp.get("team") or {}
    home_away = our.get("homeAway") or "home"
    if home_away not in ("home", "away"):
        home_away = "home"
    opp_home_away = opp.get("homeAway") or ("away" if home_away == "home" else "home")
    if opp_home_away not in ("home", "away"):
        opp_home_away = "away"

    start = str(comp.get("date") or event.get("date") or "")
    venue = None
    venue_block = comp.get("venue") or {}
    if isinstance(venue_block, dict):
        venue = venue_block.get("fullName") or venue_block.get("name")

    return GameState(
        event_id=str(event.get("id") or comp.get("id") or ""),
        status=state,  # type: ignore[arg-type]
        detail=str(status_block.get("detail") or status_block.get("description") or ""),
        short_detail=str(
            status_block.get("shortDetail") or status_block.get("detail") or ""
        ),
        start_time=start,
        our_side=Side(
            name=str(
                our_team.get("shortDisplayName")
                or our_team.get("displayName")
                or team.short_name
            ),
            abbreviation=str(our_team.get("abbreviation") or team.abbreviation),
            score=_score_value(our.get("score")),
            home_away=home_away,  # type: ignore[arg-type]
            winner=our.get("winner"),
        ),
        opponent=Side(
            name=str(
                opp_team.get("shortDisplayName")
                or opp_team.get("displayName")
                or opp_team.get("name")
                or "Opponent"
            ),
            abbreviation=str(opp_team.get("abbreviation") or "OPP"),
            score=_score_value(opp.get("score")),
            home_away=opp_home_away,  # type: ignore[arg-type]
            winner=opp.get("winner"),
        ),
        venue=venue,
    )


def _fetch_json(url: str, timeout: float = 20.0) -> dict[str, Any]:
    resp = _SESSION.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected ESPN payload from {url}")
    return data


def _schedule_url(cfg: AppConfig, team: TeamConfig) -> str:
    return (
        f"{cfg.espn_base_url}/{team.sport}/{team.league}/teams/"
        f"{team.espn_id}/schedule"
    )


def _scoreboard_url(cfg: AppConfig, team: TeamConfig) -> str:
    return f"{cfg.espn_base_url}/{team.sport}/{team.league}/scoreboard"


def _pick_games(events: list[GameState]) -> tuple[GameState | None, GameState | None]:
    """Return (current_or_last, next_game)."""
    live = [g for g in events if g.status == "in"]
    upcoming = sorted(
        [g for g in events if g.status == "pre"],
        key=lambda g: g.start_time,
    )
    completed = sorted(
        [g for g in events if g.status == "post"],
        key=lambda g: g.start_time,
    )

    current_or_last: GameState | None = None
    next_game: GameState | None = None

    if live:
        current_or_last = live[0]
        # Next after the live game (if any later scheduled)
        later = [g for g in upcoming if g.start_time > current_or_last.start_time]
        next_game = later[0] if later else (upcoming[0] if upcoming else None)
    elif upcoming:
        # Treat nearest upcoming as both "current focus" and next_game
        next_game = upcoming[0]
        current_or_last = completed[-1] if completed else upcoming[0]
        # If we only have upcoming, current_or_last is the same upcoming game
        if not completed:
            current_or_last = upcoming[0]
    elif completed:
        current_or_last = completed[-1]
        next_game = None
    return current_or_last, next_game


def fetch_team_board(cfg: AppConfig, team: TeamConfig) -> TeamBoard:
    """Fetch schedule (and today's scoreboard overlay) for one team."""
    schedule = _fetch_json(_schedule_url(cfg, team))
    events_raw = schedule.get("events") or []
    games: list[GameState] = []
    for event in events_raw:
        parsed = _parse_event(event, team)
        if parsed:
            games.append(parsed)

    # Overlay today's scoreboard for fresher live scores / clock detail
    try:
        scoreboard = _fetch_json(_scoreboard_url(cfg, team))
        by_id = {g.event_id: g for g in games}
        for event in scoreboard.get("events") or []:
            parsed = _parse_event(event, team)
            if not parsed:
                continue
            by_id[parsed.event_id] = parsed
            if parsed.event_id not in {g.event_id for g in games}:
                games.append(parsed)
        games = list(by_id.values())
    except requests.RequestException:
        # Schedule alone is enough for idle / next-game views
        pass

    current_or_last, next_game = _pick_games(games)

    # When current focus is an upcoming game, keep next_game pointing at it
    if (
        current_or_last
        and current_or_last.is_upcoming
        and (next_game is None or next_game.event_id == current_or_last.event_id)
    ):
        next_game = current_or_last

    # After a final, prefer a distinct next upcoming game
    if (
        current_or_last
        and current_or_last.is_final
        and next_game
        and next_game.event_id == current_or_last.event_id
    ):
        upcoming = sorted(
            [g for g in games if g.status == "pre"],
            key=lambda g: g.start_time,
        )
        next_game = upcoming[0] if upcoming else None

    return TeamBoard(
        team_id=team.id,
        team_name=team.name,
        short_name=team.short_name,
        abbreviation=team.abbreviation,
        accent=team.accent,
        current_or_last=current_or_last,
        next_game=next_game,
    )


def fetch_board(cfg: AppConfig) -> BoardSnapshot:
    boards = [fetch_team_board(cfg, team) for team in cfg.teams]
    return BoardSnapshot(
        fetched_at=datetime.now(timezone.utc).isoformat(),
        boards=boards,
    )
