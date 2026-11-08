from __future__ import annotations

import struct
import unittest
from unittest.mock import MagicMock, patch

from evoctl.kernel import (
    EVO_CTRL_TRANSFER,
    EvoKernelTransport,
    KernelTransportError,
    _XFER_FORMAT,
    _XFER_SIZE,
)
from evoctl.protocol import ControlAddress, EntityId, InputSelector


class KernelTransportTests(unittest.TestCase):
    def test_ioctl_number_matches_kernel_struct(self) -> None:
        self.assertEqual(_XFER_SIZE, 264)
        self.assertEqual((EVO_CTRL_TRANSFER >> 30) & 0x3, 3)
        self.assertEqual((EVO_CTRL_TRANSFER >> 16) & 0x3FFF, _XFER_SIZE)
        self.assertEqual((EVO_CTRL_TRANSFER >> 8) & 0xFF, ord("E"))
        self.assertEqual(EVO_CTRL_TRANSFER & 0xFF, 0)

    @patch("evoctl.kernel.open")
    def test_open_does_not_touch_usb_interfaces(self, open_mock: MagicMock) -> None:
        device = MagicMock()
        open_mock.return_value = device
        transport = EvoKernelTransport()
        transport.open()
        open_mock.assert_called_once_with("/dev/evo8", "rb", buffering=0)
        transport.close()
        device.close.assert_called_once_with()

    @patch("evoctl.kernel.open", side_effect=FileNotFoundError)
    def test_missing_helper_has_install_message(self, _open_mock: MagicMock) -> None:
        with self.assertRaisesRegex(KernelTransportError, "evo_raw"):
            EvoKernelTransport().open()

    @patch("evoctl.kernel.fcntl.ioctl")
    @patch("evoctl.kernel.open")
    def test_write_packs_setup_and_payload(
        self, open_mock: MagicMock, ioctl_mock: MagicMock
    ) -> None:
        open_mock.return_value = MagicMock()
        address = ControlAddress(EntityId.INPUT, InputSelector.PHANTOM_POWER, 2)
        with EvoKernelTransport() as transport:
            transport.write(address, bytes.fromhex("01000000"))

        _, command, buffer = ioctl_mock.call_args.args
        self.assertEqual(command, EVO_CTRL_TRANSFER)
        request_type, request, value, index, length, payload = struct.unpack(
            _XFER_FORMAT, buffer
        )
        self.assertEqual((request_type, request), (0x21, 1))
        self.assertEqual((value, index), (0x0002, 0x3A00))
        self.assertEqual(length, 4)
        self.assertEqual(payload[:4], bytes.fromhex("01000000"))

    @patch("evoctl.kernel.fcntl.ioctl")
    @patch("evoctl.kernel.open")
    def test_read_returns_kernel_response(
        self, open_mock: MagicMock, ioctl_mock: MagicMock
    ) -> None:
        open_mock.return_value = MagicMock()

        def respond(_device: object, _command: int, buffer: bytearray) -> None:
            request_type, request, value, index, _, _ = struct.unpack(
                _XFER_FORMAT, buffer
            )
            buffer[:] = struct.pack(
                _XFER_FORMAT,
                request_type,
                request,
                value,
                index,
                4,
                bytes.fromhex("00f8ffff").ljust(256, b"\0"),
            )

        ioctl_mock.side_effect = respond
        address = ControlAddress(EntityId.INPUT, InputSelector.GAIN, 0)
        with EvoKernelTransport() as transport:
            self.assertEqual(transport.read(address, 4), bytes.fromhex("00f8ffff"))


if __name__ == "__main__":
    unittest.main()
