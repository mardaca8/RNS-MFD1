"""Test mode: terminal keys (e.g. over SSH) stand in for MFD buttons.

Each key becomes the same (button, kind) event the CAN link produces,
so it goes through the normal [buttons] mapping to openauto.
"""
import os
import select
import sys
import termios
import tty

# terminal key sequence -> MFD button event
KEYMAP = {
    "\x1b[D": ("knob_left", "turn"),   # Left arrow
    "\x1bOD": ("knob_left", "turn"),
    "\x1b[C": ("knob_right", "turn"),  # Right arrow
    "\x1bOC": ("knob_right", "turn"),
    "\x1b[A": ("up", "short"),         # Up arrow
    "\x1bOA": ("up", "short"),
    "\x1b[B": ("down", "short"),       # Down arrow
    "\x1bOB": ("down", "short"),
    "\r": ("ok", "short"),             # Enter
    "\n": ("ok", "short"),
    "v": ("ok", "long"),
    "\x7f": ("exit", "short"),         # Backspace
    "\x08": ("exit", "short"),
    "h": ("exit", "long"),
    ",": ("prev", "short"),
    "<": ("prev", "long"),
    ".": ("next", "short"),
    ">": ("next", "long"),
    " ": ("scan", "short"),
    "n": ("scan", "long"),
    "1": ("key1", "short"),
    "2": ("key2", "short"),
}
QUIT = ("q", "\x03")  # q, Ctrl+C

HELP = """Keyboard test mode (stands in for the MFD buttons):
  Left / Right   knob turn            Up / Down    up / down
  Enter          knob press (select)  v            long knob press (assistant)
  Backspace      EXIT (back)          h            long EXIT (home)
  , / .          prev / next track    < / >        long prev / next (left / right)
  Space          SCAN (play/pause)    n            long SCAN (navigation)
  1 / 2          answer / end call    q            quit"""


def parse(chunk):
    """Split one read from the terminal into MFD button events."""
    events = []
    longest = max(len(seq) for seq in KEYMAP)
    i = 0
    while i < len(chunk):
        for size in range(longest, 0, -1):
            event = KEYMAP.get(chunk[i:i + size])
            if event:
                events.append(event)
                i += size
                break
        else:
            i += 1  # unknown key or the rest of an unknown escape sequence
    return events


def run(on_button):
    """Read keys until q / Ctrl+C and pass each MFD event to on_button(name, kind)."""
    print(HELP)
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            select.select([fd], [], [])
            chunk = os.read(fd, 32).decode(errors="ignore")
            if any(key in chunk for key in QUIT):
                break
            for name, kind in parse(chunk):
                sys.stdout.write(f"-> {name} {kind}\r\n")
                sys.stdout.flush()
                on_button(name, kind)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
