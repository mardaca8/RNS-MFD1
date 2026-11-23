"""Song text on the instrument cluster (FIS), the way skin.rnspi's sendcan does it.

openauto (patched MediaPlaybackStatusService) writes what the phone plays to NOWPLAYING_FILE.
While something plays, the two 8-character radio lines are sent every second:
  0x265  line 1 (artist)       0x267  line 2 (song)       0x665  6F200000300020  (FIS activation)
Longer text scrolls one character per second. When nothing plays, nothing is sent and the
RNS's own text (TV/VIDEO) comes back.
"""
import logging
import threading
import unicodedata

log = logging.getLogger(__name__)

NOWPLAYING_FILE = "/dev/shm/openauto-nowplaying"
LINE1_ID = 0x265
LINE2_ID = 0x267
ACTIVATION_ID = 0x665
ACTIVATION = bytes.fromhex("6F200000300020")
WIDTH = 8
INTERVAL = 1.0
HOLD = 2  # ticks the start of a scrolling line stays still


def read_nowplaying(path=NOWPLAYING_FILE):
    """key=value lines -> dict; empty dict if openauto has written nothing yet."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return dict(line.rstrip("\n").split("=", 1) for line in f if "=" in line)
    except OSError:
        return {}


def to_fis(text):
    """Upper case ASCII the cluster can show; accents dropped (Ž -> Z), anything else -> space."""
    text = unicodedata.normalize("NFKD", text.upper())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = "".join(c if " " <= c <= "_" else " " for c in text)
    return " ".join(text.split())  # 8 characters are precious: no double spaces


def window(text, tick):
    """The 8 characters shown at this tick: short text is padded, long text scrolls and wraps."""
    if len(text) <= WIDTH:
        return text.ljust(WIDTH)
    steps = len(text) - WIDTH + 1
    pos = max(0, tick % (steps + HOLD) - HOLD)
    return text[pos:pos + WIDTH]


class FisText:
    """Sends the now-playing lines through send(can_id, payload) once per INTERVAL."""

    def __init__(self, send, path=NOWPLAYING_FILE):
        self.send = send
        self.path = path
        self._stop = threading.Event()
        self._shown = None

    def start(self):
        threading.Thread(target=self._run, name="fis", daemon=True).start()

    def stop(self):
        self._stop.set()

    def frames(self, tick):
        """CAN frames for this tick, [] when nothing plays."""
        info = read_nowplaying(self.path)
        if info.get("state") != "playing" or not (info.get("song") or info.get("artist")):
            return []
        line1, line2 = to_fis(info.get("artist", "")), to_fis(info.get("song", ""))
        if (line1, line2) != self._shown:
            self._shown = (line1, line2)
            self._start_tick = tick
            log.info("FIS: %s / %s", line1, line2)
        t = tick - self._start_tick  # scrolling starts over with every new song
        return [
            (LINE1_ID, window(line1, t).encode("ascii")),
            (LINE2_ID, window(line2, t).encode("ascii")),
            (ACTIVATION_ID, ACTIVATION),
        ]

    def _run(self):
        tick = 0
        while not self._stop.wait(INTERVAL):
            for can_id, payload in self.frames(tick):
                self.send(can_id, payload)
            tick += 1
