"""EVO-style PySide6 mixer UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QCloseEvent, QPaintEvent, QPainter
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
from .meter import AudioMeterReader, SILENCE_DB


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


class LevelMeter(QWidget):
    """Compact mono/stereo peak meter with a controlled visual decay."""

    def __init__(self, channels: int, *, height: int = 270) -> None:
        super().__init__()
        self.channels = channels
        self._levels = [SILENCE_DB] * channels
        self.setFixedWidth(15 if channels == 1 else 28)
        self.setMinimumHeight(height)

    def set_levels(self, levels: tuple[float, ...]) -> None:
        for channel in range(self.channels):
            incoming = levels[channel] if channel < len(levels) else SILENCE_DB
            self._levels[channel] = max(incoming, self._levels[channel] - 2.5)
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(COLORS["meter"]))
        gap = 2
        width = max(2, (self.width() - gap * (self.channels + 1)) // self.channels)
        for channel, level in enumerate(self._levels):
            left = gap + channel * (width + gap)
            top = gap
            height = max(1, self.height() - gap * 2)
            painter.fillRect(left, top, width, height, QColor("#080808"))
            proportion = max(0.0, min(1.0, (level + 60.0) / 60.0))
            filled = round(height * proportion)
            if not filled:
                continue
            green_height = min(filled, round(height * 0.8))
            painter.fillRect(
                left,
                top + height - green_height,
                width,
                green_height,
                QColor("#58c696"),
            )
            if filled > green_height:
                yellow_height = min(filled - green_height, round(height * 0.15))
                painter.fillRect(
                    left,
                    top + height - green_height - yellow_height,
                    width,
                    yellow_height,
                    QColor("#e2b84f"),
                )
                red_height = filled - green_height - yellow_height
                if red_height:
                    painter.fillRect(
                        left,
                        top + height - filled,
                        width,
                        red_height,
                        QColor(COLORS["danger"]),
                    )
        painter.setPen(QColor("#303030"))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)


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
        self.meter = LevelMeter(len(spec.sources))
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
            if not self.gain.isSliderDown():
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
        if len(self.spec.sources) == 1:
            value = round(max(levels))
            if value <= -128:
                pan = 0
            else:
                pan = round((levels[1] - levels[0]) / 1.28)
                pan = max(-100, min(100, pan))
        else:
            value = round(sum(levels) / len(levels))
            pan = 0
        self.fader.blockSignals(True)
        self.pan.blockSignals(True)
        try:
            self.fader.setValue(max(-128, min(6, value)))
            self._show_level(value)
            self.pan.setValue(pan)
            self._show_pan(pan)
        finally:
            self.fader.blockSignals(False)
            self.pan.blockSignals(False)

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
        self.meter = LevelMeter(2, height=180)
        self.meter.setFixedWidth(48)
        meters.addWidget(self.meter)
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
            if not self.volume.isSliderDown():
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
        settings: QSettings | None = None,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.connected = connected
        self.settings = settings
        self.setWindowTitle("EVO")
        self.resize(1500, 850)
        self.setMinimumSize(980, 680)
        self.setStyleSheet(STYLE)
        self.active_pair = 0
        self.artist_enabled = False
        self.input_strips: list[MixerStrip] = []
        self.output_strips: list[MasterSection] = []
        self.mix_levels: dict[tuple[int, int], QWidget] = {}
        self._sync_failures = 0
        self._meter_reader: AudioMeterReader | None = None
        self._loading_settings = False
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(200)
        self.sync_timer.timeout.connect(self._sync_hardware_state)
        self.meter_timer = QTimer(self)
        self.meter_timer.setInterval(33)
        self.meter_timer.timeout.connect(self._update_meters)
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

        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(0)
        self.message = QLabel(status_text)
        self.message.setObjectName("small")
        self.message.setContentsMargins(12, 5, 12, 5)
        self.message.setStyleSheet(
            f"color: {COLORS['main'] if connected else COLORS['danger']};"
        )
        footer_layout.addWidget(self.message, 1)
        self.meter_message = QLabel("Meters stopped")
        self.meter_message.setObjectName("small")
        self.meter_message.setContentsMargins(12, 5, 12, 5)
        self.meter_message.setAlignment(Qt.AlignmentFlag.AlignRight)
        footer_layout.addWidget(self.meter_message)
        root_layout.addWidget(footer)
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
        if self.settings is not None and not self._loading_settings:
            self.settings.setValue("ui/show_preamp", visible)

    def _enable_artist_mix(self, enabled: bool) -> None:
        self.artist_enabled = enabled
        if not enabled and self.active_pair == 1:
            self.select_mix(0)
        self.master.artist_choice.setEnabled(enabled)
        self.message.setText("Artist Mix enabled" if enabled else "Artist Mix disabled")
        if self.settings is not None and not self._loading_settings:
            self.settings.setValue("ui/artist_enabled", enabled)

    def select_mix(self, pair: int) -> None:
        if pair == 1 and not self.artist_enabled:
            self.master.main_choice.setChecked(True)
            self.master.artist_choice.setChecked(False)
            self.message.setText("Enable Artist Mix from Setup first")
            return
        if not self._loading_settings:
            self._save_mix_state(self.active_pair)
        self.active_pair = pair
        artist = pair == 1
        for strip in self.input_strips:
            strip.set_output_pair(pair, artist)
        self.master.set_mix(pair, artist)
        if self.connected:
            self._load_selected_mix()
        self._restore_mix_state(pair)
        if self.settings is not None and not self._loading_settings:
            self.settings.setValue("ui/active_pair", pair)

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

    def load_preferences(self) -> None:
        """Restore local mixer semantics and send saved mixes to the EVO."""
        if self.settings is None:
            return
        self._loading_settings = True
        try:
            geometry = self.settings.value("ui/geometry")
            if geometry is not None:
                self.restoreGeometry(geometry)
            self.preamp_action.setChecked(
                self.settings.value("ui/show_preamp", False, type=bool)
            )
            self.artist_action.setChecked(
                self.settings.value("ui/artist_enabled", False, type=bool)
            )
            pair = self.settings.value("ui/active_pair", 0, type=int)
            if pair not in (0, 1) or (pair == 1 and not self.artist_enabled):
                pair = 0
            self.select_mix(pair)
        finally:
            self._loading_settings = False

        if self.connected:
            try:
                restored = self._apply_saved_mixes()
            except Exception as error:
                self.message.setText(f"Saved mixer restore failed: {error}")
                self.message.setStyleSheet(f"color: {COLORS['danger']};")
            else:
                if restored:
                    self.message.setText("Previous mixer settings restored to EVO 8")
                    self.message.setStyleSheet(f"color: {COLORS['main']};")

    def start_hardware_sync(self) -> None:
        """Keep controls in step with changes made on the EVO 8 itself."""
        if self.connected and not self.sync_timer.isActive():
            self.sync_timer.start()

    def start_audio_meters(self) -> None:
        """Start graph-based meters without opening an ALSA device."""
        if self._meter_reader is not None:
            return
        self._meter_reader = AudioMeterReader()
        self._meter_reader.start()
        self.meter_message.setText(self._meter_reader.status)
        self.meter_timer.start()

    def _update_meters(self) -> None:
        if self._meter_reader is None:
            return
        snapshot = self._meter_reader.snapshot()
        source_levels = (
            (snapshot.capture[0],),
            (snapshot.capture[1],),
            (snapshot.capture[2],),
            (snapshot.capture[3],),
            snapshot.playback[0:2],
            snapshot.playback[2:4],
            snapshot.capture[4:6],
        )
        for strip, levels in zip(self.input_strips, source_levels, strict=True):
            strip.meter.set_levels(levels)
        pair = self.active_pair * 2
        self.master.meter.set_levels(snapshot.playback[pair : pair + 2])
        self.meter_message.setText(self._meter_reader.status)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._save_preferences()
        self.sync_timer.stop()
        self.meter_timer.stop()
        if self._meter_reader is not None:
            self._meter_reader.stop()
        super().closeEvent(event)

    def _sync_hardware_state(self) -> None:
        errors: list[Exception] = []
        for strip in self.input_strips:
            if strip.spec.input_channel is not None:
                try:
                    strip.apply_input_state(
                        self.controller.read_input(strip.spec.input_channel)
                    )
                except Exception as error:
                    errors.append(error)
        try:
            self.master.apply_state(
                self.controller.read_output(self.active_pair * 2)
            )
        except Exception as error:
            errors.append(error)

        if errors:
            self._sync_failures += 1
            if self._sync_failures >= 3:
                self.sync_timer.setInterval(2000)
            self.message.setText(
                f"Hardware synchronisation failed ({len(errors)} controls): {errors[0]}"
            )
            self.message.setStyleSheet(f"color: {COLORS['danger']};")
        else:
            if self._sync_failures:
                self.message.setText("EVO 8 connected · hardware synchronisation restored")
                self.message.setStyleSheet(f"color: {COLORS['main']};")
            self._sync_failures = 0
            self.sync_timer.setInterval(200)

    def _load_selected_mix(self) -> None:
        for strip in self.input_strips:
            strip.load_mix_level()
        self.master.apply_state(self.controller.read_output(self.active_pair * 2))

    def _mix_key(self, pair: int, strip: int, field: str) -> str:
        return f"mix/{pair}/strip/{strip}/{field}"

    def _save_mix_state(self, pair: int) -> None:
        if self.settings is None or self._loading_settings:
            return
        for index, strip in enumerate(self.input_strips):
            self.settings.setValue(self._mix_key(pair, index, "fader"), strip.fader.value())
            self.settings.setValue(self._mix_key(pair, index, "pan"), strip.pan.value())
            self.settings.setValue(self._mix_key(pair, index, "mute"), strip.mute.isChecked())
            self.settings.setValue(self._mix_key(pair, index, "solo"), strip.solo.isChecked())

    def _restore_mix_state(self, pair: int) -> bool:
        if self.settings is None:
            return False
        restored = False
        for index, strip in enumerate(self.input_strips):
            fader_key = self._mix_key(pair, index, "fader")
            if not self.settings.contains(fader_key):
                continue
            restored = True
            for widget in (strip.fader, strip.pan, strip.mute, strip.solo):
                widget.blockSignals(True)
            try:
                fader = self.settings.value(fader_key, 0, type=int)
                pan = self.settings.value(
                    self._mix_key(pair, index, "pan"), 0, type=int
                )
                strip.fader.setValue(max(-128, min(6, fader)))
                strip._show_level(strip.fader.value())
                strip.pan.setValue(max(-100, min(100, pan)))
                strip._show_pan(strip.pan.value())
                strip.mute.setChecked(
                    self.settings.value(
                        self._mix_key(pair, index, "mute"), False, type=bool
                    )
                )
                strip.solo.setChecked(
                    self.settings.value(
                        self._mix_key(pair, index, "solo"), False, type=bool
                    )
                )
            finally:
                for widget in (strip.fader, strip.pan, strip.mute, strip.solo):
                    widget.blockSignals(False)
        return restored

    def _apply_saved_mixes(self) -> bool:
        if self.settings is None:
            return False
        restored = False
        for pair in (0, 1):
            states: list[tuple[int, int, bool, bool] | None] = []
            for index in range(len(self.input_strips)):
                fader_key = self._mix_key(pair, index, "fader")
                if not self.settings.contains(fader_key):
                    states.append(None)
                    continue
                restored = True
                states.append(
                    (
                        self.settings.value(fader_key, 0, type=int),
                        self.settings.value(
                            self._mix_key(pair, index, "pan"), 0, type=int
                        ),
                        self.settings.value(
                            self._mix_key(pair, index, "mute"), False, type=bool
                        ),
                        self.settings.value(
                            self._mix_key(pair, index, "solo"), False, type=bool
                        ),
                    )
                )
            any_solo = any(state is not None and state[3] for state in states)
            destination = pair * 2
            for strip, state in zip(self.input_strips, states, strict=True):
                if state is None:
                    continue
                level, pan, muted, solo = state
                effective = -128 if muted or (any_solo and not solo) else level
                left = effective
                right = effective
                if len(strip.spec.sources) == 1 and effective > -128:
                    if pan < 0:
                        right = max(-128, round(effective - abs(pan) * 1.28))
                    elif pan > 0:
                        left = max(-128, round(effective - pan * 1.28))
                if len(strip.spec.sources) == 1:
                    self.controller.set_mix_level(strip.spec.sources[0], destination, left)
                    self.controller.set_mix_level(
                        strip.spec.sources[0], destination + 1, right
                    )
                else:
                    self.controller.set_mix_level(
                        strip.spec.sources[0], destination, effective
                    )
                    self.controller.set_mix_level(
                        strip.spec.sources[1], destination + 1, effective
                    )
        return restored

    def _save_preferences(self) -> None:
        if self.settings is None:
            return
        self._save_mix_state(self.active_pair)
        self.settings.setValue("state/version", 1)
        self.settings.setValue("ui/geometry", self.saveGeometry())
        self.settings.setValue("ui/show_preamp", self.preamp_action.isChecked())
        self.settings.setValue("ui/artist_enabled", self.artist_action.isChecked())
        self.settings.setValue("ui/active_pair", self.active_pair)
        self.settings.sync()

    def _apply_solo(self) -> None:
        any_solo = any(strip.solo.isChecked() for strip in self.input_strips)

        def operation() -> None:
            for strip in self.input_strips:
                strip.write_effective_level(any_solo)

        self.invoke(operation)
        self._save_mix_state(self.active_pair)

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
