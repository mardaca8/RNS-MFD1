import configparser
from dataclasses import dataclass, field

from .keys import ACTIONS

DEFAULT_BUTTONS = {
    "knob_left": "rotary_left",
    "knob_right": "rotary_right",
    "ok.short": "select",
    "ok.long": "voice",
    "exit.short": "back",
    "exit.long": "home",
    "up.short": "up",
    "down.short": "down",
    "prev.short": "prev",
    "prev.long": "left",
    "next.short": "next",
    "next.long": "right",
    "scan.short": "play_pause",
    "scan.long": "navigation",
    "key1.short": "call",
    "key2.short": "end_call",
}


@dataclass
class Config:
    can_channel: str = "can0"
    long_press: float = 0.4
    buttons: dict = field(default_factory=lambda: dict(DEFAULT_BUTTONS))


def parse_action(name):
    """Returns the action name, or None for 'none'."""
    name = name.strip().lower()
    if name in ("", "none"):
        return None
    if name not in ACTIONS:
        raise ValueError(f"unknown button action '{name}'")
    return name


def load(path):
    cfg = Config()
    ini = configparser.ConfigParser(interpolation=None)
    if path and not ini.read(path):
        raise FileNotFoundError(path)

    cfg.can_channel = ini.get("can", "channel", fallback=cfg.can_channel)
    cfg.long_press = ini.getfloat("can", "long_press", fallback=cfg.long_press)
    if ini.has_section("buttons"):
        cfg.buttons.update(ini.items("buttons"))
    for action in cfg.buttons.values():
        parse_action(action)  # fail early on typos
    return cfg
