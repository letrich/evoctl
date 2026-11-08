# Reverse-engineering ledger

This document separates observations from inferences. It is updated as the
Windows application and live hardware provide more evidence.

## Targets

Primary installer:

- file: `EVO-v4.4.0a.exe`
- SHA-256: `5a08a609e989ea49556fdfae152189934e8c32812842f42a50720c97707b19c7`
- packaging: 32-bit NSIS 3 Unicode self-extracting installer

The installer contains two native EVO applications under the same logical
path. They must be extracted with duplicate auto-renaming enabled.

- x86-64 application SHA-256:
  `6c77c84438b894b78221582eb4dda1ee9e612442a7fb04568fa6beb458493faa`
- x86 application SHA-256:
  `d49e1189062c61e2bf672b5b9edd0688a8c705f684c5a059933eea7309c0ce15`

The older installer is retained as fallback evidence and has not been
reverse-engineered.

## Connected device observations

The connected interface enumerates as:

- USB VID/PID: `2708:0007`
- manufacturer/product: `Audient` / `EVO8`
- device revision: `0x014c`
- USB 2.0, 480 Mbit/s, active configuration 1
- interfaces 0-2: USB Audio Class 2, bound to `snd-usb-audio`
- interface 3: USB DFU class, intentionally not used by normal controls

Opening the usbfs device alone is insufficient: class-interface reads return
`LIBUSB_ERROR_IO` while `snd-usb-audio` owns AudioControl interface 0.
Temporarily detaching and claiming interface 0 makes those reads succeed, but
runtime testing contradicted the initial cleanup assumption: detaching the
AudioControl interface disconnects the shared ALSA card. Reattaching interface
0 restores its sysfs driver link but does not reliably reconstruct the card for
a running DAW; a physical USB reconnect may be required. The application no
longer uses this transport.

Changing the request recipient from interface (`0xa1`) to device, endpoint, or
other (`0xa0`, `0xa2`, or `0xa3`) while leaving the kernel driver bound was
tested read-only. The firmware rejected all three variants with a control-pipe
stall, so changing request type is not a safe bypass.

The safe transport uses the included `evo_raw` helper. It binds only unused DFU
interface 3 to obtain the kernel `usb_device` handle, then forwards normal UAC2
endpoint-zero requests with `usb_control_msg()`. Interfaces 0–2 remain owned by
`snd-usb-audio`; the helper does not send DFU requests. The design was derived
from the public-domain `vanzaho/audient-evo-py` implementation and hardened with
reference-counted unplug/open-file lifetime handling.

Live concurrency verification on kernel `7.0.0-38-generic` established:

- `evo_raw` owned interface 3 while `snd-usb-audio` continuously owned
  interfaces 0–2;
- a six-channel, 48 kHz, signed-32-bit ALSA playback stream remained active
  while the control panel loaded hardware state and performed an idempotent
  Input 1 gain write;
- a six-channel ALSA capture stream remained active during an output-state
  control read;
- playback reopened immediately after the control panel closed, with no USB
  reconnect and no driver rebind.

The first live read-only snapshot established:

- all four input selector-1 values decoded to `-8.0 dB`, matching ALSA's
  `Mic Playback Volume` minimum;
- phantom, mute, and stereo-link selectors were false on all four inputs;
- all four output selector-0 values decoded to `-127.0 dB`, with mute false;
- all 40 mixer-unit crosspoints were readable as signed 16-bit Q8.8;
- no control write was issued during the snapshot;
- subsequent idempotent writes of the current input-gain, output-volume, and
  mixer-crosspoint values all read back unchanged, covering both 32-bit and
  16-bit payload paths without changing effective device state;
- an idempotent selector-4 write on Input 1 preserved both the complete input
  state and the other mode-flag bits, then `snd-usb-audio` was reattached.

## Control-transfer format (observed)

Native decompilation of the x86-64 Windows application establishes the exact
normal-control request construction:

| Direction | bmRequestType | bRequest | wValue | wIndex |
|---|---:|---:|---|---|
| Write | `0x21` | `0x01` (`CUR`) | `selector << 8 | channel` | `entity << 8 | interface` |
| Read | `0xa1` | `0x01` (`CUR`) | `selector << 8 | channel` | `entity << 8 | interface` |

