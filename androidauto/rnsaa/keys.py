"""Virtual keyboard (uinput) that feeds MFD buttons to openauto.

openauto maps these Qt keys to Android Auto key codes
(src/autoapp/Projection/InputDevice.cpp in opencardev/openauto).
"""
import logging
import time

log = logging.getLogger(__name__)

# action -> evdev key name
ACTIONS = {
    "rotary_left": "KEY_1",    # KEYCODE_ROTARY_CONTROLLER, wheel left
    "rotary_right": "KEY_2",   # KEYCODE_ROTARY_CONTROLLER, wheel right
    "select": "KEY_ENTER",     # DPAD_CENTER
    "back": "KEY_ESC",
    "home": "KEY_H",
    "up": "KEY_UP",
    "down": "KEY_DOWN",
    "left": "KEY_LEFT",
    "right": "KEY_RIGHT",
    "play": "KEY_X",
    "pause": "KEY_C",
    "play_pause": "KEY_B",
    "next": "KEY_N",
    "prev": "KEY_V",
    "voice": "KEY_M",          # Google Assistant
    "call": "KEY_P",
    "end_call": "KEY_O",
    "navigation": "KEY_F",
}


class VirtualKeyboard:
    def __init__(self, name="rns-mfd-keys"):
        from evdev import UInput, ecodes  # python3-evdev, only needed on the Pi

        self.ecodes = ecodes
        self.ui = UInput({ecodes.EV_KEY: [ecodes.ecodes[k] for k in ACTIONS.values()]}, name=name)
        log.info("virtual keyboard %s created", self.ui.device.path if self.ui.device else name)

    def tap(self, action):
        code = self.ecodes.ecodes[ACTIONS[action]]
        self.ui.write(self.ecodes.EV_KEY, code, 1)
        self.ui.syn()
        time.sleep(0.03)
        self.ui.write(self.ecodes.EV_KEY, code, 0)
        self.ui.syn()

    def close(self):
        self.ui.close()
