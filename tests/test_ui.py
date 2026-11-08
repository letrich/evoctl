from __future__ import annotations

import json
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
from evoctl.mixer import channel_gains
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
        left, right = channel_gains(-32, 25)
        controller.set_mix_level(0, 0, left)
        controller.set_mix_level(0, 1, right)
        window = MainWindow(controller, connected=True, status_text="TEST")

        window.load_state()

        self.assertEqual(window.input_strips[0].fader.value(), -32)
        self.assertEqual(window.input_strips[0].pans[0].value(), 25)
        window.close()

    def test_daw_playback_channels_are_four_mono_strips(self) -> None:
        window = MainWindow(
            Evo8Controller(DemoTransport()), connected=True, status_text="TEST"
        )

        daw_strips = window.input_strips[4:8]

        self.assertEqual(
            [strip.spec.name for strip in daw_strips],
            ["DAW 1", "DAW 2", "DAW 3", "DAW 4"],
        )
        self.assertEqual(
            [strip.spec.sources for strip in daw_strips],
            [(4,), (5,), (6,), (7,)],
        )
        self.assertTrue(all(len(strip.pans) == 1 for strip in daw_strips))
        window.close()

    def test_loopback_stereo_pan_changes_channel_and_master_indication(self) -> None:
        window = MainWindow(
            Evo8Controller(DemoTransport()), connected=True, status_text="TEST"
        )
        window.input_strips[8].fader.setValue(-12)
        window.input_strips[8].pans[1].setValue(100)
        window._meter_reader = FixedMeterReader(
            MeterSnapshot(
                capture=(SILENCE_DB,) * 5 + (-14.0,),
                playback=(SILENCE_DB,) * 6,
                capture_seen=True,
                playback_seen=True,
            )
        )

        window._update_meters()

        self.assertEqual(window.input_strips[8].meter._levels, [SILENCE_DB, -26.0])
        self.assertEqual(window.master.meter._levels, [SILENCE_DB, -26.0])
        window.close()

    def test_loopback_stereo_pans_write_all_four_crosspoints(self) -> None:
        controller = Evo8Controller(DemoTransport())
        window = MainWindow(controller, connected=True, status_text="TEST")
        strip = window.input_strips[8]
        strip.fader.setValue(-12)
        strip.pans[0].setValue(-100)
        strip.pans[1].setValue(100)

        strip.write_effective_level(False)

        self.assertEqual(controller.read_mix_level(8, 0), -12)
        self.assertEqual(controller.read_mix_level(8, 1), SILENCE_DB)
        self.assertEqual(controller.read_mix_level(9, 0), SILENCE_DB)
        self.assertEqual(controller.read_mix_level(9, 1), -12)
        window.close()

    def test_meters_follow_mix_fader_and_output_volume(self) -> None:
        window = MainWindow(
            Evo8Controller(DemoTransport()), connected=True, status_text="TEST"
        )
        window.input_strips[4].fader.setValue(-20)
        window.input_strips[4].pans[0].setValue(-100)
        window.input_strips[5].fader.setValue(-20)
        window.input_strips[5].pans[0].setValue(100)
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

        self.assertEqual(window.input_strips[4].meter._levels, [-30.0])
        self.assertEqual(window.input_strips[5].meter._levels, [-32.0])
        self.assertEqual(window.master.meter._levels, [-36.0, -38.0])
        window.close()

    def test_artist_mix_meter_uses_sources_routed_to_outputs_3_and_4(self) -> None:
        window = MainWindow(
            Evo8Controller(DemoTransport()), connected=True, status_text="TEST"
        )
        window.artist_action.setChecked(True)
        window.select_mix(1)
        window.input_strips[4].fader.setValue(-10)
        window.input_strips[4].pans[0].setValue(-100)
        window.input_strips[5].fader.setValue(-10)
        window.input_strips[5].pans[0].setValue(100)
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
            first.input_strips[0].pans[0].setValue(50)
            first.input_strips[0].mute.setChecked(True)
            first.input_strips[4].fader.setValue(-10)
            first.input_strips[4].pans[0].setValue(-50)
            first.input_strips[5].fader.setValue(-14)
            first.input_strips[5].pans[0].setValue(40)
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
            self.assertEqual(second.input_strips[0].pans[0].value(), 50)
            self.assertTrue(second.input_strips[0].mute.isChecked())
            self.assertEqual(second.input_strips[4].fader.value(), -10)
            self.assertEqual(second.input_strips[4].pans[0].value(), -50)
            self.assertEqual(second.input_strips[5].fader.value(), -14)
            self.assertEqual(second.input_strips[5].pans[0].value(), 40)
            self.assertEqual(
                second.controller.read_mix_level(0, 2),
                -128,
            )
            self.assertEqual(
                second.controller.read_mix_level(0, 3),
                -128,
            )
            second.close()

    def test_saved_stereo_daw_settings_migrate_to_four_mono_strips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(
                str(Path(directory) / "old-evoctl.ini"), QSettings.Format.IniFormat
            )
            settings.setValue("state/version", 1)
            for index, fader, left, right in (
                (4, -10, -70, 60),
                (5, -20, -80, 80),
                (6, -8, -100, 100),
            ):
                settings.setValue(f"mix/0/strip/{index}/fader", fader)
                settings.setValue(f"mix/0/strip/{index}/pan_left", left)
                settings.setValue(f"mix/0/strip/{index}/pan_right", right)

            window = MainWindow(
                Evo8Controller(DemoTransport()),
                connected=False,
                status_text="TEST",
                settings=settings,
            )
            window.load_preferences()

            self.assertEqual(window.input_strips[4].fader.value(), -10)
            self.assertEqual(window.input_strips[4].pans[0].value(), -70)
            self.assertEqual(window.input_strips[5].fader.value(), -10)
            self.assertEqual(window.input_strips[5].pans[0].value(), 60)
            self.assertEqual(window.input_strips[6].fader.value(), -20)
            self.assertEqual(window.input_strips[6].pans[0].value(), -80)
            self.assertEqual(window.input_strips[7].fader.value(), -20)
            self.assertEqual(window.input_strips[7].pans[0].value(), 80)
            self.assertEqual(window.input_strips[8].fader.value(), -8)
            self.assertEqual(
                tuple(pan.value() for pan in window.input_strips[8].pans),
                (-100, 100),
            )
            window.close()

    def test_mixer_configuration_round_trip_restores_both_mixes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configuration = root / "session.evoctl.json"
            first = MainWindow(
                Evo8Controller(DemoTransport()),
                connected=True,
                status_text="TEST",
                settings=QSettings(
                    str(root / "first.ini"), QSettings.Format.IniFormat
                ),
            )
            first.input_strips[4].fader.setValue(-12)
            first.input_strips[4].pans[0].setValue(-30)
            first.input_strips[4].mute.setChecked(True)
            first.artist_action.setChecked(True)
            first.select_mix(1)
            first.input_strips[5].fader.setValue(-18)
            first.input_strips[5].pans[0].setValue(55)
            first.input_strips[5].solo.setChecked(True)

            first.save_mixer_configuration(configuration)
            document = json.loads(configuration.read_text(encoding="utf-8"))

            self.assertEqual(document["format"], "evoctl-mixer-configuration")
            self.assertEqual(document["active_mix"], 1)
            self.assertNotIn("gain", configuration.read_text(encoding="utf-8"))

            second = MainWindow(
                Evo8Controller(DemoTransport()),
                connected=True,
                status_text="TEST",
                settings=QSettings(
                    str(root / "second.ini"), QSettings.Format.IniFormat
                ),
            )
            second.open_mixer_configuration(configuration)

            self.assertTrue(second.artist_enabled)
            self.assertEqual(second.active_pair, 1)
            self.assertEqual(second.input_strips[5].fader.value(), -18)
            self.assertEqual(second.input_strips[5].pans[0].value(), 55)
            self.assertTrue(second.input_strips[5].solo.isChecked())
            second.select_mix(0)
            self.assertEqual(second.input_strips[4].fader.value(), -12)
            self.assertEqual(second.input_strips[4].pans[0].value(), -30)
            self.assertTrue(second.input_strips[4].mute.isChecked())
            first.close()
            second.close()

    def test_invalid_mixer_configuration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            configuration = root / "invalid.json"
            configuration.write_text('{"format": "something-else"}', encoding="utf-8")
            window = MainWindow(
                Evo8Controller(DemoTransport()),
                connected=True,
                status_text="TEST",
                settings=QSettings(
                    str(root / "settings.ini"), QSettings.Format.IniFormat
                ),
            )

            with self.assertRaisesRegex(ValueError, "not an evoctl"):
                window.open_mixer_configuration(configuration)
            window.close()


if __name__ == "__main__":
    unittest.main()
