# evoctl

`evoctl` is a native-feeling Linux control panel for Audient EVO audio
interfaces. The EVO 8 is the first supported device; the protocol and UI are
structured so EVO 4 and EVO 16 profiles can be added without duplicating the
transport layer.

The project is in active reverse-engineering and implementation. The current
milestone contains:

- a documented, byte-accurate UAC2 control-transfer model;
- an EVO 8 protocol profile for input, output, and mixer controls;
- a `libusb` transport that claims only AudioControl interface 0 and restores
  `snd-usb-audio` when it closes;
- a PySide6 control-panel shell with Inputs, Outputs, and Routing pages;
- a demo mode and protocol unit tests that do not touch hardware.

## Install dependencies

On Ubuntu or Debian, install the PySide6 QtWidgets binding. Its package
dependencies provide the matching QtCore and QtGui bindings:

```sh
sudo apt update
sudo apt install python3-pyside6.qtwidgets
```

Verify the GUI binding:

```sh
python3 -c 'from PySide6.QtWidgets import QApplication; print("PySide6 QtWidgets: OK")'
```

No third-party Python USB package is required. The transport loads the system
`libusb-1.0` library directly.

## Grant USB access

The EVO 8 enumerates as USB device `2708:0007`. Install the included udev rule
to grant control-transfer access to the active desktop user and members of the
`plugdev` group:

```sh
sudo install -Dm644 packaging/udev/60-evoctl.rules \
  /etc/udev/rules.d/60-evoctl.rules
sudo udevadm control --reload-rules
```

Disconnect and reconnect the EVO 8 after reloading the rules. A reboot is not
required. Confirm that the device is present and that evoctl can open it:

```sh
lsusb -d 2708:0007
PYTHONPATH=src python3 - <<'PY'
from evoctl.usb import EvoUsbTransport

with EvoUsbTransport():
    print("EVO 8 USB access: OK")
PY
```

Opening the device for this check does not issue a control read or write. Linux
requires evoctl to detach and claim AudioControl interface 0 while the process
is open; the streaming interfaces are not detached, and `snd-usb-audio` is
reattached when the transport closes. If access is still denied, confirm
membership with `id -nG`; log out and back in after adding yourself to
`plugdev`.

## Run the current UI

From the repository root:

```sh
PYTHONPATH=src python3 -m evoctl --demo
```

Omit `--demo` to open USB device `2708:0007`. The process needs permission to
open the corresponding `/dev/bus/usb` node. Hardware writes happen only after
an explicit UI change. On startup, the UI reads the current input, output, and
routing state from the interface.

## Tests

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Safety and project status

Normal mixer and preamp controls use USB Audio Class 2 `CUR` requests. Firmware
update and DFU operations are deliberately out of scope until they have a
separate, guarded implementation. Controls whose meaning is not yet proven are
kept out of the UI.

See [docs/reverse-engineering.md](docs/reverse-engineering.md) for evidence,
known control IDs, and remaining work.
