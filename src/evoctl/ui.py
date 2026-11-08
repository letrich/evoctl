"""PySide6 control-panel UI."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from .controller import Evo8Controller, InputState, OutputState


COLORS = {
    "background": "#0b1017",
    "panel": "#121a24",
    "panel_alt": "#182332",
    "line": "#263548",
    "text": "#edf5ff",
    "muted": "#8da0b6",
    "accent": "#20d6b5",
    "accent_dim": "#123f3c",
    "danger": "#ff647c",
    "warning": "#f3b849",
}


STYLE = f"""
QWidget {{
    background: {COLORS['background']};
    color: {COLORS['text']};
    font-family: Inter, Noto Sans, sans-serif;
    font-size: 13px;
}}
QMainWindow {{ background: {COLORS['background']}; }}
QLabel {{ background: transparent; }}
QFrame#topBar, QFrame#card {{
    background: {COLORS['panel']};
    border: 1px solid {COLORS['line']};
    border-radius: 12px;
}}
QLabel#title {{ font-size: 24px; font-weight: 700; }}
QLabel#sectionTitle {{ font-size: 18px; font-weight: 650; }}
QLabel#muted {{ color: {COLORS['muted']}; }}
QLabel#value {{ color: {COLORS['accent']}; font-size: 15px; font-weight: 650; }}
QLabel#statusGood {{
    color: {COLORS['accent']};
    background: {COLORS['accent_dim']};
    border-radius: 9px;
    padding: 7px 12px;
    font-weight: 650;
}}
QLabel#statusBad {{
    color: {COLORS['warning']};
    background: #382d1b;
    border-radius: 9px;
    padding: 7px 12px;
    font-weight: 650;
}}
QTabWidget::pane {{ border: 0; margin-top: 10px; }}
QTabBar::tab {{
    color: {COLORS['muted']};
    background: transparent;
    padding: 11px 18px;
    margin-right: 5px;
    border-radius: 8px;
}}
QTabBar::tab:selected {{
    color: {COLORS['text']};
    background: {COLORS['panel_alt']};
}}
QPushButton {{
    color: {COLORS['text']};
    background: {COLORS['panel_alt']};
    border: 1px solid {COLORS['line']};
    border-radius: 8px;
    padding: 8px 10px;
    font-weight: 600;
}}
QPushButton:hover {{ border-color: {COLORS['accent']}; }}
QPushButton:checked {{
    color: #061511;
    background: {COLORS['accent']};
    border-color: {COLORS['accent']};
}}
QPushButton#danger:checked {{
    color: white;
    background: {COLORS['danger']};
    border-color: {COLORS['danger']};
}}
QSlider::groove:vertical {{
    background: {COLORS['line']};
    width: 6px;
    border-radius: 3px;
}}
QSlider::sub-page:vertical {{
    background: {COLORS['accent']};
    border-radius: 3px;
}}
QSlider::handle:vertical {{
    background: {COLORS['text']};
    border: 3px solid {COLORS['accent']};
    height: 18px;
    width: 18px;
    margin: 0 -7px;
    border-radius: 9px;
}}
QTableWidget {{
    background: {COLORS['panel']};
    alternate-background-color: {COLORS['panel_alt']};
    border: 1px solid {COLORS['line']};
    border-radius: 10px;
    gridline-color: {COLORS['line']};
}}
QHeaderView::section {{
    color: {COLORS['muted']};
    background: {COLORS['panel_alt']};
    border: 0;
    border-right: 1px solid {COLORS['line']};
    border-bottom: 1px solid {COLORS['line']};
    padding: 9px;
    font-weight: 650;
}}
QDoubleSpinBox {{
    color: {COLORS['text']};
    background: transparent;
    border: 0;
    padding: 6px;
}}
QScrollArea {{ border: 0; }}
"""


class InputStrip(QFrame):
    def __init__(
        self,
        channel: int,
        controller: Evo8Controller,
        invoke: Callable[[Callable[[], None]], None],
    ) -> None:
        super().__init__()
        self.setObjectName("card")
        self.setMinimumWidth(180)
        self._controller = controller
        self._invoke = invoke
        self._channel = channel

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel(f"INPUT {channel + 1}")
        title.setObjectName("sectionTitle")
        subtitle = QLabel("Mic · Line · Instrument" if channel < 2 else "Mic · Line")
        subtitle.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.value = QLabel("−8 dB")
        self.value.setObjectName("value")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value)

        self.gain = QSlider(Qt.Orientation.Vertical)
        self.gain.setRange(-8, 50)
        self.gain.setValue(-8)
        self.gain.setMinimumHeight(230)
        self.gain.setTickInterval(6)
        self.gain.setTickPosition(QSlider.TickPosition.TicksBothSides)
        self.gain.valueChanged.connect(lambda value: self.value.setText(f"{value} dB"))
        self.gain.sliderReleased.connect(self._set_gain)
        layout.addWidget(self.gain, 1, Qt.AlignmentFlag.AlignHCenter)

        buttons = QHBoxLayout()
        self.phantom = self._toggle("48V", self._set_phantom)
        self.mute = self._toggle("MUTE", self._set_mute, danger=True)
        buttons.addWidget(self.phantom)
        buttons.addWidget(self.mute)
        layout.addLayout(buttons)

        self.link = self._toggle("STEREO LINK", self._set_link)
        layout.addWidget(self.link)

    def apply_state(self, state: InputState) -> None:
        for widget in (self.gain, self.phantom, self.mute, self.link):
            widget.blockSignals(True)
        try:
            self.gain.setValue(round(state.gain_db))
            self.value.setText(f"{state.gain_db:g} dB")
            self.phantom.setChecked(state.phantom_power)
            self.mute.setChecked(state.muted)
            self.link.setChecked(state.stereo_linked)
        finally:
            for widget in (self.gain, self.phantom, self.mute, self.link):
                widget.blockSignals(False)

    def _toggle(
        self,
        text: str,
        callback: Callable[[bool], None],
        *,
        danger: bool = False,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setCheckable(True)
        if danger:
            button.setObjectName("danger")
        button.toggled.connect(callback)
        return button

    def _set_gain(self) -> None:
        value = self.gain.value()
        self._invoke(lambda: self._controller.set_input_gain(self._channel, value))

    def _set_phantom(self, enabled: bool) -> None:
        self._invoke(lambda: self._controller.set_phantom_power(self._channel, enabled))

    def _set_mute(self, enabled: bool) -> None:
        self._invoke(lambda: self._controller.set_input_mute(self._channel, enabled))

    def _set_link(self, enabled: bool) -> None:
        self._invoke(lambda: self._controller.set_stereo_link(self._channel, enabled))


class OutputStrip(QFrame):
    def __init__(
        self,
        title_text: str,
        channel: int,
        controller: Evo8Controller,
        invoke: Callable[[Callable[[], None]], None],
    ) -> None:
        super().__init__()
        self.setObjectName("card")
        self.setMinimumWidth(230)
        self._controller = controller
        self._invoke = invoke
        self._channel = channel

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        title = QLabel(title_text)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        hint = QLabel(f"Hardware channels {channel + 1}–{channel + 2}")
        hint.setObjectName("muted")
        layout.addWidget(hint)

        self.value = QLabel("0 dB")
        self.value.setObjectName("value")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value)

        self.volume = QSlider(Qt.Orientation.Vertical)
        self.volume.setRange(-128, 0)
        self.volume.setValue(0)
        self.volume.setMinimumHeight(260)
        self.volume.valueChanged.connect(self._show_value)
        self.volume.sliderReleased.connect(self._set_volume)
        layout.addWidget(self.volume, 1, Qt.AlignmentFlag.AlignHCenter)

        self.mute = QPushButton("MUTE")
        self.mute.setObjectName("danger")
        self.mute.setCheckable(True)
        self.mute.toggled.connect(self._set_mute)
        layout.addWidget(self.mute)

    def apply_state(self, state: OutputState) -> None:
        self.volume.blockSignals(True)
        self.mute.blockSignals(True)
        try:
            self.volume.setValue(round(state.volume_db))
            self._show_value(round(state.volume_db))
            self.mute.setChecked(state.muted)
        finally:
            self.volume.blockSignals(False)
            self.mute.blockSignals(False)

    def _show_value(self, value: int) -> None:
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
        self.setWindowTitle("evoctl · EVO 8")
        self.resize(1180, 760)
        self.setMinimumSize(900, 620)
        self.setStyleSheet(STYLE)
        self.input_strips: list[InputStrip] = []
        self.output_strips: list[OutputStrip] = []
        self.mix_levels: dict[tuple[int, int], QDoubleSpinBox] = {}

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(12)
        root_layout.addWidget(self._top_bar(connected, status_text))

        self.tabs = QTabWidget()
        self.tabs.addTab(self._inputs_page(), "Inputs")
        self.tabs.addTab(self._outputs_page(), "Outputs")
        self.tabs.addTab(self._routing_page(), "Routing")
        root_layout.addWidget(self.tabs, 1)

        self.message = QLabel("Ready")
        self.message.setObjectName("muted")
        root_layout.addWidget(self.message)
        self.setCentralWidget(root)

    def _top_bar(self, connected: bool, status_text: str) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 14, 18, 14)
        brand = QVBoxLayout()
        title = QLabel("EVO 8 CONTROL")
        title.setObjectName("title")
        subtitle = QLabel("Linux hardware mixer and routing")
        subtitle.setObjectName("muted")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        layout.addLayout(brand)
        layout.addStretch(1)
        status = QLabel(status_text)
        status.setObjectName("statusGood" if connected else "statusBad")
        layout.addWidget(status)
        return bar

    def _inputs_page(self) -> QWidget:
        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)
        for channel in range(4):
            strip = InputStrip(channel, self.controller, self.invoke)
            self.input_strips.append(strip)
            layout.addWidget(strip, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def _outputs_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(14)
        main = OutputStrip("MAIN OUTPUT", 0, self.controller, self.invoke)
        headphones = OutputStrip("HEADPHONES", 2, self.controller, self.invoke)
        self.output_strips.extend((main, headphones))
        layout.addWidget(main)
        layout.addWidget(headphones)
        layout.addStretch(1)
        return page

    def _routing_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 4)
        title = QLabel("LOW-LATENCY ROUTING")
        title.setObjectName("sectionTitle")
        hint = QLabel("Mix each hardware, DAW, and loopback source into the four output channels.")
        hint.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(hint)

        sources = ["Mic 1", "Mic 2", "Mic 3", "Mic 4", "DAW 1", "DAW 2", "DAW 3", "DAW 4", "Loopback 1", "Loopback 2"]
        destinations = ["Out 1", "Out 2", "Out 3", "Out 4"]
        table = QTableWidget(len(sources), len(destinations))
        table.setHorizontalHeaderLabels(destinations)
        table.setVerticalHeaderLabels(sources)
        table.setAlternatingRowColors(True)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setDefaultSectionSize(46)
        for destination in range(len(destinations)):
            table.horizontalHeader().setSectionResizeMode(
                destination, QHeaderView.ResizeMode.Stretch
            )
        for source in range(len(sources)):
            for destination in range(len(destinations)):
                level = QDoubleSpinBox()
                level.setRange(-128.0, 0.0)
                level.setSingleStep(0.5)
                level.setDecimals(1)
                level.setSuffix(" dB")
                level.setSpecialValueText("−∞")
                level.setValue(-128.0)
                level.editingFinished.connect(
                    lambda s=source, d=destination, widget=level: self.invoke(
                        lambda: self.controller.set_mix_level(s, d, widget.value())
                    )
                )
                self.mix_levels[source, destination] = level
                table.setCellWidget(source, destination, level)
        layout.addWidget(table, 1)
        return page

    def load_state(self) -> None:
        try:
            for channel, strip in enumerate(self.input_strips):
                strip.apply_state(self.controller.read_input(channel))
            for channel, strip in ((0, self.output_strips[0]), (2, self.output_strips[1])):
                strip.apply_state(self.controller.read_output(channel))
            for (source, destination), widget in self.mix_levels.items():
                widget.blockSignals(True)
                try:
                    widget.setValue(
                        self.controller.read_mix_level(source, destination)
                    )
                finally:
                    widget.blockSignals(False)
        except Exception as error:
            self.message.setText(f"State readback failed: {error}")
            self.message.setStyleSheet(f"color: {COLORS['danger']};")
        else:
            self.message.setText("Hardware state loaded")
            self.message.setStyleSheet(f"color: {COLORS['accent']};")

    def invoke(self, operation: Callable[[], None]) -> None:
        try:
            operation()
        except Exception as error:  # surfaced to the user without killing the UI
            self.message.setText(str(error))
            self.message.setStyleSheet(f"color: {COLORS['danger']};")
        else:
            self.message.setText("Device updated")
            self.message.setStyleSheet(f"color: {COLORS['accent']};")
