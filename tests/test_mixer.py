from __future__ import annotations

import unittest

from evoctl.mixer import (
    FADER_STEPS,
    SILENCE_DB,
    channel_gains,
    pan_attenuations,
    reconstruct_level_and_pan,
)


class MixerTaperTests(unittest.TestCase):
    def test_official_fader_table_has_audio_taper_and_fine_unity_steps(self) -> None:
        self.assertEqual(len(FADER_STEPS), 179)
        self.assertEqual(FADER_STEPS[:4], (-128.0, -122.0, -116.0, -110.0))
        self.assertIn(-20.0, FADER_STEPS)
        self.assertIn(-4.8, FADER_STEPS)
        self.assertEqual(FADER_STEPS[-2:], (5.8, 6.0))

    def test_official_pan_law_is_minus_six_db_at_centre(self) -> None:
        left, right = pan_attenuations(0)
        self.assertAlmostEqual(left, -6.0, places=6)
        self.assertAlmostEqual(right, -6.0, places=6)
        self.assertEqual(pan_attenuations(-100), (0.0, SILENCE_DB))
        self.assertEqual(pan_attenuations(100), (SILENCE_DB, 0.0))

    def test_hard_pan_attenuates_the_opposite_side(self) -> None:
        self.assertEqual(channel_gains(-12.0, -100), (-12.0, SILENCE_DB))
        self.assertEqual(channel_gains(-12.0, 100), (SILENCE_DB, -12.0))

    def test_level_and_pan_round_trip_through_crosspoints(self) -> None:
        levels = channel_gains(-18.0, 37)
        level, pan = reconstruct_level_and_pan(*levels)
        self.assertEqual(level, -18.0)
        self.assertEqual(pan, 37)


if __name__ == "__main__":
    unittest.main()