The EVO 8 uses AudioControl interface 0, so the low byte of `wIndex` is zero.
Most Audient extension-unit values are signed 32-bit little-endian Q8.8.
Standard mixer crosspoints are signed 16-bit little-endian Q8.8.

Relevant REA evidence IDs from the primary application:

- application overview: `ev_fb0c6f977eaf26bddba0727853c83503594b504267170cf38c73f343f3d436e6`
- Windows driver API loader: `ev_337fb6dc3f210a20025a2f93d67ef70a27ad665638af4553a0ff16f02cf8c184`
- request-OUT construction: `ev_1e743e6f2b710aa54bb4d78e69f5be9bc23512a65d2a91460b7e65f9bb2ebd78`
- request-IN construction: `ev_cef464d914c3ed4dc208f78d3423aa49ab382021be1c49ce10edb0324d363090`
- setup-packet builder: `ev_14f780919042a409fae7902d2f3287021a348bf0dd3aaffce316cc6c36371c6d`

The Windows program dynamically loads Thesycon's `TUSBAUDIO_*` API, including
`AudioControlRequestSet` and `AudioControlRequestGet`. This API is only a
Windows transport wrapper; the on-wire request is standard UAC2 and can be
sent through the Linux kernel helper without detaching the audio driver.

## EVO 8 entities and controls

The device descriptors and application code expose these entity IDs:

| Entity | ID | Status |
|---|---:|---|
| routing extension unit | `0x32` | class identity inferred; mapping still under analysis |
| mono-mix extension unit | `0x33` | class identity inferred; mapping still under analysis |
| system control extension unit | `0x39` | identity inferred; controls still under analysis |
| input control extension unit | `0x3a` | observed in application and historical captures |
| output control extension unit | `0x3b` | observed in application and historical captures |
| standard mixer unit | `0x3c` | observed in descriptors and historical captures |
| optional auxiliary helper | `0x3e` | looked up by generic app code; absent from the connected EVO 8 descriptors |

The generic Windows application also contains optional models for a blend
mixer at entity `0x38` and a monitor controller at entity `0x36`. Neither
entity occurs in the connected EVO 8's active descriptor graph, so these are
not treated as EVO 8 controls. Static Evidence IDs:
`ev_4ec785b4eb0ca50d100bc6ae6dcfcc4ad13c49a82a02866dfebd169abad9d759`
and `ev_c4670e2389ae3a2f1781ee8242b12871bcde6c2fad8ebd3f5c152c4ece9da24b`.

### Input control (`0x3a`)

The Windows model polls selectors 0, 1, 2, 3, 4, 5, and 7 for each input.
The first four meanings are established by model serialization and UI binding:

| Selector | Meaning | Channel | Payload |
|---:|---|---|---|
| 0 | phantom power | input index, zero-based | 32-bit boolean |
| 1 | preamp gain | input index, zero-based | signed Q8.8 in 32 bits |
| 2 | input mute | input index, zero-based | 32-bit boolean |
| 3 | stereo link | input index, zero-based | 32-bit boolean |
| 4 | mode flags: bit 0 instrument, bit 1 Smartgain selection | input index | 32-bit bit field |
| 5 | global Smartgain state; enum meanings still under analysis | channel 0 | 32-bit value |
| 7 | unknown per-input state | input index | 32-bit value |

Evidence: `ev_a2d8f6651adc3a93d645b27d2745c193c7cb06352eff929106e408f2f981b156`
and `ev_1c8e398811ec1bc702e301bca4f585c1ed2d81d26c02560545b5b4228c35779a`.
Instrument/Smartgain flag recovery is corroborated by
`ev_357563ac4df81ee70f2b9ccd9f83980fc7c010fd0f39ef11705019d03399d34d`.
The common application model carries the flag per input, while the EVO 8 UI
exposes instrument mode only for Input 1, matching the device's single front
JFET instrument input.

### Output control (`0x3b`)

The Windows model polls selector 0 and selector 1 for every output channel.
Historical captures identify selector 0 as output volume; UI behavior identifies
selector 1 as mute.

| Selector | Meaning | Payload |
|---:|---|---|
| 0 | output volume | signed Q8.8 in 32 bits |
| 1 | output mute | 32-bit boolean |

Evidence: `ev_1289d88f0dd7d5bfd94c2be2f30a3f6c58af23bc74493775fd023ec0ae928d05`
and `ev_3da179ed243fec3dd8c5bc144abaf180c03c8181be81fea652d88a1f440dc681`.

