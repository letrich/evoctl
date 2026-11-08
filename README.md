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

No third-party Python USB or audio package is required. If `pactl` and `parec`
are already installed, evoctl can also use PipeWire/Pulse as an automatic
meter fallback, but direct ALSA is fully supported and remains the preferred
low-latency DAW path.

## Install concurrent device control

Linux usbfs cannot issue EVO class-interface requests while `snd-usb-audio`
owns AudioControl interface 0. Detaching that interface disconnects the shared
ALSA card, makes the EVO unavailable to a DAW, and may require a physical USB
reconnect. evoctl therefore does not detach it.

Instead, the included `evo_raw` helper binds only the otherwise-unused DFU
interface 3 and exposes `/dev/evo8`. AudioControl and both streaming interfaces
remain continuously owned by `snd-usb-audio`.

The installer also loads the kernel's standard `usbmon` module and grants the
`dialout` group read-only access to the monitor for the USB bus where the EVO 8
is connected. evoctl filters that passive stream to the EVO's current device
address and audio endpoints, calculates peaks in memory, and stores no audio.
It does not open a PCM, so REAPER can continue to own direct ALSA capture and
playback exclusively. Access to a bus monitor can expose traffic from other USB
devices on the same bus; the rule deliberately grants only the EVO's bus, not
`usbmon0` or every USB bus.

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
ls -l /dev/usbmon*
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

Omit `--demo` to open `/dev/evo8`. On first use, hardware writes happen only
after an explicit UI change. Once local mixer state has been saved, it is sent
back to the EVO matrix at startup, matching the official application's restore
behavior. The UI reads current input and output state without taking the
interface away from the DAW. While it is open, the app reads the input and
selected-output controls five times per second, so changes made with the EVO 8
buttons and encoder appear in the UI without reopening it.

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
page. Mono strips have one pan control. As in the official mixer, paired stereo
strips have independent `LEFT` and `RIGHT` pan controls (hard-left and
hard-right by default) and one shared fader. All four stereo crosspoints are
written, so either source can be placed anywhere in the selected output mix.

The apparent fader range also follows the official application. The device
range is −128 to +6 dB, but the slider uses the recovered 179-step audio taper
instead of spacing that range linearly: it moves in 6 dB steps near silence,
then becomes progressively finer, reaching 0.2 dB steps around unity. The pan
law is the official −6 dB-centre curve rather than a linear dB approximation.

Signal meters passively observe the EVO 8 USB audio packets through the
read-only bus monitor. Direct ALSA remains exclusively owned by the DAW; the
control panel neither opens nor duplicates its PCM streams. The playback meters
reflect audio sent from the DAW to the EVO. Direct-monitor audio mixed only
inside the hardware is not present in that playback stream.

Channel meters are post-fader for the selected mix: fader, pan, mute, and solo
all affect the indication. A stereo strip's two meters show its panned L/R mix,
including crossfeed when either channel is moved away from its default side.
The master L/R meter combines the active source levels and then applies the
selected output volume and mute. With one active source its dB movement is
exact; with several simultaneous sources the master uses a power-sum estimate
because the EVO does not expose its final internal DSP samples to the host.

evoctl automatically stores application-level mixer state in
`~/.config/evoctl/evoctl.conf`. On the next start it restores the selected mix,
Artist Mix and preamp-view state, faders, pan, mute, and solo, and sends saved
mixer levels back to the EVO matrix. Preamp gain, 48 V, instrument mode, output
volume, and output mute are read from the device instead, so physical controls
remain authoritative. Demo mode uses the same local application settings and
also keeps an in-memory device state while it is running.

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
