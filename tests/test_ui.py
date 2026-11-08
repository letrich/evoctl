from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from evoctl.__main__ import DemoTransport
from evoctl.controller import Evo8Controller
from evoctl.meter import MeterSnapshot, SILENCE_DB
from evoctl.ui import MainWindow


class FixedMeterReader:
    status = "TEST METERS"

    def __init__(self, snapshot: MeterSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> MeterSnapshot:
        return self._snapshot

    def stop(self) -> None:
        pass


class UiReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_hardware_sync_applies_encoder_changes(self) -> None:
        controller = Evo8Controller(DemoTransport())
        window = MainWindow(controller, connected=True, status_text="TEST")
        controller.set_input_gain(0, 23)
        controller.set_output_volume(0, -17)

        window._sync_hardware_state()

        self.assertEqual(window.input_strips[0].gain.value(), 23)
        self.assertEqual(window.master.volume.value(), -17)
        self.assertEqual(window._sync_failures, 0)
        window.close()

    def test_pan_is_reconstructed_from_device_crosspoints(self) -> None:
        controller = Evo8Controller(DemoTransport())
        controller.set_mix_level(0, 0, -64)
        controller.set_mix_level(0, 1, -32)
        window = MainWindow(controller, connected=True, status_text="TEST")

        window.load_state()

        self.assertEqual(window.input_strips[0].fader.value(), -32)
        self.assertEqual(window.input_strips[0].pan.value(), 25)
        window.close()

    def test_meters_follow_mix_fader_and_output_volume(self) -> None:
        window = MainWindow(
            Evo8Controller(DemoTransport()), connected=True, status_text="TEST"
        )
        window.input_strips[4].fader.setValue(-20)
        window.master.volume.setValue(-6)
        window._meter_reader = FixedMeterReader(
            MeterSnapshot(
                capture=(SILENCE_DB,) * 6,
                playback=(-10.0, -12.0, SILENCE_DB, SILENCE_DB, SILENCE_DB, SILENCE_DB),
                capture_seen=True,
                playback_seen=True,
            )
        )

        window._update_meters()

        self.assertEqual(window.input_strips[4].meter._levels, [-30.0, -32.0])
        self.assertEqual(window.master.meter._levels, [-36.0, -38.0])
        window.close()

    def test_artist_mix_meter_uses_sources_routed_to_outputs_3_and_4(self) -> None:
        window = MainWindow(
            Evo8Controller(DemoTransport()), connected=True, status_text="TEST"
        )
        window.artist_action.setChecked(True)
        window.select_mix(1)
        window.input_strips[4].fader.setValue(-10)
        window.master.volume.setValue(0)
        window._meter_reader = FixedMeterReader(
            MeterSnapshot(
                capture=(SILENCE_DB,) * 6,
                playback=(-10.0, -12.0, SILENCE_DB, SILENCE_DB, SILENCE_DB, SILENCE_DB),
                capture_seen=True,
                playback_seen=True,
            )
        )

        window._update_meters()

        self.assertEqual(window.active_pair, 1)
        self.assertEqual(window.master.meter._levels, [-20.0, -22.0])
        window.close()

    def test_mixer_settings_survive_restart_and_restore_device(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evoctl.ini"
            first_settings = QSettings(str(path), QSettings.Format.IniFormat)
            first = MainWindow(
                Evo8Controller(DemoTransport()),
                connected=True,
                status_text="TEST",
                settings=first_settings,
            )
            first.artist_action.setChecked(True)
            first.preamp_action.setChecked(True)
            first.select_mix(1)
            first.input_strips[0].fader.setValue(-24)
            first.input_strips[0].pan.setValue(50)
            first.input_strips[0].mute.setChecked(True)
            first.close()

            second_transport = DemoTransport()
            second = MainWindow(
                Evo8Controller(second_transport),
                connected=True,
                status_text="TEST",
                settings=QSettings(str(path), QSettings.Format.IniFormat),
            )
            second.load_state()
            second.load_preferences()

            self.assertTrue(second.artist_enabled)
            self.assertTrue(second.preamp_action.isChecked())
            self.assertEqual(second.active_pair, 1)
            self.assertEqual(second.input_strips[0].fader.value(), -24)
            self.assertEqual(second.input_strips[0].pan.value(), 50)
            self.assertTrue(second.input_strips[0].mute.isChecked())
            self.assertEqual(
                second.controller.read_mix_level(0, 2),
                -128,
            )
            self.assertEqual(
                second.controller.read_mix_level(0, 3),
                -128,
            )
            second.close()


if __name__ == "__main__":
    unittest.main()
