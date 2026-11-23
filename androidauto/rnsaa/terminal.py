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
    "\x1b[A": ("key4", "short"),       # Up arrow
    "\x1bOA": ("key4", "short"),
    "\x1b[B": ("key5", "short"),       # Down arrow
    "\x1bOB": ("key5", "short"),
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
    "a": ("as", "short"),
    "1": ("key1", "short"),
    "2": ("key2", "short"),
    "3": ("key3", "short"),
    "4": ("key4", "short"),
    "5": ("key5", "short"),
    "6": ("key6", "short"),
}
QUIT = ("q", "\x03")  # q, Ctrl+C

HELP = """Keyboard test mode (stands in for the MFD buttons):
  Left / Right   right knob turn      Enter        right knob press (select)
  Backspace      arrow next to NAVI   v / h        long knob press / long arrow (assistant / home)
  , / .          < / > (track)        < / >        long < / > (left / right)
  Space / n      SCAN / long SCAN     a            AS (assistant)
  1 .. 6         preset keys          Up / Down    same as 4 / 5
  q              quit"""


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
            if chunk[i] == "\x1b":
                # skip a whole unknown escape sequence (e.g. PageUp "\x1b[5~"), not just ESC
                i += 1
                while i < len(chunk) and not (chunk[i].isalpha() or chunk[i] == "~"):
                    i += 1
            i += 1
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
