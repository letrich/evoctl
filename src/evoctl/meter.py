"""Non-exclusive EVO audio metering through the PipeWire/Pulse graph."""

from __future__ import annotations

from array import array
import ctypes
from dataclasses import dataclass
import errno
import fcntl
import math
import os
from pathlib import Path
import select
import shutil
import struct
import subprocess
import sys
from threading import Event, Lock, Thread
import time


SILENCE_DB = -128.0
_USBMON_HEADER = struct.Struct("<QBBBBHccqiiII8siiII")
_USBMON_GETX = (1 << 30) | (24 << 16) | (0x92 << 8) | 10
_ISO_DESCRIPTOR = struct.Struct("<iIII")


@dataclass(frozen=True, slots=True)
class MeterSnapshot:
    capture: tuple[float, ...]
    playback: tuple[float, ...]
    capture_seen: bool
    playback_seen: bool


def peak_db(interleaved: array[float], channels: int) -> tuple[float, ...]:
    """Return the peak dBFS value for each channel in interleaved audio."""
    peaks = [0.0] * channels
    for index, sample in enumerate(interleaved):
        channel = index % channels
        magnitude = abs(sample)
        if magnitude > peaks[channel]:
            peaks[channel] = magnitude
    return tuple(
        max(SILENCE_DB, 20.0 * math.log10(value)) if value else SILENCE_DB
        for value in peaks
    )


def s32le_peak_db(payload: bytes, channels: int) -> tuple[float, ...]:
    """Return channel peaks for signed 32-bit little-endian PCM."""
    usable = len(payload) - len(payload) % (channels * 4)
    samples = array("i")
    samples.frombytes(payload[:usable])
    if sys.byteorder != "little":
        samples.byteswap()
    peaks = []
    for channel in range(channels):
        channel_samples = samples[channel::channels]
        if channel_samples:
            peaks.append(max(max(channel_samples), -min(channel_samples)))
        else:
            peaks.append(0)
    return tuple(
        max(SILENCE_DB, 20.0 * math.log10(value / 2**31))
        if value
        else SILENCE_DB
        for value in peaks
    )


def extract_iso_payload(raw: bytes, descriptor_count: int) -> bytes:
    """Remove usbmon ISO descriptors and compact sparse transfer data."""
    descriptor_bytes = descriptor_count * _ISO_DESCRIPTOR.size
    if descriptor_count <= 0 or descriptor_bytes > len(raw):
        return b""
    transfer = raw[descriptor_bytes:]
    chunks: list[bytes] = []
    for index in range(descriptor_count):
        _status, offset, length, _padding = _ISO_DESCRIPTOR.unpack_from(
            raw, index * _ISO_DESCRIPTOR.size
        )
        end = offset + length
        if length and end <= len(transfer):
            chunks.append(transfer[offset:end])
    return b"".join(chunks)


def find_evo_usb_device(
    root: Path = Path("/sys/bus/usb/devices"),
) -> tuple[int, int] | None:
    """Return the bus and current device address for the connected EVO 8."""
    try:
        devices = root.iterdir()
    except OSError:
        return None
    for device in devices:
        try:
            if (device / "idVendor").read_text().strip().lower() != "2708":
                continue
            if (device / "idProduct").read_text().strip().lower() != "0007":
                continue
            return (
                int((device / "busnum").read_text().strip()),
                int((device / "devnum").read_text().strip()),
            )
        except (OSError, ValueError):
            continue
    return None


def find_evo_sources(output: str) -> tuple[str | None, str | None]:
    """Find the EVO capture source and playback-monitor source in pactl output."""
    capture = None
    playback = None
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            fields = line.split()
        if len(fields) < 2:
            continue
        name = fields[1]
        lowered = name.lower()
        if "audient_evo8" not in lowered:
            continue
        if lowered.endswith(".monitor"):
            playback = name
        elif "alsa_input" in lowered:
            capture = name
    return capture, playback


