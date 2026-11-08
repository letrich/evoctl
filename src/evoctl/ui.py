"""EVO-style PySide6 mixer UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDial,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .controller import Evo8Controller, InputState, OutputState


COLORS = {
    "window": "#151515",
    "panel_alt": "#282828",
    "line": "#404040",
    "text": "#f1f1f1",
    "muted": "#909090",
    "main": "#5ec49f",
    "artist": "#d4aa56",
    "danger": "#e65a67",
    "meter": "#121212",
}


STYLE = f"""
QWidget {{
    background: {COLORS['window']};
    color: {COLORS['text']};
    font-family: Inter, Noto Sans, sans-serif;
    font-size: 12px;
}}
QMainWindow {{ background: {COLORS['window']}; }}
QMenuBar {{
    background: #303030;
    border-bottom: 1px solid #4a4a4a;
    padding: 2px;
}}
QMenuBar::item {{ background: transparent; padding: 5px 10px; }}
QMenuBar::item:selected {{ background: #505050; }}
QMenu {{ background: #303030; border: 1px solid #555; padding: 4px; }}
QMenu::item {{ padding: 6px 28px 6px 20px; }}
QMenu::item:selected {{ background: #4b4b4b; }}
QLabel {{ background: transparent; }}
QLabel#channelName {{
    color: #bcbcbc;
    font-size: 15px;
    font-weight: 500;
    letter-spacing: 2px;
}}
QLabel#small {{ color: {COLORS['muted']}; font-size: 10px; }}
QLabel#readout {{ color: #d5d5d5; font-size: 11px; font-weight: 600; }}
QLabel#masterTitle {{ font-size: 18px; font-weight: 600; letter-spacing: 1px; }}
QFrame#channel {{
    background: {COLORS['panel_alt']};
    border-right: 1px solid {COLORS['line']};
    border-bottom: 1px solid {COLORS['line']};
}}
QFrame#master {{
    background: #1c1c1c;
    border-left: 1px solid {COLORS['line']};
    border-bottom: 1px solid {COLORS['line']};
}}
QFrame#accentMain {{ background: {COLORS['main']}; min-height: 8px; max-height: 8px; }}
QFrame#accentArtist {{ background: {COLORS['artist']}; min-height: 8px; max-height: 8px; }}
QPushButton {{
    color: #c8c8c8;
    background: #121212;
    border: 1px solid #303030;
    border-radius: 16px;
    min-height: 31px;
    padding: 0 10px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: #777; color: white; }}
QPushButton:checked {{ color: #111; background: {COLORS['main']}; border-color: {COLORS['main']}; }}
QPushButton#mute:checked {{ color: white; background: {COLORS['danger']}; border-color: {COLORS['danger']}; }}
QPushButton#mixChoice {{
    border: 0;
    border-radius: 0;
    background: transparent;
    min-height: 72px;
    font-size: 16px;
    letter-spacing: 1px;
}}
QPushButton#mixChoice:checked {{ color: white; background: #262626; }}
QSlider::groove:vertical {{ background: #080808; width: 17px; border-radius: 8px; }}
QSlider::sub-page:vertical {{ background: #080808; border-radius: 8px; }}
QSlider::handle:vertical {{
    background: #969696;
    border: 1px solid #b8b8b8;
    height: 23px;
    width: 29px;
    margin: 0 -7px;
    border-radius: 11px;
}}
QDial {{ background: transparent; }}
QScrollArea {{ border: 0; background: {COLORS['window']}; }}
"""


@dataclass(frozen=True, slots=True)
class MixerChannel:
    name: str
    sources: tuple[int, ...]
    input_channel: int | None = None


MIXER_CHANNELS = (
    MixerChannel("MIC 1", (0,), 0),
    MixerChannel("MIC 2", (1,), 1),
    MixerChannel("MIC 3", (2,), 2),
    MixerChannel("MIC 4", (3,), 3),
    MixerChannel("DAW 1+2", (4, 5)),
    MixerChannel("DAW 3+4", (6, 7)),
    MixerChannel("LOOP-BACK 1+2", (8, 9)),
)


class MixerStrip(QFrame):
    def __init__(
        self,
        spec: MixerChannel,
        controller: Evo8Controller,
        invoke: Callable[[Callable[[], None]], None],
        solo_changed: Callable[[], None],
    ) -> None:
        super().__init__()
        self.setObjectName("channel")
        self.setMinimumWidth(150 if len(spec.sources) == 1 else 220)
        self.setMaximumWidth(170 if len(spec.sources) == 1 else 250)
        self.spec = spec
        self._controller = controller
        self._invoke = invoke
        self._solo_changed = solo_changed
        self._output_pair = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 14)
        layout.setSpacing(9)

        self.accent = QFrame()
        self.accent.setObjectName("accentMain")
        layout.addWidget(self.accent)

        title = QLabel(spec.name)
        title.setObjectName("channelName")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.pan = QDial()
        self.pan.setRange(-100, 100)
        self.pan.setValue(0)
        self.pan.setNotchesVisible(False)
        self.pan.setFixedSize(72, 72)
        self.pan.valueChanged.connect(self._show_pan)
        self.pan.sliderReleased.connect(self._write_level)
        layout.addWidget(self.pan, 0, Qt.AlignmentFlag.AlignHCenter)

        self.pan_label = QLabel("C")
        self.pan_label.setObjectName("small")
        self.pan_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.pan_label)

        self.link = QPushButton("MONO" if len(spec.sources) == 1 else "STEREO")
        self.link.setCheckable(spec.input_channel is not None)
        self.link.setEnabled(spec.input_channel is not None)
        self.link.toggled.connect(self._set_link)
        layout.addWidget(self.link)

        actions = QHBoxLayout()
        self.solo = QPushButton("S" if len(spec.sources) == 1 else "SOLO")
        self.solo.setCheckable(True)
        self.solo.toggled.connect(lambda _checked: self._solo_changed())
        self.mute = QPushButton("M" if len(spec.sources) == 1 else "MUTE")
        self.mute.setObjectName("mute")
        self.mute.setCheckable(True)
        self.mute.toggled.connect(lambda _checked: self._write_level())
        actions.addWidget(self.solo)
        actions.addWidget(self.mute)
        layout.addLayout(actions)

        fader_row = QHBoxLayout()
        fader_row.setSpacing(7)
        self.meter = QFrame()
        self.meter.setFixedWidth(15 if len(spec.sources) == 1 else 28)
        self.meter.setStyleSheet(
            f"background: {COLORS['meter']}; border: 1px solid #303030;"
        )
        fader_row.addWidget(self.meter)
        self.fader = QSlider(Qt.Orientation.Vertical)
        self.fader.setRange(-128, 6)
        self.fader.setValue(0)
        self.fader.setMinimumHeight(270)
        self.fader.valueChanged.connect(self._show_level)
        self.fader.sliderReleased.connect(self._write_level)
        fader_row.addWidget(self.fader, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addLayout(fader_row, 1)

        self.level_label = QLabel("0 dB")
        self.level_label.setObjectName("readout")
        self.level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.level_label)

        self.preamp = QWidget()
        preamp_layout = QVBoxLayout(self.preamp)
        preamp_layout.setContentsMargins(0, 7, 0, 0)
        preamp_layout.setSpacing(6)
        preamp_title = QLabel("MIC PRE")
        preamp_title.setObjectName("small")
        preamp_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preamp_layout.addWidget(preamp_title)
        preamp_actions = QHBoxLayout()
        self.phantom = QPushButton("48V")
        self.phantom.setCheckable(True)
        self.phantom.toggled.connect(self._set_phantom)
        self.instrument = QPushButton("INST")
        self.instrument.setCheckable(True)
        self.instrument.toggled.connect(self._set_instrument)
        self.instrument.setVisible(spec.input_channel == 0)
        preamp_actions.addWidget(self.phantom)
        preamp_actions.addWidget(self.instrument)
        preamp_layout.addLayout(preamp_actions)
        self.gain = QDial()
        self.gain.setRange(-8, 50)
        self.gain.setValue(-8)
        self.gain.setFixedSize(62, 62)
        self.gain.valueChanged.connect(self._show_gain)
        self.gain.sliderReleased.connect(self._set_gain)
        preamp_layout.addWidget(self.gain, 0, Qt.AlignmentFlag.AlignHCenter)
        self.gain_label = QLabel("GAIN  −8 dB")
        self.gain_label.setObjectName("readout")
        self.gain_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preamp_layout.addWidget(self.gain_label)
        self.preamp.setVisible(False)
        layout.addWidget(self.preamp)

        if spec.input_channel is None:
            self.preamp.setEnabled(False)

    def set_preamp_visible(self, visible: bool) -> None:
        self.preamp.setVisible(visible and self.spec.input_channel is not None)

    def set_output_pair(self, pair: int, artist: bool) -> None:
        self._output_pair = pair
        self.accent.setObjectName("accentArtist" if artist else "accentMain")
        self.accent.style().unpolish(self.accent)
        self.accent.style().polish(self.accent)

    def apply_input_state(self, state: InputState) -> None:
        for widget in (self.gain, self.phantom, self.instrument, self.link):
            widget.blockSignals(True)
        try:
            self.gain.setValue(round(state.gain_db))
            self._show_gain(round(state.gain_db))
            self.phantom.setChecked(state.phantom_power)
            self.instrument.setChecked(state.instrument_mode)
            self.link.setChecked(state.stereo_linked)
            self.link.setText("STEREO" if state.stereo_linked else "MONO")
        finally:
            for widget in (self.gain, self.phantom, self.instrument, self.link):
                widget.blockSignals(False)

    def load_mix_level(self) -> None:
        destination = self._output_pair * 2
        if len(self.spec.sources) == 1:
            levels = (
                self._controller.read_mix_level(self.spec.sources[0], destination),
                self._controller.read_mix_level(self.spec.sources[0], destination + 1),
            )
        else:
            levels = (
                self._controller.read_mix_level(self.spec.sources[0], destination),
                self._controller.read_mix_level(self.spec.sources[1], destination + 1),
            )
        value = round(sum(levels) / len(levels))
        self.fader.blockSignals(True)
        try:
            self.fader.setValue(max(-128, min(6, value)))
            self._show_level(value)
        finally:
            self.fader.blockSignals(False)

    def write_effective_level(self, any_solo: bool) -> None:
        suppressed = self.mute.isChecked() or (any_solo and not self.solo.isChecked())
        level = -128 if suppressed else self.fader.value()
        pan = self.pan.value()
        left = level
        right = level
        if len(self.spec.sources) == 1 and level > -128:
            if pan < 0:
                right = max(-128, round(level - abs(pan) * 1.28))
            elif pan > 0:
                left = max(-128, round(level - pan * 1.28))
        destination = self._output_pair * 2
        if len(self.spec.sources) == 1:
            self._controller.set_mix_level(self.spec.sources[0], destination, left)
            self._controller.set_mix_level(self.spec.sources[0], destination + 1, right)
        else:
            self._controller.set_mix_level(self.spec.sources[0], destination, level)
            self._controller.set_mix_level(self.spec.sources[1], destination + 1, level)

    def _write_level(self) -> None:
        self._solo_changed()

    def _show_pan(self, value: int) -> None:
        self.pan_label.setText(
            "C" if value == 0 else f"L {abs(value)}" if value < 0 else f"R {value}"
        )

    def _show_level(self, value: int) -> None:
        self.level_label.setText("−∞" if value <= -128 else f"{value} dB")

    def _show_gain(self, value: int) -> None:
        self.gain_label.setText(f"GAIN  {value} dB")

    def _set_gain(self) -> None:
        if self.spec.input_channel is not None:
            self._invoke(
                lambda: self._controller.set_input_gain(
                    self.spec.input_channel, self.gain.value()
                )
            )

    def _set_phantom(self, enabled: bool) -> None:
        if self.spec.input_channel is not None:
            self._invoke(
                lambda: self._controller.set_phantom_power(self.spec.input_channel, enabled)
            )

    def _set_instrument(self, enabled: bool) -> None:
        if self.spec.input_channel is not None:
            self._invoke(
                lambda: self._controller.set_instrument_mode(self.spec.input_channel, enabled)
            )

    def _set_link(self, enabled: bool) -> None:
        if self.spec.input_channel is not None:
            self.link.setText("STEREO" if enabled else "MONO")
            self._invoke(
                lambda: self._controller.set_stereo_link(self.spec.input_channel, enabled)
            )


class MasterSection(QFrame):
    def __init__(
        self,
        controller: Evo8Controller,
        invoke: Callable[[Callable[[], None]], None],
        select_mix: Callable[[int], None],
    ) -> None:
        super().__init__()
        self.setObjectName("master")
        self.setMinimumWidth(275)
        self.setMaximumWidth(315)
        self._controller = controller
        self._invoke = invoke
        self._select_mix = select_mix
        self._channel = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 18)
        layout.setSpacing(0)
        self.accent = QFrame()
        self.accent.setObjectName("accentMain")
        layout.addWidget(self.accent)

        self.main_choice = QPushButton("OUTPUTS 1+2")
        self.main_choice.setObjectName("mixChoice")
        self.main_choice.setCheckable(True)
        self.main_choice.setChecked(True)
        self.main_choice.clicked.connect(lambda: self._select_mix(0))
        layout.addWidget(self.main_choice)

        self.artist_choice = QPushButton("OUTPUTS 3+4")
        self.artist_choice.setObjectName("mixChoice")
        self.artist_choice.setCheckable(True)
        self.artist_choice.setEnabled(False)
        self.artist_choice.clicked.connect(lambda: self._select_mix(1))
        layout.addWidget(self.artist_choice)

        body = QVBoxLayout()
        body.setContentsMargins(24, 22, 24, 0)
        body.setSpacing(11)
        self.title = QLabel("OUTPUTS 1+2")
        self.title.setObjectName("masterTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(self.title)
        self.kind = QLabel("MASTER MIX")
        self.kind.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.kind.setStyleSheet(f"color: {COLORS['main']}; letter-spacing: 2px;")
        body.addWidget(self.kind)

        self.volume = QDial()
        self.volume.setRange(-128, 0)
        self.volume.setValue(0)
        self.volume.setFixedSize(122, 122)
        self.volume.valueChanged.connect(self._show_volume)
        self.volume.sliderReleased.connect(self._set_volume)
        body.addWidget(self.volume, 0, Qt.AlignmentFlag.AlignHCenter)
        self.value = QLabel("0 dB")
        self.value.setObjectName("readout")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(self.value)
        self.mute = QPushButton("MUTE")
        self.mute.setObjectName("mute")
        self.mute.setCheckable(True)
        self.mute.toggled.connect(self._set_mute)
        body.addWidget(self.mute)
        body.addStretch(1)

        meter_label = QLabel("L                         R")
        meter_label.setObjectName("small")
        meter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(meter_label)
        meters = QHBoxLayout()
        for _ in range(2):
            meter = QFrame()
            meter.setFixedSize(22, 180)
            meter.setStyleSheet(
                f"background: {COLORS['meter']}; border: 1px solid #303030;"
            )
            meters.addWidget(meter)
        body.addLayout(meters)
        layout.addLayout(body, 1)

    def set_mix(self, pair: int, artist: bool) -> None:
        self._channel = pair * 2
        self.main_choice.blockSignals(True)
        self.artist_choice.blockSignals(True)
        self.main_choice.setChecked(pair == 0)
        self.artist_choice.setChecked(pair == 1)
        self.main_choice.blockSignals(False)
        self.artist_choice.blockSignals(False)
        self.title.setText(f"OUTPUTS {pair * 2 + 1}+{pair * 2 + 2}")
        self.kind.setText("ARTIST MIX" if artist else "MASTER MIX")
        color = COLORS["artist" if artist else "main"]
        self.kind.setStyleSheet(f"color: {color}; letter-spacing: 2px;")
        self.accent.setObjectName("accentArtist" if artist else "accentMain")
        self.accent.style().unpolish(self.accent)
        self.accent.style().polish(self.accent)

    def apply_state(self, state: OutputState) -> None:
        self.volume.blockSignals(True)
        self.mute.blockSignals(True)
        try:
            self.volume.setValue(round(state.volume_db))
            self._show_volume(round(state.volume_db))
            self.mute.setChecked(state.muted)
        finally:
            self.volume.blockSignals(False)
            self.mute.blockSignals(False)

    def _show_volume(self, value: int) -> None:
        self.value.setText("−∞" if value <= -128 else f"{value} dB")

    def _set_volume(self) -> None:
        self._invoke(
            lambda: self._controller.set_output_volume(self._channel, self.volume.value())
        )

    def _set_mute(self, enabled: bool) -> None:
        self._invoke(lambda: self._controller.set_output_mute(self._channel, enabled))


class MainWindow(QMainWindow):
    def __init__(
        self,
        controller: Evo8Controller,
        *,
        connected: bool,
        status_text: str,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.connected = connected
        self.setWindowTitle("EVO")
        self.resize(1500, 850)
        self.setMinimumSize(980, 680)
        self.setStyleSheet(STYLE)
        self.active_pair = 0
        self.artist_enabled = False
        self.input_strips: list[MixerStrip] = []
        self.output_strips: list[MasterSection] = []
        self.mix_levels: dict[tuple[int, int], QWidget] = {}
        self._build_menus()

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        strips = QWidget()
        strips_layout = QHBoxLayout(strips)
        strips_layout.setContentsMargins(0, 0, 0, 0)
        strips_layout.setSpacing(0)
        for spec in MIXER_CHANNELS:
            strip = MixerStrip(spec, controller, self.invoke, self._apply_solo)
            self.input_strips.append(strip)
            strips_layout.addWidget(strip)
        strips_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(strips)
        content_layout.addWidget(scroll, 1)

        self.master = MasterSection(controller, self.invoke, self.select_mix)
        self.output_strips.append(self.master)
        content_layout.addWidget(self.master)
        root_layout.addWidget(content, 1)

        self.message = QLabel(status_text)
        self.message.setObjectName("small")
        self.message.setContentsMargins(12, 5, 12, 5)
        self.message.setStyleSheet(
            f"color: {COLORS['main'] if connected else COLORS['danger']};"
        )
        root_layout.addWidget(self.message)
        self.setCentralWidget(root)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        save = file_menu.addAction("Save Mixer Configuration…")
        save.setEnabled(False)
        open_action = file_menu.addAction("Open Mixer Configuration…")
        open_action.setEnabled(False)
        file_menu.addSeparator()
        file_menu.addAction("Quit").triggered.connect(self.close)

        view_menu = self.menuBar().addMenu("View")
        self.preamp_action = QAction("Show Mic Pre Controls", self)
        self.preamp_action.setCheckable(True)
        self.preamp_action.toggled.connect(self._show_preamp_controls)
        view_menu.addAction(self.preamp_action)

        setup_menu = self.menuBar().addMenu("Setup")
        self.artist_action = QAction("Enable Artist Mix", self)
        self.artist_action.setCheckable(True)
        self.artist_action.toggled.connect(self._enable_artist_mix)
        setup_menu.addAction(self.artist_action)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("About evoctl").triggered.connect(
            lambda: self.message.setText("evoctl · Linux control for Audient EVO 8")
        )

    def _show_preamp_controls(self, visible: bool) -> None:
        for strip in self.input_strips:
            strip.set_preamp_visible(visible)

    def _enable_artist_mix(self, enabled: bool) -> None:
        self.artist_enabled = enabled
        if not enabled and self.active_pair == 1:
            self.select_mix(0)
        self.master.artist_choice.setEnabled(enabled)
        self.message.setText("Artist Mix enabled" if enabled else "Artist Mix disabled")

    def select_mix(self, pair: int) -> None:
        if pair == 1 and not self.artist_enabled:
            self.master.main_choice.setChecked(True)
            self.master.artist_choice.setChecked(False)
            self.message.setText("Enable Artist Mix from Setup first")
            return
        self.active_pair = pair
        artist = pair == 1
        for strip in self.input_strips:
            strip.set_output_pair(pair, artist)
        self.master.set_mix(pair, artist)
        if self.connected:
            self._load_selected_mix()

    def load_state(self) -> None:
        try:
            for strip in self.input_strips:
                if strip.spec.input_channel is not None:
                    strip.apply_input_state(
                        self.controller.read_input(strip.spec.input_channel)
                    )
            self._load_selected_mix()
        except Exception as error:
            self.message.setText(f"State readback failed: {error}")
            self.message.setStyleSheet(f"color: {COLORS['danger']};")
        else:
            self.message.setText("EVO 8 connected · hardware state loaded")
            self.message.setStyleSheet(f"color: {COLORS['main']};")

    def _load_selected_mix(self) -> None:
        for strip in self.input_strips:
            strip.load_mix_level()
        self.master.apply_state(self.controller.read_output(self.active_pair * 2))

    def _apply_solo(self) -> None:
        any_solo = any(strip.solo.isChecked() for strip in self.input_strips)

        def operation() -> None:
            for strip in self.input_strips:
                strip.write_effective_level(any_solo)

        self.invoke(operation)

    def invoke(self, operation: Callable[[], None]) -> None:
        try:
            operation()
        except Exception as error:
            self.message.setText(str(error))
            self.message.setStyleSheet(f"color: {COLORS['danger']};")
        else:
            self.message.setText("Device updated")
            color = COLORS["artist" if self.active_pair else "main"]
            self.message.setStyleSheet(f"color: {color};")
