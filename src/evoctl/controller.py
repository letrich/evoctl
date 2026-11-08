"""High-level EVO 8 controls over an injectable transport."""

from __future__ import annotations

from typing import Protocol

from .protocol import (
    ControlAddress,
    EntityId,
    InputSelector,
    OutputSelector,
    encode_bool,
    encode_q8_8,
    mixer_crosspoint,
)


class Transport(Protocol):
    def write(self, address: ControlAddress, payload: bytes) -> None: ...

    def read(self, address: ControlAddress, length: int = 4) -> bytes: ...


class Evo8Controller:
    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    def set_phantom_power(self, channel: int, enabled: bool) -> None:
        self._input(InputSelector.PHANTOM_POWER, channel, encode_bool(enabled))

    def set_input_gain(self, channel: int, gain_db: float) -> None:
        self._input(InputSelector.GAIN, channel, encode_q8_8(gain_db, width=4))

    def set_input_mute(self, channel: int, muted: bool) -> None:
        self._input(InputSelector.MUTE, channel, encode_bool(muted))

    def set_stereo_link(self, channel: int, enabled: bool) -> None:
        self._input(InputSelector.STEREO_LINK, channel, encode_bool(enabled))

    def set_output_volume(self, channel: int, volume_db: float) -> None:
        self._output(OutputSelector.VOLUME, channel, encode_q8_8(volume_db, width=4))

    def set_output_mute(self, channel: int, muted: bool) -> None:
        self._output(OutputSelector.MUTE, channel, encode_bool(muted))

    def set_mix_level(self, source: int, destination: int, level_db: float) -> None:
        self.transport.write(
            mixer_crosspoint(source, destination),
            encode_q8_8(level_db, width=2),
        )

    def _input(self, selector: int, channel: int, payload: bytes) -> None:
        if not 0 <= channel < 4:
            raise ValueError("EVO 8 input channel must be in range 0..3")
        self.transport.write(ControlAddress(EntityId.INPUT, selector, channel), payload)

    def _output(self, selector: int, channel: int, payload: bytes) -> None:
        if not 0 <= channel < 4:
            raise ValueError("EVO 8 output channel must be in range 0..3")
        self.transport.write(ControlAddress(EntityId.OUTPUT, selector, channel), payload)
