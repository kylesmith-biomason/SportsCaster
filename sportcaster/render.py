from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import ROOT
from .scores import BoardSnapshot, TeamBoard, format_start_time

# Waveshare 7.3" 7-color (F) palette — RGB values matching epd7in3f
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
ORANGE = (255, 128, 0)

WIDTH = 800
HEIGHT = 480
HALF = HEIGHT // 2
HEADER_H = 48
# Score text stays left of this; logos scale to fill the right box.
LOGO_LEFT = 340
LOGO_SCALE = 0.8  # fraction of the available right-hand box
OPP_LOGO_SIZE = 48  # opponent logo beside matchup text
OPP_LOGO_SIZE_NFL = int(OPP_LOGO_SIZE * 1.15 * 1.15 * 1.20)  # NFL logos larger than MLB
# Fit score text against this probe so MLB/NFL panels share one visual size
# (NFL scores are often two digits and would otherwise shrink more).
SCORE_WIDTH_PROBE = "WWW 99 - WWW 99"
SCORE_FONT_LIVE = 64
SCORE_FONT_FINAL = 52
LOGOS_DIR = ROOT / "assets" / "logos"
MLB_LOGOS_DIR = ROOT / "assets" / "mlb_logos"
NFL_LOGOS_DIR = ROOT / "assets" / "nfl_logos"

# Map ESPN-style abbreviations → files in assets/mlb_logos/{slug}.png
_MLB_LOGO_ALIASES = {
    "ari": "ari",
    "az": "ari",
    "atl": "atl",
    "bal": "bal",
    "bos": "bos",
    "chc": "chc",
    "cin": "cin",
    "cle": "cle",
    "col": "col",
    "cws": "cws",
    "chw": "cws",
    "det": "det",
    "hou": "hou",
    "kc": "kc",
    "kcr": "kc",
    "laa": "laa",
    "ana": "laa",
    "lad": "lad",
    "la": "lad",
    "mia": "mia",
    "fla": "mia",
    "mil": "mil",
    "min": "min",
    "nym": "nym",
    "nyy": "nyy",
    "oak": "oak",
    "ath": "oak",
    "phi": "phi",
    "pit": "pit",
    "sd": "sd",
    "sdp": "sd",
    "sea": "sea",
    "sf": "sf",
    "sfg": "sf",
    "stl": "stl",
    "tb": "tb",
    "tbr": "tb",
    "tex": "tex",
    "tor": "tor",
    "wsh": "wsh",
    "was": "wsh",
    "washington": "wsh",
}

# Map ESPN-style abbreviations → files in assets/nfl_logos/{slug}.png
_NFL_LOGO_ALIASES = {
    "ari": "ari",
    "atl": "atl",
    "bal": "bal",
    "buf": "buf",
    "car": "car",
    "chi": "chi",
    "cin": "cin",
    "cle": "cle",
    "dal": "dal",
    "den": "den",
    "det": "det",
    "gb": "gb",
    "gnb": "gb",
    "hou": "hou",
    "ind": "ind",
    "jax": "jax",
    "jac": "jax",
    "kc": "kc",
    "lac": "lac",
    "sd": "lac",
    "lar": "lar",
    "stl": "lar",
    "lv": "lv",
    "oak": "lv",
    "mia": "mia",
    "min": "min",
    "ne": "ne",
    "no": "no",
    "nyg": "nyg",
    "nyj": "nyj",
    "phi": "phi",
    "pit": "pit",
    "sea": "sea",
    "sf": "sf",
    "tb": "tb",
    "ten": "ten",
    "was": "was",
    "wsh": "was",
    "washington": "was",
}

ACCENT_COLORS = {
    "blue": BLUE,
    "red": RED,
    "black": BLACK,
    "green": GREEN,
    "orange": ORANGE,
    "yellow": YELLOW,
}


