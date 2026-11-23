"""RNS-MFD1 -> openauto bridge: python3 -m rnsaa [-c /etc/rnsaa.conf] [--learn | --keyboard]

Keeps the MFD in TV mode (tuner emulation) and turns MFD buttons
into key presses for openauto (Android Auto).
"""
import argparse
import logging
import signal
import sys
import threading
import time

from . import config as config_mod
from .fis import FisText
from .mfd import MfdLink

log = logging.getLogger("rnsaa")
CAN_RETRY = 5  # seconds


def learn(cfg):
    """Run only the tuner emulation and print what the MFD sends."""
    def raw(data):
        print("464#" + data.hex().upper())

    def button(name, kind):
        print(f"  -> {name} {kind}")

    link = MfdLink(cfg.can_channel, cfg.long_press, button, on_raw=raw)
    link.start()
    print("Switch the MFD to TV and press buttons. Ctrl+C to quit.")
    threading.Event().wait()


def button_handler(cfg, keyboard):
    """Map MFD button events through [buttons] to openauto key taps."""
    actions = {key: config_mod.parse_action(value) for key, value in cfg.buttons.items()}

    def on_button(name, kind):
        action = actions.get(name if kind == "turn" else f"{name}.{kind}")
        if action:
            log.debug("%s %s -> %s", name, kind, action)
            keyboard.tap(action)

    return on_button


def keyboard_test(cfg):
    """No CAN: terminal keys stand in for MFD buttons."""
    from . import terminal
    from .keys import VirtualKeyboard

    keyboard = VirtualKeyboard()
    try:
        terminal.run(button_handler(cfg, keyboard))
    finally:
        keyboard.close()


def run(cfg):
    from .keys import VirtualKeyboard

    keyboard = VirtualKeyboard()
    on_button = button_handler(cfg, keyboard)

    link = MfdLink(cfg.can_channel, cfg.long_press, on_button)

    def shutdown(*_):
        link.stop()
        keyboard.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    # Keep the virtual keyboard alive while can0 is missing or not up yet (e.g. no CAN module)
    while True:
        try:
            link.start()
            break
        except Exception as e:
            log.warning("CAN %s not available (%s), retrying in %d s", cfg.can_channel, e, CAN_RETRY)
            time.sleep(CAN_RETRY)
    if cfg.fis:
        FisText(link.send).start()
    threading.Event().wait()


def main():
    parser = argparse.ArgumentParser(prog="rnsaa")
    parser.add_argument("-c", "--config", default="/etc/rnsaa.conf")
    parser.add_argument("--learn", action="store_true", help="print raw MFD frames and decoded buttons")
    parser.add_argument("--keyboard", action="store_true",
                        help="test without CAN: arrows / Enter / Backspace in this terminal act as MFD buttons")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    cfg = config_mod.load(args.config)
    if args.learn:
        learn(cfg)
    elif args.keyboard:
        keyboard_test(cfg)
    else:
        run(cfg)


if __name__ == "__main__":
    main()
