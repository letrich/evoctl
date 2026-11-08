"""Mixer tapers recovered from the official EVO 4.4.0 application."""

from __future__ import annotations

from bisect import bisect_left
import math


SILENCE_DB = -128.0
MAX_FADER_DB = 6.0

# CustomScaledFader uses this exact 179-value table.  Coarse steps are useful
# near silence; around unity the hardware's Q8.8 crosspoints allow 0.2 dB
# changes, so most of the physical travel is kept in the useful range.
FADER_STEPS: tuple[float, ...] = (
    tuple(float(value) for value in range(-128, -49, 6))
    + tuple(float(value) for value in range(-49, -39))
    + tuple(value / 2 for value in range(-79, -39))
    + tuple(value / 4 for value in range(-79, -19))
    + tuple(value / 5 for value in range(-24, 31))
)


def nearest_fader_index(value_db: float) -> int:
    """Return the closest official fader step for an arbitrary dB value."""
    index = bisect_left(FADER_STEPS, value_db)
    if index <= 0:
        return 0
    if index >= len(FADER_STEPS):
        return len(FADER_STEPS) - 1
    before = FADER_STEPS[index - 1]
    after = FADER_STEPS[index]
    return index - 1 if value_db - before <= after - value_db else index


def clamp_mixer_gain(value_db: float) -> float:
    return max(SILENCE_DB, min(MAX_FADER_DB, value_db))


def _official_pan_curve(position: float) -> float:
    """Convert one side's 0..1 pan position to the official attenuation."""
    position = max(0.0, min(1.0, position))
    # The Windows model computes this coefficient from pow(10, -0.3), giving
    # exactly -6 dB on each side at the centre position.
    coefficient = 2.0 - 4.0 * (10.0**-0.3)
    amplitude = ((coefficient * position + 1.0) - coefficient) * position
    if amplitude <= 0.0:
        return SILENCE_DB
    return max(SILENCE_DB, 20.0 * math.log10(amplitude))


def pan_attenuations(pan: int) -> tuple[float, float]:
    """Return official mono left/right attenuation for a -100..100 pan."""
    normalised = (max(-100, min(100, pan)) + 100.0) / 200.0
    return _official_pan_curve(1.0 - normalised), _official_pan_curve(normalised)


def channel_gains(level_db: float, pan: int) -> tuple[float, float]:
    """Return the left/right crosspoint gains for one source channel."""
    if level_db <= SILENCE_DB:
        return SILENCE_DB, SILENCE_DB
    attenuations = pan_attenuations(pan)
    return tuple(
        SILENCE_DB
        if attenuation <= SILENCE_DB
        else clamp_mixer_gain(level_db + attenuation)
        for attenuation in attenuations
    )


def reconstruct_level_and_pan(left_db: float, right_db: float) -> tuple[float, int]:
    """Reconstruct the nearest UI state from a pair of device crosspoints."""
    if left_db <= SILENCE_DB and right_db <= SILENCE_DB:
        return SILENCE_DB, 0

    best_pan = 0
    best_error = math.inf
    best_level = SILENCE_DB
    for pan in range(-100, 101):
        left_attenuation, right_attenuation = pan_attenuations(pan)
        candidates = []
        if left_db > SILENCE_DB and left_attenuation > SILENCE_DB:
            candidates.append(left_db - left_attenuation)
        if right_db > SILENCE_DB and right_attenuation > SILENCE_DB:
            candidates.append(right_db - right_attenuation)
        if not candidates:
            continue
        level = sum(candidates) / len(candidates)
        predicted = channel_gains(level, pan)
        error = sum(
            abs(observed - expected)
            for observed, expected in zip((left_db, right_db), predicted, strict=True)
            if observed > SILENCE_DB or expected > SILENCE_DB
        )
        if error < best_error:
            best_error = error
            best_pan = pan
            best_level = level
    return FADER_STEPS[nearest_fader_index(clamp_mixer_gain(best_level))], best_pan