class AudioMeterReader:
    """Read EVO graph audio without opening an ALSA hardware PCM."""

    channels = 6

    def __init__(self) -> None:
        self._lock = Lock()
        self._stop = Event()
        self._processes: list[subprocess.Popen[bytes]] = []
        self._threads: list[Thread] = []
        self._usbmon_fd: int | None = None
        self._usbmon_seen = False
        self._usbmon_error: str | None = None
        self._levels = {
            "capture": (SILENCE_DB,) * self.channels,
            "playback": (SILENCE_DB,) * self.channels,
        }
        self._last_sample = {"capture": 0.0, "playback": 0.0}
        self._started = 0.0
        self.status = "Meters are stopped"

    def start(self) -> None:
        if self._started:
            return
        self._started = time.monotonic()
        self._start_usbmon()
        if self._usbmon_fd is not None:
            self.status = "Waiting for direct ALSA audio…"
            return
        pactl = shutil.which("pactl")
        parec = shutil.which("parec")
        if not pactl or not parec:
            if self._usbmon_fd is not None:
                self.status = "Waiting for direct ALSA audio…"
            else:
                self.status = "Meters need usbmon access or pactl/parec"
            return
        try:
            result = subprocess.run(
                [pactl, "list", "short", "sources"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            if self._usbmon_fd is not None:
                self.status = "Waiting for direct ALSA audio…"
            else:
                self.status = "No direct-ALSA or PipeWire meter source is available"
            return

        capture, playback = find_evo_sources(result.stdout)
        if not capture and not playback:
            if self._usbmon_fd is not None:
                self.status = "Waiting for direct ALSA audio…"
            else:
                self.status = "EVO 8 meter sources were not found"
            return

        if capture:
            self._spawn(parec, "capture", capture)
        if playback:
            self._spawn(parec, "playback", playback)
        self.status = (
            "Waiting for direct ALSA audio…"
            if self._usbmon_fd is not None
            else "Waiting for EVO 8 audio from PipeWire/JACK…"
        )

    def stop(self) -> None:
        self._stop.set()
        if self._usbmon_fd is not None:
            os.close(self._usbmon_fd)
            self._usbmon_fd = None
        for process in self._processes:
            if process.poll() is None:
                process.terminate()
        for process in self._processes:
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
        for thread in self._threads:
            thread.join(timeout=1)
        self._processes.clear()
        self._threads.clear()

    def snapshot(self) -> MeterSnapshot:
        now = time.monotonic()
        with self._lock:
            capture_seen = now - self._last_sample["capture"] < 0.75
            playback_seen = now - self._last_sample["playback"] < 0.75
            capture = self._levels["capture"] if capture_seen else (SILENCE_DB,) * 6
            playback = self._levels["playback"] if playback_seen else (SILENCE_DB,) * 6

        if self._usbmon_seen and (capture_seen or playback_seen):
            self.status = "Meters connected · direct ALSA remains exclusive to the DAW"
        elif capture_seen or playback_seen:
            self.status = "Meters connected through PipeWire/JACK"
        elif self._started and now - self._started > 1.5:
            if self._usbmon_error:
                self.status = f"Direct ALSA meters unavailable · {self._usbmon_error}"
            elif self._usbmon_fd is not None:
                self.status = "Waiting for direct ALSA audio from the EVO 8"
            else:
                self.status = "No active EVO 8 meter stream"
        return MeterSnapshot(capture, playback, capture_seen, playback_seen)

    def _spawn(self, parec: str, kind: str, source: str) -> None:
        command = [
            parec,
            f"--device={source}",
            "--raw",
            "--format=float32le",
            "--rate=48000",
            f"--channels={self.channels}",
            "--no-remix",
            "--no-remap",
            "--latency-msec=20",
        ]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return
        self._processes.append(process)
        thread = Thread(target=self._read, args=(process, kind), daemon=True)
        self._threads.append(thread)
        thread.start()

    def _read(self, process: subprocess.Popen[bytes], kind: str) -> None:
        if process.stdout is None:
            return
        chunk_size = self.channels * 4 * 1024
        while not self._stop.is_set():
            payload = process.stdout.read(chunk_size)
            if not payload:
                return
            usable = len(payload) - len(payload) % (self.channels * 4)
            samples = array("f")
            samples.frombytes(payload[:usable])
            if sys.byteorder != "little":
                samples.byteswap()
            levels = peak_db(samples, self.channels)
            with self._lock:
                if self._usbmon_seen:
                    continue
                self._levels[kind] = levels
                self._last_sample[kind] = time.monotonic()

    def _start_usbmon(self) -> None:
        device = find_evo_usb_device()
        if device is None:
            self._usbmon_error = "EVO 8 USB address was not found"
            return
        bus, device_number = device
        path = f"/dev/usbmon{bus}"
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except FileNotFoundError:
            self._usbmon_error = "load the usbmon kernel module"
            return
        except PermissionError:
            self._usbmon_error = f"read permission is required for {path}"
            return
        except OSError as error:
            self._usbmon_error = error.strerror or str(error)
            return
        self._usbmon_fd = descriptor
        thread = Thread(
            target=self._read_usbmon,
            args=(descriptor, bus, device_number),
            daemon=True,
        )
        self._threads.append(thread)
        thread.start()

    def _read_usbmon(self, descriptor: int, bus: int, device: int) -> None:
        header = ctypes.create_string_buffer(_USBMON_HEADER.size)
        data = ctypes.create_string_buffer(65536)
        argument = struct.pack(
            "<QQQ",
            ctypes.addressof(header),
            ctypes.addressof(data),
            len(data),
        )
        pending = {"capture": bytearray(), "playback": bytearray()}
        last_publish = {"capture": 0.0, "playback": 0.0}
        while not self._stop.is_set():
            try:
                readable, _, _ = select.select([descriptor], [], [], 0.2)
                if not readable:
                    continue
                fcntl.ioctl(descriptor, _USBMON_GETX, argument)
            except OSError as error:
                if self._stop.is_set() or error.errno == errno.EBADF:
                    return
                if error.errno in (errno.EAGAIN, errno.EINTR):
                    continue
                self._usbmon_error = error.strerror or str(error)
                return

            packet = _USBMON_HEADER.unpack(header.raw)
            event = packet[1]
            transfer_type = packet[2]
            endpoint = packet[3]
            packet_device = packet[4]
            packet_bus = packet[5]
            captured_length = packet[12]
            descriptor_count = packet[17]
            if transfer_type != 0 or packet_bus != bus or packet_device != device:
                continue
            if event == ord("S") and endpoint == 0x01:
                kind = "playback"
            elif event == ord("C") and endpoint == 0x82:
                kind = "capture"
            else:
                continue

            raw = data.raw[:captured_length]
            payload = extract_iso_payload(raw, descriptor_count)
            if not payload:
                continue
            pending[kind].extend(payload)
            now = time.monotonic()
            if now - last_publish[kind] < 0.02:
                continue
            levels = s32le_peak_db(pending[kind], self.channels)
            with self._lock:
                self._levels[kind] = levels
                self._last_sample[kind] = now
                self._usbmon_seen = True
            pending[kind].clear()
            last_publish[kind] = now
