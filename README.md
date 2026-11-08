# evoctl

`evoctl` is a native-feeling Linux control panel for Audient EVO audio
interfaces. The EVO 8 is the first supported device; the protocol and UI are
structured so EVO 4 and EVO 16 profiles can be added without duplicating the
transport layer.

The project is in active reverse-engineering and implementation. The current
milestone contains:

- a documented, byte-accurate UAC2 control-transfer model;
- an EVO 8 protocol profile for input, output, and mixer controls;
- a small `libusb` transport that does not detach the audio driver by default;
- a PySide6 control-panel shell with Inputs, Outputs, and Routing pages;
- a demo mode and protocol unit tests that do not touch hardware.

## Run the current UI

From the repository root:

```sh
PYTHONPATH=src python3 -m evoctl --demo
```

Omit `--demo` to open USB device `2708:0007`. The process needs permission to
open the corresponding `/dev/bus/usb` node. Hardware writes happen only after
an explicit UI change.

The current environment provides Python and libusb. PySide6 package metadata
is present, but the actual Qt bindings (including `PySide6.QtWidgets`) are not
installed, so the GUI cannot start until that dependency is added. No system
packages were installed while creating this project.

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
