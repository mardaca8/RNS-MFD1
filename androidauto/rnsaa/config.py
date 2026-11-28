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
    "as.short": "voice",
    "scan.short": "play_pause",
    "scan.long": "navigation",
    "prev.short": "prev",
    "prev.long": "left",
    "next.short": "next",
    "next.long": "right",
    "key1.short": "call",
    "key2.short": "end_call",
    "key3.short": "home",
    "key4.short": "up",
    "key5.short": "down",
    "key6.short": "navigation",
}


@dataclass
class Config:
    can_channel: str = "can0"
    long_press: float = 0.4
    fis: bool = True  # text on the instrument cluster instead of TV/VIDEO
    fis_nowplaying: bool = False  # artist / song from the phone instead of the fixed lines
    fis_line1: str = "Android"
    fis_line2: str = "Auto"
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
    cfg.fis = ini.getboolean("can", "fis", fallback=cfg.fis)
    cfg.fis_nowplaying = ini.getboolean("can", "fis_nowplaying", fallback=cfg.fis_nowplaying)
    cfg.fis_line1 = ini.get("can", "fis_line1", fallback=cfg.fis_line1)
    cfg.fis_line2 = ini.get("can", "fis_line2", fallback=cfg.fis_line2)
    if ini.has_section("buttons"):
        cfg.buttons.update(ini.items("buttons"))
    for action in cfg.buttons.values():
        parse_action(action)  # fail early on typos
    return cfg
