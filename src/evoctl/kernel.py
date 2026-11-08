"""Safe EVO control transport through the evo_raw kernel helper."""

from __future__ import annotations

import fcntl
import os
import struct
from dataclasses import dataclass, field
from typing import BinaryIO

from .protocol import ControlAddress, ControlTransfer


EVO_MAX_DATA = 256
_XFER_FORMAT = f"<BBHHH{EVO_MAX_DATA}s"
_XFER_SIZE = struct.calcsize(_XFER_FORMAT)

# Linux _IOWR('E', 0, struct evo_ctrl_xfer).
_IOC_READ = 2
_IOC_WRITE = 1
EVO_CTRL_TRANSFER = (
    ((_IOC_READ | _IOC_WRITE) << 30)
    | (_XFER_SIZE << 16)
    | (ord("E") << 8)
)


class KernelTransportError(RuntimeError):
    pass


@dataclass(slots=True)
class EvoKernelTransport:
    """Issue endpoint-zero requests without detaching ``snd-usb-audio``.

    The ``evo_raw`` helper binds only the otherwise-unused DFU interface 3 and
    forwards control requests inside the kernel. AudioControl and streaming
    interfaces remain owned by ``snd-usb-audio`` for the whole application
    lifetime, so a DAW can use the EVO concurrently.
    """

    device_path: str = "/dev/evo8"
    _device: BinaryIO | None = field(init=False, default=None, repr=False)

    @property
    def is_open(self) -> bool:
        return self._device is not None

    def open(self) -> None:
        if self.is_open:
            return
        try:
            self._device = open(self.device_path, "rb", buffering=0)
        except FileNotFoundError as error:
            raise KernelTransportError(
                f"{self.device_path} is missing; install and load the evo_raw "
                "kernel helper as described in README.md"
            ) from error
        except PermissionError as error:
            raise KernelTransportError(
                f"permission denied for {self.device_path}; install the evoctl "
                "udev rule and log in again after joining dialout"
            ) from error
        except OSError as error:
            raise KernelTransportError(
                f"could not open {self.device_path}: {error.strerror or error}"
            ) from error

    def close(self) -> None:
        if self._device is not None:
            self._device.close()
            self._device = None

    def __enter__(self) -> EvoKernelTransport:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def transfer(self, transfer: ControlTransfer) -> bytes:
        if self._device is None:
            raise KernelTransportError("kernel transport is not open")

        if transfer.read_length:
            length = transfer.read_length
            payload = bytes(EVO_MAX_DATA)
        else:
            length = len(transfer.payload)
            payload = transfer.payload.ljust(EVO_MAX_DATA, b"\0")

        if not 0 < length <= EVO_MAX_DATA:
            raise ValueError(f"control payload length must be in 1..{EVO_MAX_DATA}")

        buffer = bytearray(
            struct.pack(
                _XFER_FORMAT,
                transfer.request_type,
                transfer.request,
                transfer.address.w_value,
                transfer.address.w_index,
                length,
                payload,
            )
        )
        try:
            fcntl.ioctl(self._device, EVO_CTRL_TRANSFER, buffer)
        except OSError as error:
            raise KernelTransportError(
                "control transfer "
                f"entity=0x{transfer.address.entity:02x} "
                f"selector={transfer.address.selector} "
                f"channel={transfer.address.channel} failed: "
                f"{error.strerror or os.strerror(error.errno)}"
            ) from error

        if not transfer.read_length:
            return b""

        _, _, _, _, response_length, response = struct.unpack(
            _XFER_FORMAT, buffer
        )
        if response_length != length:
            raise KernelTransportError(
                f"short control transfer: expected {length}, got {response_length}"
            )
        return bytes(response[:response_length])

    def write(self, address: ControlAddress, payload: bytes) -> None:
        self.transfer(ControlTransfer.write(address, payload))

    def read(self, address: ControlAddress, length: int = 4) -> bytes:
        return self.transfer(ControlTransfer.read(address, length))
