from __future__ import annotations

import unittest

from evoctl.controller import Evo8Controller
from evoctl.protocol import (
    ControlAddress,
    ControlTransfer,
    EntityId,
    InputSelector,
    UAC2_CUR,
    UAC2_INTERFACE_IN,
    UAC2_INTERFACE_OUT,
    decode_q8_8,
    encode_q8_8,
    mixer_crosspoint,
)


class RecordingTransport:
    def __init__(self) -> None:
        self.writes: list[tuple[ControlAddress, bytes]] = []

    def write(self, address: ControlAddress, payload: bytes) -> None:
        self.writes.append((address, bytes(payload)))

    def read(self, address: ControlAddress, length: int = 4) -> bytes:
        return bytes(length)


class ProtocolTests(unittest.TestCase):
    def test_input_gain_setup_packet(self) -> None:
        address = ControlAddress(EntityId.INPUT, InputSelector.GAIN, 2)
        transfer = ControlTransfer.write(address, encode_q8_8(31.0, width=4))
        self.assertEqual(transfer.request_type, UAC2_INTERFACE_OUT)
        self.assertEqual(transfer.request, UAC2_CUR)
        self.assertEqual(address.w_value, 0x0102)
        self.assertEqual(address.w_index, 0x3A00)
        self.assertEqual(transfer.payload, bytes.fromhex("001f0000"))

    def test_read_setup_packet(self) -> None:
        address = ControlAddress(EntityId.OUTPUT, 0, 2)
        transfer = ControlTransfer.read(address, 4)
        self.assertEqual(transfer.request_type, UAC2_INTERFACE_IN)
        self.assertEqual(transfer.request, UAC2_CUR)
        self.assertEqual(address.w_value, 0x0002)
        self.assertEqual(address.w_index, 0x3B00)

    def test_q8_8_round_trip(self) -> None:
        for value in (-128.0, -42.5, -0.5, 0.0, 31.0):
            for width in (2, 4):
                with self.subTest(value=value, width=width):
                    self.assertEqual(decode_q8_8(encode_q8_8(value, width=width)), value)

    def test_mixer_crosspoint_layout(self) -> None:
        first = mixer_crosspoint(0, 0)
        last = mixer_crosspoint(9, 3)
        self.assertEqual(first.w_value, 0x0100)
        self.assertEqual(last.w_value, 0x0127)
        self.assertEqual(first.w_index, 0x3C00)

    def test_high_level_mixer_write(self) -> None:
        transport = RecordingTransport()
        controller = Evo8Controller(transport)
        controller.set_mix_level(4, 2, -12.5)
        self.assertEqual(len(transport.writes), 1)
        address, payload = transport.writes[0]
        self.assertEqual(address.w_value, 0x0112)
        self.assertEqual(address.w_index, 0x3C00)
        self.assertEqual(payload, bytes.fromhex("80f3"))


if __name__ == "__main__":
    unittest.main()
