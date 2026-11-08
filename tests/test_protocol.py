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
        self.reads: list[tuple[ControlAddress, int]] = []
        self.responses: dict[tuple[ControlAddress, int], bytes] = {}

    def write(self, address: ControlAddress, payload: bytes) -> None:
        self.writes.append((address, bytes(payload)))

    def read(self, address: ControlAddress, length: int = 4) -> bytes:
        self.reads.append((address, length))
        return self.responses.get((address, length), bytes(length))


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

    def test_high_level_input_readback(self) -> None:
        transport = RecordingTransport()
        channel = 2
        transport.responses.update(
            {
                (ControlAddress(EntityId.INPUT, 0, channel), 4): bytes.fromhex(
                    "01000000"
                ),
                (ControlAddress(EntityId.INPUT, 1, channel), 4): bytes.fromhex(
                    "001f0000"
                ),
                (ControlAddress(EntityId.INPUT, 2, channel), 4): bytes.fromhex(
                    "00000000"
                ),
                (ControlAddress(EntityId.INPUT, 3, channel), 4): bytes.fromhex(
                    "01000000"
                ),
            }
        )
        state = Evo8Controller(transport).read_input(channel)
        self.assertTrue(state.phantom_power)
        self.assertEqual(state.gain_db, 31.0)
        self.assertFalse(state.muted)
        self.assertTrue(state.stereo_linked)

    def test_high_level_output_and_mixer_readback(self) -> None:
        transport = RecordingTransport()
        transport.responses.update(
            {
                (ControlAddress(EntityId.OUTPUT, 0, 0), 4): bytes.fromhex(
                    "0081ffff"
                ),
                (ControlAddress(EntityId.OUTPUT, 1, 0), 4): bytes.fromhex(
                    "01000000"
                ),
                (mixer_crosspoint(4, 2), 2): bytes.fromhex("80f3"),
            }
        )
        controller = Evo8Controller(transport)
        output = controller.read_output(0)
        self.assertEqual(output.volume_db, -127.0)
        self.assertTrue(output.muted)
        self.assertEqual(controller.read_mix_level(4, 2), -12.5)


if __name__ == "__main__":
    unittest.main()
