"""Hardware-free tests:  cd androidauto && python3 -m unittest discover tests"""
import configparser
import os
import tempfile
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rnsaa import config, fis  # noqa: E402
from rnsaa.keys import ACTIONS  # noqa: E402
from rnsaa.mfd import ButtonDecoder, TunerEmulator  # noqa: E402
from rnsaa.terminal import KEYMAP, parse  # noqa: E402

HERE = os.path.dirname(__file__)
h = bytes.fromhex


class TunerEmulatorTest(unittest.TestCase):
    def test_handshake(self):
        t = TunerEmulator()
        self.assertEqual(t.handle(h("E00100")), [h("E00100")])
        self.assertEqual(t.handle(h("A300")), [h("E101")])
        self.assertEqual(t.handle(h("E101")), [h("10150100020000"), h("11270200")])

    def test_ack_and_counter(self):
        t = TunerEmulator()
        self.assertEqual(t.handle(h("2A0001")), [h("BB"), h("110101")])
        self.assertEqual(t.handle(h("2B0002")), [h("BC"), h("120102")])
        self.assertEqual(t.handle(h("2C080000")), [h("BD"), h("23090142500231")])

    def test_button_frame_is_acked(self):
        self.assertEqual(TunerEmulator().handle(h("2F20010020")), [h("B0")])


class ButtonDecoderTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.d = ButtonDecoder(long_press=0.4, clock=lambda: self.now)

    def press(self, code, held):
        self.assertEqual(self.d.feed(h("212001" + code)), [])
        self.now += held
        return self.d.feed(h("222002" + code))

    def test_knob(self):
        self.assertEqual(self.d.feed(h("21200100")), [])  # wrong length
        self.assertEqual(self.d.feed(h("21200100FF")), [("knob_left", "turn")])
        self.assertEqual(self.d.feed(h("21200101FF")), [("knob_right", "turn")])

    def test_short_and_long(self):
        self.assertEqual(self.press("0005", 0.1), [("ok", "short")])
        self.assertEqual(self.press("0300", 1.0), [("as", "long")])
        self.assertEqual(self.press("0400", 0.1), [("prev", "short")])
        self.assertEqual(self.press("0040", 0.5), [("exit", "long")])

    def test_preset_keys_fire_on_press(self):
        # recorded on the MFD: 1-6 send only a press frame
        self.assertEqual(self.d.feed(h("1320010200")), [("key1", "short")])
        self.assertEqual(self.d.feed(h("1520012000")), [("key3", "short")])
        self.assertEqual(self.d.feed(h("1820010002")), [("key6", "short")])
        self.assertEqual(self.d.feed(h("1920020002")), [])  # stray release is ignored

    def test_release_without_press_and_unknown(self):
        self.assertEqual(self.d.feed(h("2220020040")), [])
        self.assertEqual(self.d.feed(h("2120011234")), [])
        self.assertEqual(self.d.feed(h("2130010020")), [])


class ConfigTest(unittest.TestCase):
    def test_default_conf_file_loads(self):
        cfg = config.load(os.path.join(HERE, "..", "rnsaa.conf"))
        self.assertEqual(cfg.buttons, config.DEFAULT_BUTTONS)
        self.assertEqual(cfg.long_press, 0.4)

    def test_actions(self):
        self.assertEqual(config.parse_action("Select"), "select")
        self.assertIsNone(config.parse_action("none"))
        with self.assertRaises(ValueError):
            config.parse_action("selcet")

    def test_every_action_has_a_key(self):
        for action in config.DEFAULT_BUTTONS.values():
            self.assertTrue(ACTIONS[action].startswith("KEY_"))


class TerminalKeysTest(unittest.TestCase):
    def test_arrows_and_enter(self):
        self.assertEqual(parse("\x1b[D\x1b[C\x1b[A\x1b[B\r"), [
            ("knob_left", "turn"), ("knob_right", "turn"),
            ("key4", "short"), ("key5", "short"), ("ok", "short")])

    def test_unknown_keys_skipped(self):
        self.assertEqual(parse("x\x1b[5~\x7f"), [("exit", "short")])

    def test_every_key_is_mapped(self):
        for name, kind in KEYMAP.values():
            key = name if kind == "turn" else f"{name}.{kind}"
            self.assertIn(key, config.DEFAULT_BUTTONS)


class OpenautoIniTest(unittest.TestCase):
    def test_all_buttons_enabled(self):
        ini = configparser.ConfigParser(inline_comment_prefixes=None, comment_prefixes=(";",))
        ini.optionxform = str
        ini.read(os.path.join(HERE, "..", "openauto.ini"))
        self.assertEqual(ini.get("Video", "Resolution"), "1")
        self.assertEqual(ini.get("Input", "EnableTouchscreen"), "false")
        self.assertEqual(ini.get("Input", "ScrollWheelButton"), "true")
        self.assertEqual(ini.get("Audio", "OutputBackendType"), "0")


if __name__ == "__main__":
    unittest.main()


class FisTest(unittest.TestCase):
    def test_text_and_scrolling(self):
        self.assertEqual(fis.to_fis("Žemynos ąžuolas"), "ZEMYNOS AZUOLAS")
        self.assertEqual(fis.to_fis("Café — 2€"), "CAFE 2")
        self.assertEqual(fis.window("DJ SMASH", 5), "DJ SMASH")
        self.assertEqual(fis.window("ABC", 0), "ABC     ")
        text = "MOSCOW NEVER"  # 12 chars: 5 positions, held 2 ticks at the start
        shown = [fis.window(text, t) for t in range(8)]
        self.assertEqual(shown, ["MOSCOW N", "MOSCOW N", "MOSCOW N", "OSCOW NE", "SCOW NEV",
                                 "COW NEVE", "OW NEVER", "MOSCOW N"])

    def test_frames_only_while_playing(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".np") as f:
            f.write("state=playing\nsong=Moscow Never Sleeps\nartist=DJ Smash\nalbum=x\n")
        self.addCleanup(os.unlink, f.name)
        text = fis.FisText(send=None, path=f.name)
        self.assertEqual(text.frames(10), [
            (0x265, b"DJ SMASH"), (0x267, b"MOSCOW N"), (0x665, bytes.fromhex("6F200000300020"))])
        with open(f.name, "w") as out:
            out.write("state=paused\nsong=Moscow Never Sleeps\nartist=DJ Smash\n")
        self.assertEqual(text.frames(11), [])
        self.assertEqual(fis.FisText(send=None, path=f.name + ".missing").frames(0), [])

    def test_fixed_lines(self):
        text = fis.FisText(send=None, path="/nonexistent", fixed=("Android", "Auto"))
        self.assertEqual(text.frames(0), [
            (0x265, b"ANDROID "), (0x267, b"  AUTO  "), (0x665, bytes.fromhex("6F200000300020"))])
