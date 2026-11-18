# RNS-MFD1 wireless Android Auto: project context

Fork of maltsevvv "RNSPI" (Kodi skin + installer for VAG RNS, Unlicense / public domain).
The user's goal: a Raspberry Pi **3B+** that gives a VW **RNS-MFD (MFD1)** wireless Android Auto **without a dongle**:
- video into the MFD's TV input
- audio from the Pi's **3.5 mm jack** into the MFD TV audio input
- the MFD's own buttons control Android Auto

Default country code: **LT** (Lithuania).

## History / decisions (don't re-litigate)
- **CarPlay is not possible without a dongle.** It needs an Apple MFi auth chip, and react-carplay / node-carplay need a Carlinkit CPC200 dongle. A first `carplay/` folder was built, then deleted.
- **DiPlay** (shihabal3amri/DiPlay) was reviewed and rejected:
  - it's an Android APK for BYD head units, with no Pi/Linux support;
  - it uses an auth identity extracted from Carlinkit firmware, which has legal problems and can be revoked by any iOS update.
- **Current direction:** `androidauto/` on **opencardev/openauto + aasdk**. These support true wireless Android Auto: a btservice does the Bluetooth handshake, and a hostapd hotspot carries the session.
- For iPhone, the only realistic option is a Carlinkit dongle as a second mode. Not built.

## Layout
- `install.sh`, `driver/`, `kodi20|21/`: the original RNSPI project. **Don't change it**; only reuse its helper style (green/red, rpi_vga, rpi_composite, rpi_audio).
- `README.md` (root): the original README, plus an appended section "RNS-MFD1 wireless Android Auto setup" (TOC item 9).
- `androidauto/`:
  - `install.sh`: installer for Pi OS Lite **trixie** (aasdk only supports trixie).
  - `rnsaa/`: Python MFD bridge.
    - `mfd.py`: CAN tuner emulation + button decoding.
    - `keys.py`: uinput virtual keyboard.
    - `config.py`: default button map and config loading.
    - `__main__.py`: CLI; `--learn` prints raw frames and decoded buttons.
  - `rnsaa.conf` → `/etc/rnsaa.conf`; `rnsaa.service` (WorkingDirectory=/opt/rnsaa).
  - `openauto.ini` → `/etc/openauto/openauto.ini`. openauto reads the ini from its working directory, which a drop-in sets.
  - `tests/test_rnsaa.py`: run with `cd androidauto && python3 -m unittest discover tests`. 10 tests, all passing.
  - `README.md`: the androidauto guide.

## MFD CAN protocol
Recovered from the skin's compiled control.pyc. 100 kbit infotainment CAN, MCP2515 as can0.
- **IDs:** the MFD sends on **0x464**; the emulated TV tuner replies on **0x264**.
- **Handshake replies:**
  - E00100 → E00100 (resets the counter)
  - A300 → E101
  - E101 → 10150100020000, then `{0x10+c}270200`
- **Ack:** any other frame longer than 1 byte gets `((d0+1)&0xF)+0xB0`.
- **Extra replies** (each increments the counter):
  - 3-byte frame `xx0001` → `{0x10+c}0101`
  - 3-byte frame `xx0002` → `{0x10+c}0102`
  - 4-byte frame `xx08..` → `{0x20+c}090142500231`
- **Buttons:** `[seq] 20 [01 press|02 release] [code16]`.
  - Encoder: `0100FF` = left, `0101FF` = right.
  - Codes: 0005/0300 ok, 0020 up, 0010 down, 0400 prev, 0500 next, 0040/2000 exit, 3000/0002 scan, 0200 key1, 0100 key2.
  - Long vs short press is decided on release (> 0.4 s = long).
  - Buttons are only sent while the MFD is in TV mode.

