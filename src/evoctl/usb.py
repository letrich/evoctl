"""Minimal libusb transport for EVO class-interface control requests."""

from __future__ import annotations

import ctypes
import ctypes.util
from dataclasses import dataclass, field

from .protocol import (
    AUDIENT_VENDOR_ID,
    ControlAddress,
    ControlTransfer,
    DeviceProfile,
    EVO8,
)


class UsbError(RuntimeError):
    pass


class DeviceNotFoundError(UsbError):
    pass


class _LibUsb:
    def __init__(self) -> None:
        library = ctypes.util.find_library("usb-1.0")
        if not library:
            raise UsbError("libusb-1.0 could not be found")
        self.lib = ctypes.CDLL(library)

        self.lib.libusb_init.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        self.lib.libusb_init.restype = ctypes.c_int
        self.lib.libusb_exit.argtypes = [ctypes.c_void_p]
        self.lib.libusb_exit.restype = None
        self.lib.libusb_open_device_with_vid_pid.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint16,
            ctypes.c_uint16,
        ]
        self.lib.libusb_open_device_with_vid_pid.restype = ctypes.c_void_p
        self.lib.libusb_close.argtypes = [ctypes.c_void_p]
        self.lib.libusb_close.restype = None
        self.lib.libusb_kernel_driver_active.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.libusb_kernel_driver_active.restype = ctypes.c_int
        self.lib.libusb_detach_kernel_driver.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.libusb_detach_kernel_driver.restype = ctypes.c_int
        self.lib.libusb_attach_kernel_driver.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.libusb_attach_kernel_driver.restype = ctypes.c_int
        self.lib.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.libusb_claim_interface.restype = ctypes.c_int
        self.lib.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.lib.libusb_release_interface.restype = ctypes.c_int
        self.lib.libusb_control_transfer.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint8,
            ctypes.c_uint8,
            ctypes.c_uint16,
            ctypes.c_uint16,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_uint16,
            ctypes.c_uint,
        ]
        self.lib.libusb_control_transfer.restype = ctypes.c_int
        self.lib.libusb_error_name.argtypes = [ctypes.c_int]
        self.lib.libusb_error_name.restype = ctypes.c_char_p

    def error_name(self, code: int) -> str:
        value = self.lib.libusb_error_name(code)
        return value.decode("ascii", errors="replace") if value else str(code)


@dataclass(slots=True)
class EvoUsbTransport:
    """Diagnostic libusb transport; unsafe for normal desktop use.

    Linux usbfs requires ownership of AudioControl interface 0 for EVO class
    requests. Detaching that interface disconnects the shared ALSA card and can
    require a physical reconnect. Normal application code must use
    :class:`evoctl.kernel.EvoKernelTransport` instead. Driver detachment is
    disabled by default and must be explicitly opted into for diagnostics.
    """

    profile: DeviceProfile = EVO8
    timeout_ms: int = 1000
    control_interface: int = 0
    claim_control_interface: bool = True
    detach_kernel_driver: bool = False
    _api: _LibUsb = field(init=False, repr=False)
    _context: ctypes.c_void_p = field(init=False, repr=False)
    _handle: ctypes.c_void_p = field(init=False, repr=False)
    _interface_claimed: bool = field(init=False, repr=False)
    _kernel_driver_detached: bool = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._api = _LibUsb()
        self._context = ctypes.c_void_p()
        self._handle = ctypes.c_void_p()
        self._interface_claimed = False
        self._kernel_driver_detached = False

    @property
    def is_open(self) -> bool:
        return bool(self._handle.value)

    def open(self) -> None:
        if self.is_open:
            return
        result = self._api.lib.libusb_init(ctypes.byref(self._context))
        if result < 0:
            raise UsbError(f"libusb_init failed: {self._api.error_name(result)}")
        handle = self._api.lib.libusb_open_device_with_vid_pid(
            self._context,
            AUDIENT_VENDOR_ID,
            self.profile.product_id,
        )
        if not handle:
            self._api.lib.libusb_exit(self._context)
            self._context = ctypes.c_void_p()
            raise DeviceNotFoundError(
                f"{self.profile.name} ({AUDIENT_VENDOR_ID:04x}:"
                f"{self.profile.product_id:04x}) is unavailable or not permitted"
            )
        self._handle = ctypes.c_void_p(handle)
        if self.claim_control_interface:
            try:
                self._claim_interface()
            except Exception:
                self.close()
                raise

    def close(self) -> None:
        if self.is_open:
            if self._interface_claimed:
                self._api.lib.libusb_release_interface(
                    self._handle, self.control_interface
                )
                self._interface_claimed = False
            if self._kernel_driver_detached:
                self._api.lib.libusb_attach_kernel_driver(
                    self._handle, self.control_interface
                )
                self._kernel_driver_detached = False
            self._api.lib.libusb_close(self._handle)
            self._handle = ctypes.c_void_p()
        if self._context.value:
            self._api.lib.libusb_exit(self._context)
            self._context = ctypes.c_void_p()

    def __enter__(self) -> EvoUsbTransport:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _claim_interface(self) -> None:
        active = self._api.lib.libusb_kernel_driver_active(
            self._handle, self.control_interface
        )
        if active < 0:
            raise UsbError(
                "could not inspect the AudioControl kernel driver: "
                f"{self._api.error_name(active)}"
            )
        if active == 1:
            if not self.detach_kernel_driver:
                raise UsbError(
                    "snd-usb-audio owns AudioControl interface 0; "
                    "refusing to detach it because that disconnects the ALSA "
                    "card; install evo_raw and use EvoKernelTransport"
                )
            result = self._api.lib.libusb_detach_kernel_driver(
                self._handle, self.control_interface
            )
            if result < 0:
                raise UsbError(
                    "could not detach AudioControl interface 0: "
                    f"{self._api.error_name(result)}"
                )
            self._kernel_driver_detached = True

        result = self._api.lib.libusb_claim_interface(
            self._handle, self.control_interface
        )
        if result < 0:
            raise UsbError(
                "could not claim AudioControl interface 0: "
                f"{self._api.error_name(result)}"
            )
        self._interface_claimed = True

    def transfer(self, transfer: ControlTransfer) -> bytes:
        if not self.is_open:
            raise UsbError("USB transport is not open")

        if transfer.read_length:
            length = transfer.read_length
            buffer = (ctypes.c_ubyte * length)()
        else:
            length = len(transfer.payload)
            buffer = (ctypes.c_ubyte * length).from_buffer_copy(transfer.payload)

        result = self._api.lib.libusb_control_transfer(
            self._handle,
            transfer.request_type,
            transfer.request,
            transfer.address.w_value,
            transfer.address.w_index,
            buffer,
            length,
            self.timeout_ms,
        )
        if result < 0:
            raise UsbError(
                "control transfer "
                f"entity=0x{transfer.address.entity:02x} "
                f"selector={transfer.address.selector} "
                f"channel={transfer.address.channel} failed: "
                f"{self._api.error_name(result)}"
            )
        if result != length:
            raise UsbError(f"short control transfer: expected {length}, got {result}")
        return bytes(buffer[:result]) if transfer.read_length else b""

    def write(self, address: ControlAddress, payload: bytes) -> None:
        self.transfer(ControlTransfer.write(address, payload))

    def read(self, address: ControlAddress, length: int = 4) -> bytes:
        return self.transfer(ControlTransfer.read(address, length))
