from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from .controller import Evo8Controller
from .kernel import EvoKernelTransport, KernelTransportError
from .protocol import ControlAddress
from .ui import MainWindow


class DemoTransport:
    def __init__(self) -> None:
        self.writes: list[tuple[ControlAddress, bytes]] = []
        self.values: dict[ControlAddress, bytes] = {}

    def write(self, address: ControlAddress, payload: bytes) -> None:
        value = bytes(payload)
        self.writes.append((address, value))
        self.values[address] = value

    def read(self, address: ControlAddress, length: int = 4) -> bytes:
        value = self.values.get(address, b"")
        return value[:length].ljust(length, b"\0")


class UnavailableTransport:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def write(self, address: ControlAddress, payload: bytes) -> None:
        raise KernelTransportError(self.reason)

    def read(self, address: ControlAddress, length: int = 4) -> bytes:
        raise KernelTransportError(self.reason)


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

    device: EvoKernelTransport | None = None
    if args.demo:
        transport = DemoTransport()
        connected = True
        status = "DEMO MODE"
    else:
        device = EvoKernelTransport()
        try:
            device.open()
        except KernelTransportError as error:
            transport = UnavailableTransport(str(error))
            connected = False
            status = "EVO 8 OFFLINE"
        else:
            transport = device
            connected = True
            status = "EVO 8 CONNECTED"
            app.aboutToQuit.connect(device.close)

    window = MainWindow(Evo8Controller(transport), connected=connected, status_text=status)
    if connected and not args.demo:
        window.load_state()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
