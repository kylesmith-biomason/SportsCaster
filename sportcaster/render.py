from __future__ import annotations

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
LOGOS_DIR = ROOT / "assets" / "logos"

ACCENT_COLORS = {
    "blue": BLUE,
    "red": RED,
    "black": BLACK,
    "green": GREEN,
    "orange": ORANGE,
    "yellow": YELLOW,
}


def _font(size: int) -> ImageFont.ImageFont:
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


def _paste_content_logo(
    img: Image.Image,
    logo: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    """Scale logo to fill as much of box (left, top, right, bottom) as possible."""
    left, top, right, bottom = box
    max_w = max(1, right - left)
    max_h = max(1, bottom - top)
    scale = min(max_w / logo.width, max_h / logo.height)
    w = max(1, int(logo.width * scale))
    h = max(1, int(logo.height * scale))
    logo = logo.resize((w, h), Image.Resampling.LANCZOS)
    x = left + (max_w - w) // 2
    y = top + (max_h - h) // 2
    img.paste(logo, (x, y), logo)


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
    if board.accent == "black":
        title_fill = WHITE

    logo = _load_team_logo(board.team_id)
    pad_x = 28
    content_top = top + 60

    if logo is not None:
        # Title bar only on the left so the logo can use the full half-panel height
        bar_right = LOGO_LEFT - 12
        bar_fill = BLACK if board.accent == "black" else accent
        draw.rectangle((0, top, bar_right, top + HEADER_H), fill=bar_fill)
        if board.accent == "black":
            draw.rectangle((0, top + HEADER_H, bar_right, top + HEADER_H + 4), fill=BLUE)
        title_font = _fit_font(draw, title, bar_right - pad_x * 2, 28)
        tw, th = _text_size(draw, title, title_font)
        title_x = max(8, (bar_right - tw) // 2)
        draw.text((title_x, top + (HEADER_H - th) // 2 - 2), title, font=title_font, fill=title_fill)

        max_w = LOGO_LEFT - pad_x - 8
        _paste_content_logo(
            img,
            logo,
            (LOGO_LEFT, top + 4, WIDTH - 8, top + height - 4),
        )
    else:
        bar_fill = BLACK if board.accent == "black" else accent
        draw.rectangle((0, top, WIDTH, top + HEADER_H), fill=bar_fill)
        if board.accent == "black":
            draw.rectangle((0, top + HEADER_H, WIDTH, top + HEADER_H + 4), fill=BLUE)
        tw, th = _text_size(draw, title, title_font)
        draw.text(((WIDTH - tw) // 2, top + (HEADER_H - th) // 2 - 2), title, font=title_font, fill=title_fill)
        max_w = WIDTH - pad_x * 2

    current = board.current_or_last
    nxt = board.next_game

    # Primary content (left column when logo is present)
    if current and current.is_live:
        score = current.score_line(board.abbreviation)
        score_font = _fit_font(draw, score, max_w, 64)
        _, sh = _text_size(draw, score, score_font)
        draw.text((pad_x, content_top + 10), score, font=score_font, fill=BLACK)

        status = f"LIVE · {current.short_detail or current.detail}"
        status_font = _fit_font(draw, status, max_w, 26)
        draw.text((pad_x, content_top + 10 + sh + 16), status, font=status_font, fill=RED)

        if nxt and nxt.event_id != current.event_id:
            next_line = f"Next: {nxt.matchup_label()}"
            time_line = format_start_time(nxt.start_time, timezone)
            small = _fit_font(draw, next_line, max_w, 20)
            draw.text((pad_x, top + height - 56), next_line, font=small, fill=BLACK)
            draw.text((pad_x, top + height - 32), time_line, font=small, fill=BLACK)

    elif current and current.is_final and (nxt is None or nxt.event_id != current.event_id):
        # Final result large, next game below
        score = current.score_line(board.abbreviation)
        score_font = _fit_font(draw, score, max_w, 52)
        _, sh = _text_size(draw, score, score_font)
        draw.text((pad_x, content_top), score, font=score_font, fill=BLACK)
        draw.text((pad_x, content_top + sh + 8), "FINAL", font=_font(24), fill=BLACK)

        if nxt:
            matchup = nxt.matchup_label()
            when = format_start_time(nxt.start_time, timezone)
            m_font = _fit_font(draw, matchup, max_w, 36)
            draw.text((pad_x, content_top + sh + 48), matchup, font=m_font, fill=BLUE)
            draw.text((pad_x, content_top + sh + 92), when, font=_font(24), fill=BLACK)
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
            m_font = _fit_font(draw, matchup, max_w, 48)
            _, mh = _text_size(draw, matchup, m_font)
            draw.text((pad_x, content_top + 8), matchup, font=m_font, fill=BLUE)

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

    # Divider between halves
    if top == 0:
        draw.line((0, HALF - 1, WIDTH, HALF - 1), fill=BLACK, width=2)


def render_board(snapshot: BoardSnapshot, timezone: str) -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
    boards = snapshot.boards
    if not boards:
        draw = ImageDraw.Draw(img)
        draw.text((40, 200), "No teams configured", font=_font(36), fill=BLACK)
        return img

    # Support 1 or 2 teams (plan is two halves)
    if len(boards) == 1:
        _draw_team_panel(img, boards[0], 0, HEIGHT, timezone)
    else:
        _draw_team_panel(img, boards[0], 0, HALF, timezone)
        _draw_team_panel(img, boards[1], HALF, HALF, timezone)
        if len(boards) > 2:
            # Extra teams ignored on this panel size
            pass
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
