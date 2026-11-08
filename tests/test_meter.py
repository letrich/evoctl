from __future__ import annotations

from array import array
import unittest

from evoctl.meter import SILENCE_DB, find_evo_sources, peak_db


class MeterTests(unittest.TestCase):
    def test_peak_db_handles_interleaved_channels(self) -> None:
        levels = peak_db(array("f", [1.0, 0.5, 0.25, 0.0]), 2)
        self.assertAlmostEqual(levels[0], 0.0)
        self.assertAlmostEqual(levels[1], -6.0206, places=3)

    def test_peak_db_uses_floor_for_silence(self) -> None:
        self.assertEqual(peak_db(array("f", [0.0, 0.0]), 2), (SILENCE_DB,) * 2)

    def test_evo_source_discovery(self) -> None:
        output = """\
10\talsa_output.usb-Audient_EVO8-00.pro-output-0.monitor\tPipeWire\ts32le 6ch\n
11\talsa_input.usb-Audient_EVO8-00.pro-input-0\tPipeWire\ts32le 6ch\n
"""
        self.assertEqual(
            find_evo_sources(output),
            (
                "alsa_input.usb-Audient_EVO8-00.pro-input-0",
                "alsa_output.usb-Audient_EVO8-00.pro-output-0.monitor",
            ),
        )


if __name__ == "__main__":
    unittest.main()
