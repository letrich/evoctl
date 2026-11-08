"""Non-exclusive EVO audio metering through the PipeWire/Pulse graph."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
import math
import shutil
import subprocess
import sys
from threading import Event, Lock, Thread
import time


SILENCE_DB = -128.0


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
        pactl = shutil.which("pactl")
        parec = shutil.which("parec")
        if not pactl or not parec:
            self.status = "Meters need pactl and parec (pulseaudio-utils)"
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
            self.status = "PipeWire/Pulse is unavailable; meters are disabled"
            return

        capture, playback = find_evo_sources(result.stdout)
        if not capture and not playback:
            self.status = "EVO 8 PipeWire sources were not found"
            return

        if capture:
            self._spawn(parec, "capture", capture)
        if playback:
            self._spawn(parec, "playback", playback)
        self.status = "Waiting for EVO 8 audio from PipeWire/JACK…"

    def stop(self) -> None:
        self._stop.set()
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

        if capture_seen or playback_seen:
            self.status = "Meters connected through PipeWire/JACK"
        elif self._started and now - self._started > 1.5:
            self.status = (
                "No shared audio stream · select JACK/PipeWire in the DAW for meters"
            )
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
                self._levels[kind] = levels
                self._last_sample[kind] = time.monotonic()