## Buttons → openauto keys
openauto's InputDevice; every `[Input]` button must be set `true` in openauto.ini.
- 1/2 = rotary left/right
- Enter = select, Esc = back, H = home, arrows = DPAD
- B = play/pause, N = next, V = prev, X = play, C = pause
- M = assistant, F = navigation, P = call, O = end call

Default MFD map:

| MFD button | short | long |
|---|---|---|
| knob turn | rotary | |
| ok | select | voice |
| exit | back | home |
| up / down | up / down | |
| prev | prev | left |
| next | next | right |
| scan | play_pause | navigation |
| key1 | call | |
| key2 | end_call | |

## Pi setup (androidauto/install.sh)
- **Pinned commits:** AASDK_REF / OPENAUTO_REF, built in /opt/openauto-build with a temporary 2 GB swap. The build is skipped if `autoapp` and `btservice` already exist, so reruns are fast.
- **can0:** MCP2515 (8 or 16 MHz crystal), interrupt GPIO25.
- **Video:**
  - HDMI-VGA 480i: `video=HDMI-A-1:NTSC,margin_*` + `drm.edid_firmware=HDMI-A-1:rpi480i.bin`, `vc4-kms-v3d,noaudio`.
  - or composite: `video=Composite-1:720x480@60ie`, `vc4.tv_norm=NTSC`, `enable_tvout=1`. The Pi 3B+ jack is TRRS (audio + composite).
- **Audio:** ALSA dmix on hw:Headphones.
- **Hotspot:** hostapd SSID `RNS-AndroidAuto`, 10.0.0.1/24.
  - systemd-networkd DHCPServer; NetworkManager is told wlan0 is unmanaged.
  - 5 GHz ch36 by default, 2.4 GHz optional; random 16-char password.
  - `cfg80211.ieee80211_regdom=LT` on the cmdline.
  - btservice reads ssid/pass from hostapd.conf.
- **configure_bluetooth** (added during debugging):
  - installs bluez-firmware, bluez-tools, pi-bluetooth; enables hciuart;
  - removes any disable-bt overlay;
  - main.conf: AutoEnable, DiscoverableTimeout 0, AlwaysPairable, JustWorksRepairing always;
  - `/usr/local/bin/rns-bt-ready` (ExecStartPre of the btservice drop-in): waits for hci0, unblocks, powers on, writes AdapterAddress into openauto.ini;
  - `rns-bt-agent.service` runs `bt-agent --capability=NoInputNoOutput`. btservice registers **no pairing agent**, which gave the phone "incorrect PIN".
- **Other:** rnsaa installed in /opt/rnsaa; uinput added to /etc/modules; Kodi, the tty1 getty and the cursor are disabled.

## Current status (2026-11-18), debugging on the user's Pi (hostname `malina`)
- Phone ↔ Pi Bluetooth pairing works, after adding the bt-agent.
- hostapd is running (AP-ENABLED).
- btservice is healthy: adapter B8:27:EB:F3:0E:72, profile 4de17a00-52cb-11e6-bdf4-0800200c9a66 registered on RFCOMM port 1.
- Fixed since: `ControllerMode = bredr` (connect had tried LE), `Class = 0x200408`, and bluez-alsa running as `bluealsa -S -p hfp-hf -p hsp-hs`. Without a hands-free profile, `bluetoothctl connect` failed with br-connection-profile-unavailable and the phone never opened the Android Auto RFCOMM. All of these are now in the installer.
- The phone now says "Android Auto connected", but the screen is white. Then "select Android Auto on your vehicle screen", and after about 10 s `TCP_TRANSFER` (33) / eof: the phone hangs up. No "Initial buffering complete", so no video data arrived.
- **Cause found:** `RtAudioOutput: No output devices found`. RtAudio prefers PulseAudio, which Pi OS Lite doesn't run. Fix: `[Audio] OutputBackendType=1` (Qt/ALSA), now in openauto.ini. Waiting on the user's retest; if the screen is still white, check the H.264 decoders with `gst-inspect-1.0` (v4l2h264dec vs avdec_h264).
- The user is testing on a regular HDMI monitor: the 480i cmdline/config entries were removed, with backups in `cmdline.txt.mfd` / `config.txt.mfd`; a USB keyboard stands in for the MFD buttons.
- Nothing has been tested on the MFD itself yet.
- The `androidauto/install.sh` Bluetooth changes are **uncommitted**: the Pi can't `git pull` them, so fixes have been given as manual commands. Commit d87a3b1 "android auto mode" holds the earlier work.