def _font(size: int) -> ImageFont.ImageFont:
    # Prefer Nunito Sans (Raspberry Pi OS ships a variable font under nunito-sans/)
    nunito_dir = Path("/usr/share/fonts/truetype/nunito-sans")
    if nunito_dir.is_dir():
        for path in sorted(nunito_dir.glob("NunitoSans-VariableFont*.ttf")):
            try:
                font = ImageFont.truetype(str(path), size=size)
                try:
                    font.set_variation_by_name("Bold")
                except (OSError, ValueError):
                    pass
                return font
            except OSError:
                continue
        for path in sorted(nunito_dir.glob("NunitoSans*Bold*.ttf")):
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, preferred: int) -> ImageFont.ImageFont:
    size = preferred
    while size >= 14:
        font = _font(size)
        w, _ = _text_size(draw, text, font)
        if w <= max_width:
            return font
        size -= 2
    return _font(14)


def _load_team_logo(team_id: str) -> Image.Image | None:
    """Load assets/logos/{team_id}.png (also tries .jpg / .webp), cropped to content."""
    for ext in (".png", ".PNG", ".jpg", ".jpeg", ".webp"):
        path = LOGOS_DIR / f"{team_id}{ext}"
        if path.is_file():
            try:
                logo = Image.open(path).convert("RGBA")
            except OSError:
                return None
            bbox = logo.getbbox()
            if bbox:
                logo = logo.crop(bbox)
            return logo
    return None


def _load_league_logo(
    abbreviation: str,
    logos_dir,
    aliases: dict[str, str],
) -> Image.Image | None:
    """Load a league opponent logo by ESPN abbreviation from a logos directory."""
    key = abbreviation.strip().lower()
    slug = aliases.get(key, key)
    path = logos_dir / f"{slug}.png"
    if not path.is_file():
        return None
    try:
        logo = Image.open(path).convert("RGBA")
    except OSError:
        return None
    bbox = logo.getbbox()
    if bbox:
        logo = logo.crop(bbox)
    return logo


def _load_opponent_logo(abbreviation: str, sport: str) -> Image.Image | None:
    """Load MLB or NFL opponent logo based on the followed team's sport."""
    sport_key = (sport or "").strip().lower()
    if sport_key in ("baseball", "mlb"):
        return _load_league_logo(abbreviation, MLB_LOGOS_DIR, _MLB_LOGO_ALIASES)
    if sport_key in ("football", "nfl"):
        return _load_league_logo(abbreviation, NFL_LOGOS_DIR, _NFL_LOGO_ALIASES)
    # Fallback: try both (NFL first only if abbr looks exclusive — prefer MLB then NFL)
    return _load_league_logo(abbreviation, MLB_LOGOS_DIR, _MLB_LOGO_ALIASES) or _load_league_logo(
        abbreviation, NFL_LOGOS_DIR, _NFL_LOGO_ALIASES
    )


def _paste_content_logo(
    img: Image.Image,
    logo: Image.Image,
    box: tuple[int, int, int, int],
    scale_factor: float = LOGO_SCALE,
) -> None:
    """Scale logo to fill as much of box (left, top, right, bottom) as possible."""
    left, top, right, bottom = box
    max_w = max(1, right - left)
    max_h = max(1, bottom - top)
    scale = min(max_w / logo.width, max_h / logo.height) * scale_factor
    w = max(1, int(logo.width * scale))
    h = max(1, int(logo.height * scale))
    logo = logo.resize((w, h), Image.Resampling.LANCZOS)
    x = left + (max_w - w) // 2
    y = top + (max_h - h) // 2
    img.paste(logo, (x, y), logo)


