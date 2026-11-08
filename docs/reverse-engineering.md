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

The execution sandbox can read sysfs descriptors but does not expose
`/dev/bus/usb` or `/dev/snd`, so live transfers cannot yet be issued from this
process.

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
sent with libusb on Linux.

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
| auxiliary extension unit | `0x3e` | observed; role still under analysis |

### Input control (`0x3a`)

The Windows model polls selectors 0, 1, 2, 3, 4, 5, and 7 for each input.
The first four meanings are established by model serialization and UI binding:

| Selector | Meaning | Channel | Payload |
|---:|---|---|---|
| 0 | phantom power | input index, zero-based | 32-bit boolean |
| 1 | preamp gain | input index, zero-based | signed Q8.8 in 32 bits |
| 2 | input mute | input index, zero-based | 32-bit boolean |
| 3 | stereo link | input index, zero-based | 32-bit boolean |
| 4 | unknown per-input flags | input index | 32-bit bit field |
| 5 | unknown global input state | channel 0 | 32-bit value |
| 7 | unknown per-input state | input index | 32-bit value |

Evidence: `ev_a2d8f6651adc3a93d645b27d2745c193c7cb06352eff929106e408f2f981b156`
and `ev_1c8e398811ec1bc702e301bca4f585c1ed2d81d26c02560545b5b4228c35779a`.

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
implementation.

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