### Mixer unit (`0x3c`)

The EVO 8 exposes 10 sources and 4 destinations. Crosspoint `wValue` values
run from `0x0100` through `0x0127`, source-major and destination-minor:

```text
wValue = 0x0100 | (source_index * 4 + destination_index)
```

The payload is signed 16-bit little-endian Q8.8 dB. `-128 dB` is treated as
off. This layout is corroborated by the upstream `evoctl` packet capture and
implementation, and all 40 addresses were read successfully from the connected
EVO 8. The Linux UI does not expose this transport representation directly.

## Official mixer user experience

The Windows binary remains the authority for control semantics. Audient's
official EVO 8 mixer documentation and screenshots are used as the visual and
workflow reference: the user works with source channel strips and a selected
output mix, not a raw crosspoint table.

The reconstructed EVO 8 mixer therefore groups the ten matrix sources as four
mono microphone strips and three stereo strips (DAW 1+2, DAW 3+4, and
Loop-back 1+2). Destinations 0–1 form the green Master Mix for Outputs 1+2;
destinations 2–3 form the optional yellow Artist Mix for Outputs 3+4. Mic preamp
controls are revealed from the View menu, and Artist Mix is enabled from the
Setup menu, matching the official interaction model.

Reference: <https://docs.audient.com/evo8/evo-mixer-configurations/>

### Meter update path

The official binary's `MeterUpdateService` periodically notifies input-channel
models. Those models convert normalized mixer-node values to dB and deliver
floating-point meter and clip events to the channel components. Static and
live control-selector scans did not establish a dedicated EVO USB control for
these rapidly changing values; the meter path is distinct from gain, mute, and
mix-level control readback.

On Linux, evoctl first obtains level data by passively observing the EVO's
already-active isochronous URBs through the kernel usbmon binary ABI. It filters
the selected bus to the current EVO device address, playback endpoint `0x01`
submissions, and capture endpoint `0x82` completions. It does not claim a USB
interface or open an ALSA PCM, so direct ALSA remains exclusively owned by the
DAW. PipeWire/Pulse capture remains an optional fallback when usbmon is not
available. The usbmon ABI and its security boundary are documented by the
Linux kernel: <https://docs.kernel.org/usb/usbmon.html>.

The captured streams are pre-mixer source samples. evoctl applies the selected
mix's fader, pan, mute, and solo state to channel indications. It reconstructs
master L/R from those post-fader peaks and applies output volume and mute. The
master value is exact for a single source and a power-sum estimate for multiple
simultaneous sources; phase relationships and final internal DSP samples are
not exposed by the device stream.

### Settings ownership and startup restore

The official application contains EVO 8-specific settings serialiser and
deserialiser classes as well as preset import/export UI. Its window-opening
path explicitly warns that the software mixer will load previous settings and
override the hardware monitor-mix value. Static evidence:
`ev_eaea66ddfd3a1ab1ad8030f709011baa4085a9ef523d4b16b4cecf38612c0774`
and `ev_a255038d6e494dc7e8b43c64282f39acf07091510ad81fdf99e2f0b1815d5d6d`.

evoctl mirrors that boundary. Raw input/output controls are read from the
device, while mixer workflow state is stored locally and restored to the EVO
mixer crosspoints on startup. This is necessary because mute and solo are
application semantics represented by temporary crosspoint attenuation; the
underlying fader value cannot be reconstructed from a muted crosspoint alone.

## Internal classes observed in the Windows application

RTTI and decompilation identify dedicated classes for:

- `UacXUAudientRoutingMatrix`
- `UacXUAudientMonoMixController`
- `UacXUAudientMonitorController`
- `UacXUAudientBlendMixer`
- `UacXUAudientInputControl`
- `UacXUAudientOutputControl`
- `UacXUAudientSystemControl`

Product definitions for EVO 4, EVO 8, and the rack device (EVO 16) are present
in the same application. EVO 8 remains the implementation priority.

## Next protocol work

1. Recover the routing, mono-mix, system, and auxiliary selector maps.
2. Expose readback and interrupt-notification synchronization.
3. Test class-interface control transfers without detaching `snd-usb-audio`.
4. Compare live readback values with physical knob/button changes.
5. Add guarded EVO 4/EVO 16 profiles only after EVO 8 behavior is verified.

DFU and firmware-update functions are not part of normal mixer control and are
not called by this implementation.
