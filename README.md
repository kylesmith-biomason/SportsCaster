# SportCaster

E-paper scoreboard for a **Waveshare 7.3″ 7-color (F)** display on a Raspberry Pi 3.

Shows **Chicago Cubs** (MLB) and **Carolina Panthers** (NFL):

- Live scores while a game is in progress
- Final score plus **next opponent** and **game date/time** when idle
- Redraws the panel only when scores or schedule state change (~35s full refresh)

## Hardware

- Raspberry Pi 3 (or similar) with SPI enabled
- [Waveshare 7.3inch e-Paper HAT (F)](https://www.waveshare.com/wiki/7.3inch_e-Paper_HAT_(F)) (800×480, 7 colors)

Seat the HAT on the 40-pin header (or wire SPI per Waveshare docs).

## Raspberry Pi setup

```bash
sudo raspi-config
# Interface Options → SPI → Enable

sudo apt-get update
sudo apt-get install -y python3-venv python3-pip python3-pil python3-numpy \
  fonts-dejavu-core liblgpio-dev

cd ~
git clone https://github.com/kylesmith-biomason/SportsCaster.git
cd SportsCaster

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install spidev RPi.GPIO gpiozero   # Pi GPIO / SPI (skip on Mac)
```

Waveshare drivers are already under `vendor/waveshare_epd/` (`epd7in3f.py`, `epdconfig.py`).

### First run

```bash
cd ~/SportCaster
source .venv/bin/activate
python -m sportcaster --once --force -v
```

On a machine without the HAT (or when SPI isn’t available), SportCaster writes a preview PNG to `out/preview.png`.

### Run continuously / on boot

Edit `systemd/sportcaster.service` if your username or path isn’t `/home/pi/SportCaster`, then:

```bash
sudo cp systemd/sportcaster.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sportcaster
sudo systemctl status sportcaster
journalctl -u sportcaster -f
```

## Configuration

Edit [`config.yaml`](config.yaml):

| Key | Purpose |
| --- | --- |
| `timezone` | Local timezone for next-game times (default `America/Chicago`) |
| `display.mode` | `auto` (hardware then mock), `hardware`, or `mock` |
| `display.driver` | `epd7in3f` (HAT F) or swap to `epd7in3e` if you have HAT E |
| `poll.live_seconds` | Poll interval during live games (default 60) |
| `poll.idle_seconds` | Poll interval when no live game (default 900) |
| `teams` | Cubs / Panthers ESPN ids and accents |

## Development (Mac / without display)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install Pillow PyYAML requests
python -m sportcaster --once --force
open out/preview.png
```

## Notes

- Score data comes from ESPN’s public web JSON (`site.web.api.espn.com`). No API key. Be polite with polling; the defaults already throttle idle refreshes.
- 7-color ACeP panels only support full refreshes — avoid forcing redraws more often than needed.
- Team abbreviation for the Cubs is **CHC** (ESPN), not CHI.
