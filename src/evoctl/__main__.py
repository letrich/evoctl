from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from .controller import Evo8Controller
from .protocol import ControlAddress
from .ui import MainWindow
from .usb import DeviceNotFoundError, EvoUsbTransport, UsbError


class DemoTransport:
    def __init__(self) -> None:
        self.writes: list[tuple[ControlAddress, bytes]] = []

    def write(self, address: ControlAddress, payload: bytes) -> None:
        self.writes.append((address, bytes(payload)))

    def read(self, address: ControlAddress, length: int = 4) -> bytes:
        return bytes(length)


class UnavailableTransport:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def write(self, address: ControlAddress, payload: bytes) -> None:
        raise UsbError(self.reason)

    def read(self, address: ControlAddress, length: int = 4) -> bytes:
        raise UsbError(self.reason)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audient EVO control panel for Linux")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="show the complete interface without opening USB hardware",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("evoctl")
    app.setOrganizationName("evoctl")

    usb: EvoUsbTransport | None = None
    if args.demo:
        transport = DemoTransport()
        connected = True
        status = "DEMO MODE"
    else:
        usb = EvoUsbTransport()
        try:
            usb.open()
        except (DeviceNotFoundError, UsbError) as error:
            transport = UnavailableTransport(str(error))
            connected = False
            status = "EVO 8 OFFLINE"
        else:
            transport = usb
            connected = True
            status = "EVO 8 CONNECTED"
            app.aboutToQuit.connect(usb.close)

    window = MainWindow(Evo8Controller(transport), connected=connected, status_text=status)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
