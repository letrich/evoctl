# evoctl

`evoctl` is a native-feeling Linux control panel for Audient EVO audio
interfaces. The EVO 8 is the first supported device; the protocol and UI are
structured so EVO 4 and EVO 16 profiles can be added without duplicating the
transport layer.

The project is in active reverse-engineering and implementation. The current
milestone contains:

- a documented, byte-accurate UAC2 control-transfer model;
- an EVO 8 protocol profile for input, output, and mixer controls;
- an `evo_raw` kernel helper that provides control access without detaching
  `snd-usb-audio` or interrupting a DAW;
- a PySide6 mixer modeled on the official EVO 8 application workflow;
- a demo mode and protocol unit tests that do not touch hardware.

## Install dependencies

On Ubuntu or Debian, install the GUI binding and kernel-module build tools:

```sh
sudo apt update
sudo apt install python3-pyside6.qtwidgets build-essential \
  linux-headers-$(uname -r) dkms
```

DKMS is strongly recommended because it automatically rebuilds the helper
after kernel updates. The installer can work without it for the current kernel,
but must then be run again after every kernel update.

Verify the GUI binding:

```sh
python3 -c 'from PySide6.QtWidgets import QApplication; print("PySide6 QtWidgets: OK")'
```

No third-party Python USB package is required.

## Install concurrent device control

Linux usbfs cannot issue EVO class-interface requests while `snd-usb-audio`
owns AudioControl interface 0. Detaching that interface disconnects the shared
ALSA card, makes the EVO unavailable to a DAW, and may require a physical USB
reconnect. evoctl therefore does not detach it.

Instead, the included `evo_raw` helper binds only the otherwise-unused DFU
interface 3 and exposes `/dev/evo8`. AudioControl and both streaming interfaces
remain continuously owned by `snd-usb-audio`.

Build, install, and load the helper with:

```sh
sudo packaging/evo_raw/install.sh
```

The script also installs the udev rule for members of the `dialout` group. If
your account is not already a member, add it and then log out and back in:

```sh
sudo usermod -aG dialout "$USER"
```

Confirm that both the safe control device and normal ALSA device exist:

```sh
ls -l /dev/evo8
aplay -l | grep -A2 EVO8
PYTHONPATH=src python3 - <<'PY'
from evoctl.kernel import EvoKernelTransport

with EvoKernelTransport():
    print("EVO 8 concurrent control access: OK")
PY
```

Opening `/dev/evo8` for this check does not issue a control read or write and
does not disturb ALSA, PipeWire, JACK, or an active DAW. Uninstall the helper
with `sudo packaging/evo_raw/uninstall.sh`.

## Run the mixer

From the repository root:

```sh
PYTHONPATH=src python3 -m evoctl --demo
```

Omit `--demo` to open `/dev/evo8`. Hardware writes happen only after an explicit
UI change. On startup, the UI reads the current input, output, and mixer state
without taking the interface away from the DAW.

The main window follows the official EVO Mixer workflow instead of presenting
the 10×4 hardware matrix directly:

- Mic 1–4, DAW 1+2, DAW 3+4, and Loop-back 1+2 appear as mixer strips;
- Outputs 1+2 is the green-accented Master Mix;
- `Setup > Enable Artist Mix` enables the independent, yellow-accented mix for
  Outputs 3+4;
- `View > Show Mic Pre Controls` adds gain, 48 V, and the applicable instrument
  control to the microphone strips.

Mixer faders and pan controls are backed by the EVO 8 mixer-unit crosspoints;
the matrix is an implementation detail and is not shown as a separate routing
page. Signal meters are visual placeholders until the device's live metering
transport has been recovered, so they do not yet display audio levels.
Demo mode keeps an in-memory device state, so control values persist when
switching between Master Mix and Artist Mix.

## Tests

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Safety and project status

Normal mixer and preamp controls use USB Audio Class 2 `CUR` requests. Firmware
update and DFU operations are deliberately out of scope until they have a
separate, guarded implementation. Controls whose meaning is not yet proven are
kept out of the UI. Although `evo_raw` binds the otherwise-unused DFU interface,
it sends normal endpoint-zero control requests only and contains no DFU or
firmware-update implementation.

See [docs/reverse-engineering.md](docs/reverse-engineering.md) for evidence,
known control IDs, and remaining work.
