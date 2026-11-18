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
3. sets up 480i video, the same way as the main installer.
4. sets audio to the 3.5 mm jack.
5. creates the hotspot `RNS-AndroidAuto` (10.0.0.1) with a random password, on 5 GHz channel 36 by default (2.4 GHz is offered too). openauto reads the password from `/etc/hostapd/hostapd.conf`.
6. writes `/etc/openauto/openauto.ini`: 800×480 at 30 fps, touchscreen off, all buttons and the rotary knob enabled.
7. installs `rnsaa.service` (the MFD bridge) and turns off Kodi, the cursor and the tty1 login.

**First connection:** on the MFD select **TV**. On the phone, pair Bluetooth with the Pi. The phone then joins the hotspot by itself and Android Auto starts.
After that `rns-bt-reconnect.service` connects to the trusted phone automatically once openauto is ready. If the phone is connected over Bluetooth but no Android Auto session starts within 30 s, it disconnects and reconnects the phone.

## MFD buttons → Android Auto (default)
| MFD | short | long (> 0.4 s) |
|---|---|---|
| Knob turn | rotary scroll (Android Auto's native knob mode) | |
| Knob press / AS | select | Google Assistant |
| EXIT / 3 | back | home |
| ▲ / ▼ (5) | up / down | |
| ◀ / ▶ | previous / next track | left / right |
| SCAN / 6 | play / pause | navigation |
| 1 / 2 | answer call / end call | |

Change these in `/etc/rnsaa.conf`, then run `sudo systemctl restart rnsaa`.

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
| ← / → | knob turn | rotary scroll |
| ↑ / ↓ | ▲ / ▼ | up / down |
| Enter | knob press | select |
| Backspace | EXIT | back |
| v / h | long knob press / long EXIT | Google Assistant / home |
| , / . | ◀ / ▶ | previous / next track |
| < / > | long ◀ / ▶ | left / right |
| Space / n | SCAN / long SCAN | play-pause / navigation |
| 1 / 2 | 1 / 2 | answer / end call |
| q | quit | |

A USB keyboard plugged into the Pi also works directly in openauto: arrows, Enter = select, Esc = back, H = home.

## Logs
```bash
journalctl -u rnsaa -u openauto -u openauto-btservice -u rns-bt-reconnect -u hostapd -f
```

## Known limits
- **5 GHz hotspot:** if `hostapd` fails to start (`journalctl -u hostapd`), check the country code in `/etc/hostapd/hostapd.conf`. Then try removing `ieee80211ac=1`, or use another non-DFS channel such as 40, 44 or 48.
- **Video latency:** the installer patches openauto's video output (`openauto-patch/`). Stock openauto plays through QMediaPlayer, which lagged ~30 s behind and used ~175 % CPU on a 3B+. The patch pushes each frame through appsrc → h264parse → avdec_h264 (one thread) → appsink with `sync=false` and keeps only the newest frame, drawn with OpenGL. The Pi's hardware decoder (v4l2h264dec) is not used: it only releases a frame after several more arrive, which caused the lag. To try another decode chain without rebuilding, set `OPENAUTO_VIDEO_PIPELINE` in a drop-in of `openauto.service` (it must end in raw video, e.g. `h264parse ! v4l2h264dec ! videoconvert`).
- **Picture position:** if the picture is cut off or shifted, change the `margin_*` values in `cmdline.txt` (same as the main project), or `MarginWidth`/`MarginHeight` in `openauto.ini`.

## Tests (no hardware)
```bash
cd androidauto && python3 -m unittest discover tests
```