## Notes for working with the user
- The user pastes multi-command text literally. Give each command on its own line or in its own code block, never joined with "and".
- Pi user `malina`; Pi OS trixie with `/boot/firmware/`.
- Commit or push only when asked.

### Update: video works, fixing audio
- `OutputBackendType=1` worked: the session stays up, the Android Auto screen shows on the monitor, and the phone says connected.
- The jack is silent. `speaker-test -D plughw:Headphones` plays, but `-D default` (dmix) hangs: dmix picked period 6000 / buffer 18000 and stalls on bcm2835. Explicit `period_size`/`buffer_size` didn't help, so dmix is dropped: asound.conf is now just `plug` → `hw:Headphones` (bcm2835 has 8 hardware subdevices, so streams play together without dmix).
- Qt 5 prefers `libqtmedia_pulse.so`, and no PulseAudio runs, so the installer now moves it aside with `dpkg-divert` (to `.disabled`). Both fixes are in install.sh `rpi_audio_jack`. Waiting on the retest.
- Next audio finding: Qt (alsa plugin) creates the outputs but opens nothing on card0. Qt5 picks the first entry from ALSA's name hints, and a `pcm.!default` without `hint { show on }` isn't listed, so it probably went to vc4hdmi (card1, back on during the monitor test because `noaudio` was removed). Fix: add a `hint` block to asound.conf (now in the installer). Waiting on the retest.
- Real cause: Qt5 alsa uses the FIRST device in `aplay -L` (skipping null), which was `bluealsa` (added by bluez-alsa-utils via /etc/alsa/conf.d/20-bluealsa.conf). The installer now removes that link (the bluealsa daemon for HFP keeps running). The `hint` block keeps `default` (3.5 mm jack) listed.
- Qt audio still never opened /dev/snd (no fd, no ALSA error; the log has "PulseAudioService: pa_context_connect() failed"). **Switched to plan B:** a system-wide PulseAudio (`pulseaudio-system.service`, system.pa = alsa-sink hw:Headphones `sink_name=jack` + native-protocol-unix `auth-anonymous=1`), openauto `PULSE_SERVER=unix:/run/pulse/native`, `OutputBackendType=0` (RtAudio). Per-user pulseaudio is disabled globally. The Qt pulse-plugin dpkg-divert was removed from the installer. Waiting on the test.
- Restarting only openauto leaves the phone saying "press Android Auto button in car". Reboot, or restart openauto + openauto-btservice and do bluetoothctl disconnect/connect.
- **2026-11-18: audio WORKS** (Spotify through the jack) with plan B: system PulseAudio + RtAudio. The video and the Android Auto session work on the HDMI monitor. On the Pi there's a leftover manual dpkg-divert of `libqtmedia_pulse.so` (harmless). Next: commit, go back to the MFD video config (`cmdline.txt.mfd` / `config.txt.mfd`), test the MFD buttons over CAN (`--learn`), (auto-reconnect added: `rns-bt-reconnect` + `.service`, which connects the first trusted phone every 15 s while none is connected).
- Added `python3 -m rnsaa --keyboard` (rnsaa/terminal.py): SSH terminal keys become MFD (button, kind) events through the normal [buttons] map (←/→ knob, ↑/↓, Enter ok, Backspace exit, v/h long, ,/. prev/next, </> long, Space/n scan, 1/2 call). 13 tests.
