from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from PIL import Image

from .config import AppConfig, ROOT
from .render import quantize_for_epd

logger = logging.getLogger(__name__)


def load_last_fingerprint(path: Path) -> list[dict[str, Any]] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("fingerprint")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def save_state(path: Path, fingerprint: list[dict[str, Any]], snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"fingerprint": fingerprint, "snapshot": snapshot}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class Display:
    """Thin wrapper around Waveshare epd7in3f with mock/PNG fallback."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self._epd = None
        self.mode = cfg.display_mode
        self._init_backend()

    def _init_backend(self) -> None:
        mode = self.cfg.display_mode
        if mode == "mock":
            logger.info("Display mode=mock → writing PNG previews")
            return

        if mode == "auto" and not self._looks_like_pi():
            logger.info("Not on Raspberry Pi; using mock PNG output")
            self.mode = "mock"
            return

        if mode in ("hardware", "auto"):
            try:
                self._epd = self._load_epd(self.cfg.driver)
                self._epd.init()
                self.mode = "hardware"
                logger.info("Initialized Waveshare driver %s", self.cfg.driver)
                return
            except Exception as exc:  # noqa: BLE001 — hardware optional on dev machines
                if mode == "hardware":
                    raise
                logger.warning(
                    "Hardware display unavailable (%s); falling back to mock PNG",
                    exc,
                )
                self.mode = "mock"

    @staticmethod
    def _looks_like_pi() -> bool:
        if Path("/proc/device-tree/model").exists():
            try:
                model = Path("/proc/device-tree/model").read_text(errors="ignore")
                return "Raspberry Pi" in model
            except OSError:
                return False
        return Path("/proc/cpuinfo").exists() and sys.platform.startswith("linux")

    def _load_epd(self, driver: str):
        vendor = ROOT / "vendor"
        if str(vendor) not in sys.path:
            sys.path.insert(0, str(vendor))
        if driver == "epd7in3f":
            from waveshare_epd import epd7in3f  # type: ignore

            return epd7in3f.EPD()
        if driver == "epd7in3e":
            from waveshare_epd import epd7in3e  # type: ignore

            return epd7in3e.EPD()
        raise ValueError(f"Unsupported display driver: {driver}")

    def show(self, image: Image.Image) -> None:
        prepared = quantize_for_epd(image)
        if self.mode == "mock" or self._epd is None:
            out = self.cfg.mock_path
            out.parent.mkdir(parents=True, exist_ok=True)
            prepared.save(out)
            logger.info("Wrote mock preview to %s", out)
            return

        # Waveshare expects an image matching panel size
        if prepared.size != (self._epd.width, self._epd.height):
            prepared = prepared.resize((self._epd.width, self._epd.height))
        logger.info("Refreshing e-paper (full refresh)…")
        self._epd.display(self._epd.getbuffer(prepared))
        logger.info("E-paper refresh complete")

    def sleep(self) -> None:
        if self._epd is not None and self.mode == "hardware":
            try:
                self._epd.sleep()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Display sleep failed: %s", exc)

    def close(self) -> None:
        self.sleep()
        if self._epd is not None:
            try:
                from waveshare_epd import epdconfig  # type: ignore

                epdconfig.module_exit()
            except Exception:  # noqa: BLE001
                pass
