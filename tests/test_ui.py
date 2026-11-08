from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from evoctl.__main__ import DemoTransport
from evoctl.controller import Evo8Controller
from evoctl.ui import MainWindow


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


if __name__ == "__main__":
    unittest.main()
