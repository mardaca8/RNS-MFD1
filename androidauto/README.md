# RNS-MFD1 wireless Android Auto (Raspberry Pi 3B+, no dongle)

Wireless Android Auto on the VW **RNS-MFD (MFD1)**, using the MFD's TV input and the MFD's own buttons.
- **Android Auto head unit:** [opencardev/openauto](https://github.com/opencardev/openauto) and [aasdk](https://github.com/opencardev/aasdk). openauto has its own Bluetooth service and a Wi-Fi hotspot handshake, so no dongle is needed.
- **MFD side** (this folder): TV-tuner emulation on CAN, plus a virtual keyboard that sends the MFD buttons to openauto.

```
 Android phone ──Bluetooth (pairing + Wi-Fi handshake)──┐
               ──Wi-Fi hotspot "RNS-AndroidAuto"────────┤ Raspberry Pi 3B+
                                                        │  openauto ──HDMI-VGA or composite──> MFD TV video in
                                                        │       └────3.5 mm jack (audio)─────> MFD TV audio in
                                                        │  rnsaa ◄──MCP2515 / CAN 100k──────── MFD buttons
                                                        │    └─ virtual keyboard ─> openauto     (+ TV-tuner emulation)
```

## Hardware
| Part | Notes |
|---|---|
| Raspberry Pi 3B+ | **Raspberry Pi OS Lite trixie**: aasdk's build only supports trixie. The built-in dual-band Wi-Fi (5 GHz hotspot) and Bluetooth are used. |
| MCP2515 + SN65HVD230 CAN module | Wired as **CAN0** in the [main README](../README.md#raspberry-PI-connect-modules) |
| Video: HDMI→VGA adapter **or** a 3.5 mm TRRS breakout | Same options as the main project. The Pi 3B+ jack carries audio L/R **and** composite video. |
| 3.5 mm jack → MFD TV audio L/R/GND | Use a **ground-loop isolator** |
| Optional USB microphone | Needed for Google Assistant and calls |
| Phone | Android 11 or newer, with wireless Android Auto |

## Install
The Pi needs internet during the install. Use Ethernet: wlan0 becomes the hotspot.
```bash
sudo apt install -y git
git clone https://github.com/maltsevvv/repository.git
sudo bash repository/androidauto/install.sh
```
The installer:
1. builds and installs aasdk and openauto, pinned to tested commits. This takes **1–3 hours** on a 3B+ and uses a temporary 2 GB swap file.
2. sets up `can0` at 100 kbit.
3. sets up 480i video. With the HDMI→VGA adapter it uses `driver/rpi480i27.bin` (480i with each pixel sent twice, 27 MHz on HDMI), because adapters don't lock onto the 13.5 MHz the main installer uses.
4. sets audio to the 3.5 mm jack.
5. creates the hotspot `RNS-AndroidAuto` (10.0.0.1) with a random password, on 5 GHz channel 36 by default (2.4 GHz is offered too). openauto reads the password from `/etc/hostapd/hostapd.conf`.
6. writes `/etc/openauto/openauto.ini`: 800×480 at 30 fps, touchscreen off, all buttons and the rotary knob enabled.
7. installs `rnsaa.service` (the MFD bridge) and turns off Kodi, the cursor and the tty1 login.

**First connection:** on the MFD select **TV**. On the phone, pair Bluetooth with the Pi. The phone then joins the hotspot by itself and Android Auto starts.
After that `rns-bt-reconnect.service` connects to the trusted phone automatically once openauto is ready. If the phone is connected over Bluetooth but no Android Auto session starts within 30 s, it disconnects and reconnects the phone.

## MFD buttons → Android Auto (default)
| MFD | short | long (> 0.4 s) |
|---|---|---|
| Right knob turn | rotary scroll (Android Auto's native knob mode) | |
| Right knob press | select | Google Assistant |
| Arrow button next to NAVI | back | home |
| AS | Google Assistant | |
| SCAN | play / pause | navigation |
| ◁ / ▷ (top left) | previous / next track | left / right |
| 1 / 2 / 3 | answer call / end call / home | |
| 4 / 5 / 6 | up / down / navigation | |

The preset keys 1–6 send only a press (no release), so they have no long press.
NAVI, AUDIO, ♪, INFO, TIM, ↩, ⚑ and the left knob (volume, power) stay with the RNS.

Change these in `/etc/rnsaa.conf`, then run `sudo systemctl restart rnsaa`.

## Text on the instrument cluster
The cluster shows `ANDROID` / `AUTO` in place of TV/VIDEO. rnsaa sends it on CAN the same way the Kodi skin does (0x265 / 0x267, plus 0x665 to activate the display).
Change the lines with `fis_line1` / `fis_line2` (8 characters each), or turn it off with `fis = false`, in `/etc/rnsaa.conf`.

With `fis_nowplaying = true` it shows the artist (line 1) and song (line 2) while music plays instead; longer text scrolls. The patched openauto writes what the phone plays to `/dev/shm/openauto-nowplaying`.

## Checking the buttons
```bash
sudo systemctl stop rnsaa
cd /opt/rnsaa && sudo python3 -m rnsaa --learn
```
Switch the MFD to TV and press buttons. Each raw `464#...` frame is printed, with the decoded button below it.

## Testing without the MFD (keyboard over SSH)
```bash
cd /opt/rnsaa && sudo python3 -m rnsaa --keyboard
```
Keys typed in this terminal act as MFD buttons. They go through the same `[buttons]` mapping as the real ones, so this also tests `/etc/rnsaa.conf`. No CAN module needed.

| Key | MFD button | Android Auto (default) |
|---|---|---|
| ← / → | right knob turn | rotary scroll |
| Enter | right knob press | select |
| Backspace | arrow next to NAVI | back |
| v / h | long knob press / long arrow | Google Assistant / home |
| a | AS | Google Assistant |
| , / . | ◁ / ▷ | previous / next track |
| < / > | long ◁ / ▷ | left / right |
| Space / n | SCAN / long SCAN | play-pause / navigation |
| 1 … 6 (↑ / ↓ = 4 / 5) | preset keys | call / end call / home / up / down / navigation |
| q | quit | |

A USB keyboard plugged into the Pi also works directly in openauto: arrows, Enter = select, Esc = back, H = home.

## Logs
```bash
journalctl -u rnsaa -u openauto -u openauto-btservice -u rns-bt-reconnect -u hostapd -f
```

## Known limits
- **5 GHz hotspot:** if `hostapd` fails to start (`journalctl -u hostapd`), check the country code in `/etc/hostapd/hostapd.conf`. Then try removing `ieee80211ac=1`, or use another non-DFS channel such as 40, 44 or 48.
- **Video latency:** the installer patches openauto's video output (`openauto-patch/`). Stock openauto plays through QMediaPlayer, which lagged ~30 s behind and used ~175 % CPU on a 3B+. The patch pushes each frame through appsrc → h264parse → avdec_h264 (one thread) → appsink with `sync=false` and keeps only the newest frame, drawn with OpenGL. The Pi's hardware decoder (v4l2h264dec) is not used: it only releases a frame after several more arrive, which caused the lag. To try another decode chain without rebuilding, set `OPENAUTO_VIDEO_PIPELINE` in a drop-in of `openauto.service` (it must end in raw video, e.g. `h264parse ! v4l2h264dec ! videoconvert`).
- **Black MFD screen with a racing line (HDMI→VGA):** the adapter isn't locking onto the HDMI signal. `cat /proc/cmdline` must contain `video=HDMI-A-1:720x480@60i` and `drm.edid_firmware=HDMI-A-1:rpi480i27.bin`. Check with `sudo grep -h 'mode: "[0-9]' /sys/kernel/debug/dri/*/state`: the mode must be `720x480i` ending in `0x101a` (0x1000 = pixel doubling).
- **Picture position:** if the picture is cut off or shifted, change the `margin_*` values in `cmdline.txt` (same as the main project), or `MarginWidth`/`MarginHeight` in `openauto.ini`.

## Tests (no hardware)
```bash
cd androidauto && python3 -m unittest discover tests
```
