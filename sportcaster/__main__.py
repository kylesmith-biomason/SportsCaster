from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from .config import DEFAULT_CONFIG_PATH, load_config
from .display import Display, load_last_fingerprint, save_state
from .render import render_board
from .scores import fetch_board

logger = logging.getLogger("sportcaster")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_once(cfg, display: Display, force: bool = False) -> bool:
    """Fetch, compare, and maybe redraw. Returns True if any game is live."""
    snapshot = fetch_board(cfg)
    fingerprint = snapshot.fingerprint()
    previous = load_last_fingerprint(cfg.state_path)

    changed = force or previous != fingerprint
    if not changed:
        logger.info("No score/schedule changes; skipping e-paper refresh")
        return snapshot.any_live

    logger.info("State changed — rendering %d team panel(s)", len(snapshot.boards))
    for board in snapshot.boards:
        cur = board.current_or_last
        nxt = board.next_game
        logger.info(
            "%s: current=%s next=%s",
            board.short_name,
            None
            if cur is None
            else f"{cur.status} {cur.matchup_label()} {cur.short_detail}",
            None if nxt is None else f"{nxt.matchup_label()} @ {nxt.start_time}",
        )

    image = render_board(snapshot, cfg.timezone)
    display.show(image)
    save_state(cfg.state_path, fingerprint, snapshot.to_dict())
    return snapshot.any_live


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SportCaster e-paper scoreboard")
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Fetch and render once, then exit",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Redraw even if state is unchanged",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    cfg = load_config(args.config)
    display = Display(cfg)

    try:
        if args.once:
            run_once(cfg, display, force=args.force)
            return 0

        logger.info(
            "SportCaster running (live=%ss idle=%ss timezone=%s)",
            cfg.live_seconds,
            cfg.idle_seconds,
            cfg.timezone,
        )
        while True:
            try:
                live = run_once(cfg, display, force=args.force)
                args.force = False
                delay = cfg.live_seconds if live else cfg.idle_seconds
            except Exception:
                logger.exception("Update failed; backing off")
                delay = cfg.error_backoff_seconds
            logger.info("Sleeping %s seconds", delay)
            time.sleep(delay)
    except KeyboardInterrupt:
        logger.info("Interrupted")
        return 0
    finally:
        display.close()


if __name__ == "__main__":
    sys.exit(main())
