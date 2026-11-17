"""RNS-MFD (MFD1) side of the CAN bus.

The MFD talks to an (emulated) VAG TV tuner on the 100 kbit infotainment CAN:
  0x464  MFD   -> tuner   (session handshake + button frames)
  0x264  tuner -> MFD     (our replies)

The handshake and button codes are the same ones skin.rnspi uses for
"Emulation TV-tuner RNSD" + "MFD Control" in this repository.
Buttons are only sent while the MFD is in TV mode.
"""
import logging
import threading
import time

log = logging.getLogger(__name__)

MFD_TX_ID = 0x464
TUNER_TX_ID = 0x264

# Button frame: [seq] 0x20 [01=press|02=release] [code hi] [code lo]
BUTTON_CODES = {
    0x0005: "ok",     # knob press / AS
    0x0300: "ok",
    0x0020: "up",
    0x0010: "down",   # "5"
    0x0400: "prev",   # <
    0x0500: "next",   # >
    0x0040: "exit",   # EXIT / "3"
    0x2000: "exit",
    0x3000: "scan",   # SCAN / "6"
    0x0002: "scan",
    0x0200: "key1",   # "1"
    0x0100: "key2",   # "2"
}
ENCODER_LEFT = bytes.fromhex("0100FF")
ENCODER_RIGHT = bytes.fromhex("0101FF")


def _seq(base, counter):
    return bytes([base + (counter & 0x0F)])


class TunerEmulator:
    """Answers the MFD so it believes a TV tuner is installed."""

    def __init__(self):
        self.counter = 0

    def handle(self, data):
        """Return the list of payloads to send on TUNER_TX_ID for one 0x464 frame."""
        replies = []
        if data == bytes.fromhex("E00100"):
            self.counter = 0
            replies.append(bytes.fromhex("E00100"))
        elif data == bytes.fromhex("E101"):
            replies.append(bytes.fromhex("10150100020000"))
            self.counter += 1
            replies.append(_seq(0x10, self.counter) + bytes.fromhex("270200"))
        elif data == bytes.fromhex("A300"):
            replies.append(bytes.fromhex("E101"))
        elif len(data) > 1:
            replies.append(bytes([((data[0] + 1) & 0x0F) + 0xB0]))

        if len(data) == 3 and data[1:3] == bytes.fromhex("0001"):
            self.counter += 1
            replies.append(_seq(0x10, self.counter) + bytes.fromhex("0101"))
        if len(data) == 4 and data[1] == 0x08:
            self.counter += 1
            replies.append(_seq(0x20, self.counter) + bytes.fromhex("090142500231"))
        if len(data) == 3 and data[1:3] == bytes.fromhex("0002"):
            self.counter += 1
            replies.append(_seq(0x10, self.counter) + bytes.fromhex("0102"))
        return replies


class ButtonDecoder:
    """Turns 0x464 button frames into (button, kind) events.

    kind is "turn" for the rotary knob, otherwise "short" or "long",
    decided on release like skin.rnspi does.
    """

    def __init__(self, long_press=0.4, clock=time.monotonic):
        self.long_press = long_press
        self.clock = clock
        self.pressed = {}

    def feed(self, data):
        if len(data) != 5 or data[1] != 0x20:
            return []
        body = data[2:5]
        if body == ENCODER_LEFT:
            return [("knob_left", "turn")]
        if body == ENCODER_RIGHT:
            return [("knob_right", "turn")]

        button = BUTTON_CODES.get(int.from_bytes(body[1:3], "big"))
        if button is None:
            log.debug("unknown MFD button frame %s", data.hex().upper())
            return []
        if body[0] == 0x01:
            self.pressed.setdefault(button, self.clock())
        elif body[0] == 0x02:
            started = self.pressed.pop(button, None)
            if started is not None:
                held = self.clock() - started
                return [(button, "long" if held > self.long_press else "short")]
        return []


class MfdLink:
    """Runs the tuner emulation on the CAN bus and reports button events."""

    def __init__(self, channel, long_press, on_button, on_raw=None):
        self.channel = channel
        self.on_button = on_button
        self.on_raw = on_raw
        self.tuner = TunerEmulator()
        self.buttons = ButtonDecoder(long_press)
        self.bus = None
        self._stop = threading.Event()

    def start(self):
        import can  # python3-can, only needed on the Pi

        self.bus = can.Bus(
            interface="socketcan",
            channel=self.channel,
            can_filters=[{"can_id": MFD_TX_ID, "can_mask": 0x7FF}],
        )
        # Announce ourselves, same effect as skin.rnspi's "464#E00100" kick.
        self._send(bytes.fromhex("E00100"))
        threading.Thread(target=self._run, name="mfd-can", daemon=True).start()
        log.info("MFD link started on %s", self.channel)

    def stop(self):
        self._stop.set()
        if self.bus:
            self.bus.shutdown()

    def _send(self, payload):
        import can

        try:
            self.bus.send(can.Message(arbitration_id=TUNER_TX_ID, data=payload, is_extended_id=False))
        except can.CanError as e:
            log.warning("CAN send failed: %s", e)

    def _run(self):
        while not self._stop.is_set():
            msg = self.bus.recv(timeout=1.0)
            if msg is None or msg.arbitration_id != MFD_TX_ID:
                continue
            data = bytes(msg.data)
            if self.on_raw:
                self.on_raw(data)
            for reply in self.tuner.handle(data):
                self._send(reply)
            for button, kind in self.buttons.feed(data):
                log.debug("MFD button %s %s", button, kind)
                try:
                    self.on_button(button, kind)
                except Exception:
                    log.exception("button handler failed")
