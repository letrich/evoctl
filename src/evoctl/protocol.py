"""Pure EVO/UAC2 protocol definitions.

This module has no USB or UI dependencies, which keeps request encoding easy
to test against captures and decompiler evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


AUDIENT_VENDOR_ID = 0x2708
EVO4_PRODUCT_ID = 0x0006
EVO8_PRODUCT_ID = 0x0007

UAC2_CUR = 0x01
UAC2_INTERFACE_OUT = 0x21
UAC2_INTERFACE_IN = 0xA1
EVO_AUDIOCONTROL_INTERFACE = 0


class EntityId(IntEnum):
    """Known EVO 8 AudioControl entity IDs."""

    ROUTING = 0x32
    MONO_MIX = 0x33
    SYSTEM = 0x39
    INPUT = 0x3A
    OUTPUT = 0x3B
    MIXER = 0x3C
    AUXILIARY = 0x3E


class InputSelector(IntEnum):
    PHANTOM_POWER = 0
    GAIN = 1
    MUTE = 2
    STEREO_LINK = 3
    UNKNOWN_FLAGS = 4
    UNKNOWN_GLOBAL = 5
    UNKNOWN_AUX = 7


class OutputSelector(IntEnum):
    VOLUME = 0
    MUTE = 1


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    name: str
    product_id: int
    input_count: int
    output_count: int
    mixer_source_count: int


EVO8 = DeviceProfile(
    name="EVO 8",
    product_id=EVO8_PRODUCT_ID,
    input_count=4,
    output_count=4,
    mixer_source_count=10,
)


@dataclass(frozen=True, slots=True)
class ControlAddress:
    """A UAC2 entity/control/channel address on AudioControl interface 0."""

    entity: int
    selector: int
    channel: int = 0
    interface: int = EVO_AUDIOCONTROL_INTERFACE

    def __post_init__(self) -> None:
        for name, value in (
            ("entity", self.entity),
            ("selector", self.selector),
            ("channel", self.channel),
            ("interface", self.interface),
        ):
            if not 0 <= int(value) <= 0xFF:
                raise ValueError(f"{name} must fit in one byte")

    @property
    def w_value(self) -> int:
        return (int(self.selector) << 8) | int(self.channel)

    @property
    def w_index(self) -> int:
        return (int(self.entity) << 8) | int(self.interface)


@dataclass(frozen=True, slots=True)
class ControlTransfer:
    request_type: int
    request: int
    address: ControlAddress
    payload: bytes = b""
    read_length: int = 0

    @classmethod
    def write(cls, address: ControlAddress, payload: bytes) -> ControlTransfer:
        return cls(UAC2_INTERFACE_OUT, UAC2_CUR, address, bytes(payload), 0)

    @classmethod
    def read(cls, address: ControlAddress, length: int) -> ControlTransfer:
        if length <= 0:
            raise ValueError("read length must be positive")
        return cls(UAC2_INTERFACE_IN, UAC2_CUR, address, b"", length)


def encode_q8_8(value_db: float, *, width: int) -> bytes:
    """Encode a signed dB value as little-endian Q8.8."""

    if width not in (2, 4):
        raise ValueError("Q8.8 controls use a 2- or 4-byte carrier")
    scaled = round(value_db * 256.0)
    minimum = -(1 << (width * 8 - 1))
    maximum = (1 << (width * 8 - 1)) - 1
    if not minimum <= scaled <= maximum:
        raise ValueError(f"{value_db} dB does not fit in {width} bytes")
    return int(scaled).to_bytes(width, "little", signed=True)


def decode_q8_8(payload: bytes) -> float:
    if len(payload) not in (2, 4):
        raise ValueError("Q8.8 controls use a 2- or 4-byte carrier")
    return int.from_bytes(payload, "little", signed=True) / 256.0


def encode_bool(value: bool) -> bytes:
    return int(bool(value)).to_bytes(4, "little", signed=False)


def encode_i32(value: int) -> bytes:
    return int(value).to_bytes(4, "little", signed=True)


def mixer_crosspoint(source: int, destination: int) -> ControlAddress:
    """Return the EVO 8 standard mixer-unit crosspoint address."""

    if not 0 <= source < EVO8.mixer_source_count:
        raise ValueError("source index is outside the EVO 8 mixer")
    if not 0 <= destination < EVO8.output_count:
        raise ValueError("destination index is outside the EVO 8 mixer")
    return ControlAddress(
        entity=EntityId.MIXER,
        selector=1,
        channel=source * EVO8.output_count + destination,
    )
