from __future__ import annotations

from array import array
from pathlib import Path
import struct
import tempfile
import unittest

from evoctl.meter import (
    SILENCE_DB,
    extract_iso_payload,
    find_evo_sources,
    find_evo_usb_device,
    peak_db,
    s32le_peak_db,
)


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

    def test_s32le_peak_db(self) -> None:
        payload = struct.pack("<iiii", 2**30, -(2**29), 0, 2**30)
        levels = s32le_peak_db(payload, 2)
        self.assertAlmostEqual(levels[0], -6.0206, places=3)
        self.assertAlmostEqual(levels[1], -6.0206, places=3)

    def test_sparse_iso_payload_is_compacted(self) -> None:
        descriptors = b"".join(
            (
                struct.pack("<iIII", 0, 0, 4, 0),
                struct.pack("<iIII", 0, 8, 4, 0),
            )
        )
        self.assertEqual(
            extract_iso_payload(descriptors + b"abcd----efgh", 2),
            b"abcdefgh",
        )

    def test_evo_usb_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            device = Path(directory) / "3-2"
            device.mkdir()
            (device / "idVendor").write_text("2708\n")
            (device / "idProduct").write_text("0007\n")
            (device / "busnum").write_text("3\n")
            (device / "devnum").write_text("17\n")
            self.assertEqual(find_evo_usb_device(Path(directory)), (3, 17))


if __name__ == "__main__":
    unittest.main()