def _draw_matchup_with_logo(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    matchup: str,
    opponent_abbr: str,
    sport: str,
    x: int,
    y: int,
    max_w: int,
    preferred_font: int,
    fill: tuple[int, int, int],
) -> int:
    """Draw matchup text with opponent logo beside it; return total height used."""
    opp_logo = _load_opponent_logo(opponent_abbr, sport)
    sport_key = (sport or "").strip().lower()
    logo_size = OPP_LOGO_SIZE_NFL if sport_key in ("football", "nfl") else OPP_LOGO_SIZE
    logo_w = 0
    gap = 10
    if opp_logo is not None:
        logo_w = logo_size + gap

    text_max = max(40, max_w - logo_w)
    font = _fit_font(draw, matchup, text_max, preferred_font)
    tw, th = _text_size(draw, matchup, font)
    draw.text((x, y), matchup, font=font, fill=fill)

    row_h = th
    if opp_logo is not None:
        scale = min(logo_size / opp_logo.width, logo_size / opp_logo.height)
        rw = max(1, int(opp_logo.width * scale))
        rh = max(1, int(opp_logo.height * scale))
        scaled = opp_logo.resize((rw, rh), Image.Resampling.LANCZOS)
        lx = x + tw + gap
        ly = y + (max(th, rh) - rh) // 2
        img.paste(scaled, (lx, ly), scaled)
        row_h = max(th, rh)
    return row_h


