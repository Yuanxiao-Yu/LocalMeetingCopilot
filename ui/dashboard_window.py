from __future__ import annotations

from pathlib import Path

import sounddevice as sd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSlider,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import AppConfig, load_config
from meeting_types import TranscriptEntry


class MeetingDashboard(QMainWindow):
    start_requested = Signal()
    pause_requested = Signal()
    end_requested = Signal()
    export_requested = Signal()
    summary_requested = Signal()
    settings_changed = Signal(object)
    speaker_rename_requested = Signal(object)

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self.config = config or load_config()
        self._entries: list[TranscriptEntry] = []

        self.setWindowTitle("LocalMeetingCopilot")
        self.resize(1180, 760)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search transcript")
        self.search_input.textChanged.connect(self._apply_filter)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "Me", "Remote", "Tasks"])
        self.filter_combo.currentTextChanged.connect(self._apply_filter)
        self.count_label = QLabel("0 entries")

        self.history_list = QListWidget()
        self.history_list.setAlternatingRowColors(True)
        self.history_list.currentItemChanged.connect(lambda _current, _previous: self._sync_speaker_editor())
        self.speaker_name_input = QLineEdit()
        self.speaker_name_input.setPlaceholderText("Selected speaker name")
        self.speaker_apply_button = QPushButton("Apply Speaker")
        self.speaker_apply_button.clicked.connect(self._request_speaker_rename)
        self.speaker_apply_button.setEnabled(False)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(18, 18, 12, 18)
        left_layout.setSpacing(10)
        title = QLabel("Transcript")
        title.setObjectName("paneTitle")
        left_layout.addWidget(title)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        filter_row.addWidget(self.search_input, 1)
        filter_row.addWidget(self.filter_combo)
        filter_row.addWidget(self.count_label)
        left_layout.addLayout(filter_row)
        speaker_row = QHBoxLayout()
        speaker_row.setSpacing(8)
        speaker_row.addWidget(self.speaker_name_input, 1)
        speaker_row.addWidget(self.speaker_apply_button)
        left_layout.addLayout(speaker_row)
        left_layout.addWidget(self.history_list, 1)

        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        self.model_label = QLabel(
            f"Ollama: {self.config.ollama_model} | Profile: {self.config.meeting_profile}"
        )
        self.queue_label = QLabel("Translation queue: 0")
        self.latency_label = QLabel("Latency: n/a")
        self.performance_label = QLabel("Performance: n/a")
        self.performance_label.setWordWrap(True)
        self.preview_label = QLabel("No active speech")
        self.preview_label.setWordWrap(True)
        self.report_view = QTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText("Exported report preview")

        self.start_button = QPushButton("Start")
        self.pause_button = QPushButton("Pause")
        self.end_button = QPushButton("End")
        self.export_button = QPushButton("Export")
        self.summary_button = QPushButton("Summarize")
        style = QApplication.style()
        self.start_button.setIcon(style.standardIcon(style.StandardPixmap.SP_MediaPlay))
        self.pause_button.setIcon(style.standardIcon(style.StandardPixmap.SP_MediaPause))
        self.end_button.setIcon(style.standardIcon(style.StandardPixmap.SP_MediaStop))
        self.export_button.setIcon(style.standardIcon(style.StandardPixmap.SP_DialogSaveButton))
        self.summary_button.setIcon(style.standardIcon(style.StandardPixmap.SP_FileDialogDetailedView))
        self.start_button.clicked.connect(self.start_requested.emit)
        self.pause_button.clicked.connect(self.pause_requested.emit)
        self.end_button.clicked.connect(self.end_requested.emit)
        self.export_button.clicked.connect(self.export_requested.emit)
        self.summary_button.clicked.connect(self.summary_requested.emit)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.pause_button)
        buttons.addWidget(self.end_button)
        buttons.addWidget(self.summary_button)
        buttons.addWidget(self.export_button)

        self.profile_combo = QComboBox()
        self.profile_combo.addItem("German", "de")
        self.profile_combo.addItem("English", "en")
        self.profile_combo.addItem("German + English", "de-en")
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Fast", "fast")
        self.preset_combo.addItem("Balanced", "balanced")
        self.preset_combo.addItem("Accurate", "accurate")
        self.style_combo = QComboBox()
        self.style_combo.addItem("Meeting Notes", "meeting")
        self.style_combo.addItem("Literal", "literal")
        self.style_combo.addItem("Natural", "natural")
        self.mic_combo = QComboBox()
        self.remote_combo = QComboBox()
        self.capture_mic_check = QCheckBox("Mic [Me]")
        self.capture_remote_check = QCheckBox("Remote")
        self.save_reports_check = QCheckBox("Save reports")
        self.privacy_check = QCheckBox("Privacy")
        self.debug_audio_check = QCheckBox("Debug WAV")
        self.auto_summary_check = QCheckBox("Auto summary on End")
        self.vad_sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.vad_sensitivity_slider.setRange(0, 100)
        self.vad_sensitivity_slider.setSingleStep(5)
        self.vad_sensitivity_label = QLabel("85")
        self.refresh_devices_button = QPushButton("Refresh Devices")
        self.refresh_devices_button.clicked.connect(lambda: self.refresh_audio_devices())
        self._wire_settings_signals()
        self.refresh_audio_devices(emit=False)
        self.sync_from_config(emit=False)

        settings_layout = QFormLayout()
        settings_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        settings_layout.addRow("Profile", self.profile_combo)
        settings_layout.addRow("Preset", self.preset_combo)
        settings_layout.addRow("Style", self.style_combo)
        settings_layout.addRow("Mic", self.mic_combo)
        settings_layout.addRow("Remote", self.remote_combo)
        track_row = QHBoxLayout()
        track_row.addWidget(self.capture_mic_check)
        track_row.addWidget(self.capture_remote_check)
        settings_layout.addRow("Tracks", track_row)
        privacy_row = QHBoxLayout()
        privacy_row.addWidget(self.save_reports_check)
        privacy_row.addWidget(self.privacy_check)
        privacy_row.addWidget(self.debug_audio_check)
        settings_layout.addRow("Storage", privacy_row)
        settings_layout.addRow("End", self.auto_summary_check)
        vad_row = QHBoxLayout()
        vad_row.addWidget(self.vad_sensitivity_slider, 1)
        vad_row.addWidget(self.vad_sensitivity_label)
        settings_layout.addRow("VAD Sensitivity", vad_row)
        settings_layout.addRow("", self.refresh_devices_button)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 18, 18, 18)
        right_layout.setSpacing(12)
        control_title = QLabel("Control")
        control_title.setObjectName("paneTitle")
        right_layout.addWidget(control_title)
        right_layout.addLayout(buttons)
        right_layout.addLayout(settings_layout)
        right_layout.addWidget(QLabel("Status"))
        right_layout.addWidget(self.status_label)
        right_layout.addWidget(QLabel("Model"))
        right_layout.addWidget(self.model_label)
        right_layout.addWidget(self.queue_label)
        right_layout.addWidget(self.latency_label)
        right_layout.addWidget(self.performance_label)
        right_layout.addWidget(QLabel("Live Preview"))
        right_layout.addWidget(self.preview_label)
        right_layout.addWidget(QLabel("Report"))
        right_layout.addWidget(self.report_view, 1)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([720, 460])

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(splitter)
        self.setCentralWidget(root)

        self.setStyleSheet(
            """
            QMainWindow {
                background: #F7F8FA;
            }
            QLabel#paneTitle {
                color: #20242B;
                font-size: 18px;
                font-weight: 700;
            }
            QListWidget, QTextEdit, QLineEdit {
                background: #FFFFFF;
                border: 1px solid #D9DEE7;
                border-radius: 6px;
                color: #20242B;
                font-size: 14px;
            }
            QListWidget::item {
                padding: 10px;
            }
            QPushButton {
                min-height: 34px;
                padding: 6px 12px;
                border: 1px solid #C7CED9;
                border-radius: 6px;
                background: #FFFFFF;
            }
            QPushButton:hover {
                background: #EEF5FF;
            }
            """
        )
        self.set_running_state(False)

    def add_entry(self, entry: TranscriptEntry) -> None:
        self._entries.append(entry)
        self._add_item(entry)
        self._update_count_label()
        self._apply_filter()
        self.history_list.scrollToBottom()

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_running_state(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.pause_button.setEnabled(running)
        self.end_button.setEnabled(running)
        self.export_button.setEnabled(True)
        self.summary_button.setEnabled(True)

    def set_summary_running(self, running: bool) -> None:
        self.summary_button.setEnabled(not running)
        self.summary_button.setText("Summarizing" if running else "Summarize")

    def set_queue_depth(self, depth: int) -> None:
        self.queue_label.setText(f"Translation queue: {depth}")

    def set_latency(self, label: str) -> None:
        self.latency_label.setText(f"Latency: {label or 'n/a'}")

    def set_performance(self, label: str) -> None:
        self.performance_label.setText(f"Performance: {label or 'n/a'}")

    def set_preview(self, speaker: str, text: str) -> None:
        self.preview_label.setText(f"[{speaker}] {text}")

    def set_translation_preview(self, speaker: str, original_text: str, translated_partial: str) -> None:
        self.preview_label.setText(
            f"[{speaker}] {original_text}\n中文: {translated_partial}"
        )

    def set_report(self, markdown: str, path: Path | None = None) -> None:
        heading = f"Saved to {path}\n\n" if path else ""
        self.report_view.setPlainText(heading + markdown)

    def rename_speaker_entries(self, old: str, new: str) -> None:
        for entry in self._entries:
            if entry.speaker == old:
                entry.speaker = new
        for row in range(self.history_list.count()):
            item = self.history_list.item(row)
            entry = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(entry, TranscriptEntry):
                item.setText(_entry_text(entry))
        self._sync_speaker_editor()
        self._apply_filter()

    def _add_item(self, entry: TranscriptEntry) -> None:
        item = QListWidgetItem(_entry_text(entry))
        item.setData(Qt.ItemDataRole.UserRole, entry)
        self.history_list.addItem(item)

    def refresh_audio_devices(self, emit: bool = True) -> None:
        current_mic = self.mic_combo.currentData()
        current_remote = self.remote_combo.currentData()
        self.mic_combo.blockSignals(True)
        self.remote_combo.blockSignals(True)
        self.mic_combo.clear()
        self.remote_combo.clear()
        self.mic_combo.addItem("Default", None)
        self.remote_combo.addItem("Auto", None)
        try:
            devices = sd.query_devices()
        except Exception:
            devices = []

        for index, device in enumerate(devices):
            if int(device.get("max_input_channels", 0)) <= 0:
                continue
            label = f"input[{index}] {device['name']}"
            self.mic_combo.addItem(label, index)
            self.remote_combo.addItem(label, index)

        self._select_combo_value(
            self.mic_combo,
            self.config.mic_device_index if self.config.mic_device_index is not None else current_mic,
        )
        self._select_combo_value(
            self.remote_combo,
            self.config.remote_device_index
            if self.config.remote_device_index is not None
            else current_remote,
        )
        self.mic_combo.blockSignals(False)
        self.remote_combo.blockSignals(False)
        if emit:
            self._emit_settings_changed()

    def sync_from_config(self, emit: bool = False) -> None:
        widgets = (
            self.profile_combo,
            self.preset_combo,
            self.style_combo,
            self.mic_combo,
            self.remote_combo,
        )
        for widget in widgets:
            widget.blockSignals(True)
        for check in (
            self.capture_mic_check,
            self.capture_remote_check,
            self.save_reports_check,
            self.privacy_check,
            self.debug_audio_check,
            self.auto_summary_check,
        ):
            check.blockSignals(True)
        self.vad_sensitivity_slider.blockSignals(True)

        self._select_combo_value(self.profile_combo, self.config.meeting_profile)
        self._select_combo_value(self.preset_combo, self.config.model_preset)
        self._select_combo_value(self.style_combo, self.config.translation_style)
        self._select_combo_value(self.mic_combo, self.config.mic_device_index)
        self._select_combo_value(self.remote_combo, self.config.remote_device_index)
        self.capture_mic_check.setChecked(self.config.capture_mic_enabled)
        self.capture_remote_check.setChecked(self.config.capture_remote_enabled)
        self.save_reports_check.setChecked(self.config.save_reports_enabled)
        self.privacy_check.setChecked(self.config.privacy_mode)
        self.debug_audio_check.setChecked(self.config.debug_audio_enabled)
        self.auto_summary_check.setChecked(self.config.auto_summary_on_end)
        self.vad_sensitivity_slider.setValue(self.config.vad_sensitivity)
        self._update_vad_sensitivity_label(self.config.vad_sensitivity)
        self.model_label.setText(
            f"Ollama: {self.config.ollama_model} | Profile: {self.config.meeting_profile} | Preset: {self.config.model_preset}"
        )

        for widget in widgets:
            widget.blockSignals(False)
        for check in (
            self.capture_mic_check,
            self.capture_remote_check,
            self.save_reports_check,
            self.privacy_check,
            self.debug_audio_check,
            self.auto_summary_check,
        ):
            check.blockSignals(False)
        self.vad_sensitivity_slider.blockSignals(False)
        if emit:
            self._emit_settings_changed()

    def _wire_settings_signals(self) -> None:
        for combo in (
            self.profile_combo,
            self.preset_combo,
            self.style_combo,
            self.mic_combo,
            self.remote_combo,
        ):
            combo.currentIndexChanged.connect(self._emit_settings_changed)
        for check in (
            self.capture_mic_check,
            self.capture_remote_check,
            self.save_reports_check,
            self.privacy_check,
            self.debug_audio_check,
            self.auto_summary_check,
        ):
            check.toggled.connect(self._emit_settings_changed)
        self.vad_sensitivity_slider.valueChanged.connect(self._on_vad_sensitivity_changed)

    def _emit_settings_changed(self) -> None:
        self.settings_changed.emit(
            {
                "profile": self.profile_combo.currentData(),
                "preset": self.preset_combo.currentData(),
                "style": self.style_combo.currentData(),
                "mic_device_index": self.mic_combo.currentData(),
                "remote_device_index": self.remote_combo.currentData(),
                "capture_mic_enabled": self.capture_mic_check.isChecked(),
                "capture_remote_enabled": self.capture_remote_check.isChecked(),
                "save_reports_enabled": self.save_reports_check.isChecked(),
                "privacy_mode": self.privacy_check.isChecked(),
                "debug_audio_enabled": self.debug_audio_check.isChecked(),
                "auto_summary_on_end": self.auto_summary_check.isChecked(),
                "vad_sensitivity": self.vad_sensitivity_slider.value(),
            }
        )

    def _on_vad_sensitivity_changed(self, value: int) -> None:
        self._update_vad_sensitivity_label(value)
        self._emit_settings_changed()

    def _update_vad_sensitivity_label(self, value: int) -> None:
        self.vad_sensitivity_label.setText(str(value))

    def _sync_speaker_editor(self) -> None:
        item = self.history_list.currentItem()
        if item is None:
            self.speaker_name_input.clear()
            self.speaker_apply_button.setEnabled(False)
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, TranscriptEntry):
            self.speaker_name_input.clear()
            self.speaker_apply_button.setEnabled(False)
            return
        self.speaker_name_input.setText(entry.speaker)
        self.speaker_apply_button.setEnabled(True)

    def _request_speaker_rename(self) -> None:
        item = self.history_list.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, TranscriptEntry):
            return
        new_name = self.speaker_name_input.text().strip()
        if not new_name or new_name == entry.speaker:
            return
        self.speaker_rename_requested.emit(
            {
                "old": entry.speaker,
                "new": new_name,
                "entry_id": entry.entry_id,
            }
        )

    def _select_combo_value(self, combo: QComboBox, value: object) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(0)

    def _apply_filter(self) -> None:
        needle = self.search_input.text().strip().lower()
        mode = self.filter_combo.currentText()
        for row in range(self.history_list.count()):
            item = self.history_list.item(row)
            entry = item.data(Qt.ItemDataRole.UserRole)
            text_matches = not needle or needle in item.text().lower()
            filter_matches = _entry_matches_filter(entry, mode)
            item.setHidden(not (text_matches and filter_matches))
        self._update_count_label()

    def _update_count_label(self) -> None:
        visible = sum(
            not self.history_list.item(row).isHidden() for row in range(self.history_list.count())
        )
        total = self.history_list.count()
        self.count_label.setText(f"{visible}/{total} entries")


def _entry_text(entry: TranscriptEntry) -> str:
    meta = []
    if entry.confidence is not None:
        meta.append(f"conf {entry.confidence:0.2f}")
    if entry.latency_label:
        meta.append(entry.latency_label)
    suffix = f" ({' | '.join(meta)})" if meta else ""
    return (
        f"[{entry.timestamp}] [{entry.speaker}]{suffix} {entry.original_text}\n"
        f"中文: {entry.chinese_translation}"
    )


def _entry_matches_filter(entry: TranscriptEntry, mode: str) -> bool:
    if mode == "All":
        return True
    if mode == "Me":
        return entry.speaker == "Me"
    if mode == "Remote":
        return entry.speaker != "Me"
    if mode == "Tasks":
        return _looks_like_action(entry)
    return True


def _looks_like_action(entry: TranscriptEntry) -> bool:
    combined = f"{entry.original_text} {entry.chinese_translation}".lower()
    markers = (
        "你",
        "我会",
        "我可以",
        "需要",
        "please",
        "could you",
        "can you",
        "i will",
        "ich kann",
        "ich werde",
        "bitte",
    )
    return entry.speaker == "Me" or any(marker in combined for marker in markers)