def _draw_team_panel(
    img: Image.Image,
    board: TeamBoard,
    top: int,
    height: int,
    timezone: str,
) -> None:
    draw = ImageDraw.Draw(img)
    accent = ACCENT_COLORS.get(board.accent, BLUE)
    title_font = _font(28)
    title = board.team_name.upper()
    # Use white text on colored bars; black on yellow/orange for contrast
    title_fill = BLACK if board.accent in ("yellow", "orange") else WHITE
    bar_fill = BLACK if board.accent == "black" else accent
    if board.accent == "black":
        title_fill = WHITE

    # Full-width team name banner
    draw.rectangle((0, top, WIDTH, top + HEADER_H), fill=bar_fill)
    if board.accent == "black":
        draw.rectangle((0, top + HEADER_H, WIDTH, top + HEADER_H + 4), fill=BLUE)
    elif board.accent == "blue":
        draw.rectangle((0, top + HEADER_H, WIDTH, top + HEADER_H + 4), fill=RED)
    tw, th = _text_size(draw, title, title_font)
    draw.text(((WIDTH - tw) // 2, top + (HEADER_H - th) // 2 - 2), title, font=title_font, fill=title_fill)

    logo = _load_team_logo(board.team_id)
    pad_x = 28
    content_top = top + 60

    if logo is not None:
        max_w = LOGO_LEFT - pad_x - 8
        _paste_content_logo(
            img,
            logo,
            (LOGO_LEFT, top + HEADER_H + 6, WIDTH - 8, top + height - 6),
        )
    else:
        max_w = WIDTH - pad_x * 2

    current = board.current_or_last
    nxt = board.next_game

    # Primary content (left column when logo is present)
    full_page = height >= HEIGHT
    if current and current.is_live:
        score = current.score_line(board.abbreviation)
        live_pref = 80 if full_page else SCORE_FONT_LIVE
        score_font = _fit_font(draw, SCORE_WIDTH_PROBE, max_w, live_pref)
        _, sh = _text_size(draw, score, score_font)
        draw.text((pad_x, content_top + 10), score, font=score_font, fill=BLACK)

        status = f"LIVE · {current.short_detail or current.detail}"
        status_font = _fit_font(draw, status, max_w, 32 if full_page else 26)
        status_y = content_top + 10 + sh + 16
        draw.text((pad_x, status_y), status, font=status_font, fill=RED)
        _, status_h = _text_size(draw, status, status_font)

        if nxt and nxt.event_id != current.event_id:
            # Same next-game style as Final state (matchup + logo, then date)
            matchup = nxt.matchup_label()
            when = format_start_time(nxt.start_time, timezone)
            matchup_y = status_y + status_h + 24
            mh = _draw_matchup_with_logo(
                img,
                draw,
                matchup,
                nxt.opponent.abbreviation,
                board.sport,
                pad_x,
                matchup_y,
                max_w,
                42 if full_page else 36,
                BLUE,
            )
            draw.text(
                (pad_x, matchup_y + mh + 8),
                when,
                font=_font(28 if full_page else 24),
                fill=BLACK,
            )

    elif current and current.is_final and (nxt is None or nxt.event_id != current.event_id):
        # Final result large, next game below
        score = current.score_line(board.abbreviation)
        score_font = _fit_font(draw, SCORE_WIDTH_PROBE, max_w, SCORE_FONT_FINAL)
        _, sh = _text_size(draw, score, score_font)
        draw.text((pad_x, content_top), score, font=score_font, fill=BLACK)
        draw.text((pad_x, content_top + sh + 8), "FINAL", font=_font(24), fill=BLACK)

        if nxt:
            matchup = nxt.matchup_label()
            when = format_start_time(nxt.start_time, timezone)
            matchup_y = content_top + sh + 48
            mh = _draw_matchup_with_logo(
                img,
                draw,
                matchup,
                nxt.opponent.abbreviation,
                board.sport,
                pad_x,
                matchup_y,
                max_w,
                36,
                BLUE,
            )
            draw.text((pad_x, matchup_y + mh + 8), when, font=_font(24), fill=BLACK)
        else:
            draw.text(
                (pad_x, content_top + sh + 48),
                "No upcoming game scheduled",
                font=_font(22),
                fill=BLACK,
            )

    else:
        # Upcoming / idle: emphasize next opponent + time
        focus = nxt or current
        if focus is None:
            draw.text((pad_x, content_top + 40), "No games found", font=_font(28), fill=BLACK)
        else:
            matchup = focus.matchup_label()
            when = format_start_time(focus.start_time, timezone)
            mh = _draw_matchup_with_logo(
                img,
                draw,
                matchup,
                focus.opponent.abbreviation,
                board.sport,
                pad_x,
                content_top + 8,
                max_w,
                48,
                BLUE,
            )
            t_font = _fit_font(draw, when, max_w, 32)
            draw.text((pad_x, content_top + 8 + mh + 18), when, font=t_font, fill=BLACK)

            # If we have a distinct last final, show it small
            if (
                current
                and current.is_final
                and current.event_id != focus.event_id
            ):
                last = current.result_line(board.abbreviation)
                draw.text((pad_x, top + height - 36), last, font=_font(20), fill=BLACK)
            elif focus.is_upcoming:
                draw.text(
                    (pad_x, top + height - 36),
                    "UPCOMING",
                    font=_font(20),
                    fill=ORANGE,
                )

    # Divider between halves (split layout only)
    if top == 0 and height == HALF:
        draw.line((0, HALF - 1, WIDTH, HALF - 1), fill=BLACK, width=2)


def _live_focus_board(boards: list[TeamBoard]) -> TeamBoard | None:
    """Return the board that should take the full page while live.

    Prefers Cubs when multiple games are live; otherwise the first live board.
    """
    live = [b for b in boards if b.is_live]
    if not live:
        return None
    for board in live:
        if board.team_id == "cubs":
            return board
    return live[0]


def render_board(snapshot: BoardSnapshot, timezone: str) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    boards = snapshot.boards
    if not boards:
        draw = ImageDraw.Draw(img)
        draw.text((40, 200), "No teams configured", font=_font(36), fill=BLACK)
        return img

    live = _live_focus_board(boards)
    if live is not None:
        # Full-page live view (Cubs wins if both are live)
        _draw_team_panel(img, live, 0, HEIGHT, timezone)
        return img

    # Idle / final: one team full page, or two-team split
    if len(boards) == 1:
        _draw_team_panel(img, boards[0], 0, HEIGHT, timezone)
    else:
        _draw_team_panel(img, boards[0], 0, HALF, timezone)
        _draw_team_panel(img, boards[1], HALF, HALF, timezone)
    return img


def quantize_for_epd(img: Image.Image) -> Image.Image:
    """Map image colors onto the 7-color ACeP palette."""
    palette_colors = [BLACK, WHITE, GREEN, BLUE, RED, YELLOW, ORANGE]
    palette_img = Image.new("P", (1, 1))
    flat: list[int] = []
    for rgb in palette_colors:
        flat.extend(rgb)
    flat.extend([0] * (768 - len(flat)))
    palette_img.putpalette(flat)
    return img.convert("RGB").quantize(palette=palette_img, dither=Image.Dither.NONE).convert("RGB")
