"""Note creation and an accessible, per-task card list."""

from datetime import datetime, timezone

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit, QTimeEdit, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QCheckBox, QFrame, QHBoxLayout, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QComboBox, QWidget,
)
from reminders import REMINDER_CHOICES, DEFAULT_REMINDER_MINUTES, validate_reminder_minutes
from ui_icons import CONTROL_STYLE, icon, style_button_box


class AddNoteDialog(QDialog):
    def __init__(self, store, parent=None, default_reminder_minutes=DEFAULT_REMINDER_MINUTES):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Add note — SuperDpet")
        self.setWindowIcon(icon('add'))
        self.resize(380, 260)
        layout = QFormLayout(self)
        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText("What would you like to remember?")
        layout.addRow("Note:", self.text_input)
        default_due = QDateTime.currentDateTime().addSecs(3600)
        self.due_date_input = QDateEdit(default_due.date())
        self.due_date_input.setCalendarPopup(True)
        self.due_date_input.setDisplayFormat("yyyy-MM-dd")
        layout.addRow("Due date:", self.due_date_input)
        self.due_time_input = QTimeEdit(default_due.time())
        self.due_time_input.setDisplayFormat("HH:mm")
        layout.addRow("Due time (local):", self.due_time_input)
        self.remind_me = QComboBox()
        for minutes in REMINDER_CHOICES:
            self.remind_me.addItem(f"{minutes} minute{'s' if minutes != 1 else ''} before", minutes)
        self.remind_me.setCurrentIndex(self.remind_me.findData(validate_reminder_minutes(default_reminder_minutes)))
        layout.addRow("Remind me:", self.remind_me)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save_note)
        style_button_box(buttons)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def save_note(self):
        self.due_date_input.interpretText()
        self.due_time_input.interpretText()
        selected = QDateTime(self.due_date_input.date(), self.due_time_input.time())
        if not selected.isValid():
            QMessageBox.warning(self, "Invalid date", "Please choose a valid date and time.")
            return
        due = datetime.fromtimestamp(selected.toSecsSinceEpoch(), timezone.utc)
        try:
            self.store.add(self.text_input.toPlainText(), due, self.remind_me.currentData())
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Note not saved", str(error))
            return
        self.accept()


class TaskCard(QFrame):
    completion_changed = Signal(str, bool)
    delete_requested = Signal(str)

    def __init__(self, note, parent=None):
        super().__init__(parent)
        self.note_id = note["id"]
        self.setObjectName("taskCard")
        self.setStyleSheet("""
            QFrame#taskCard { background: #f5faff; border: 1px solid #bfd6e9;
                             border-radius: 10px; }
            QCheckBox { spacing: 0px; padding: 6px; }
            QCheckBox::indicator { width: 22px; height: 22px; }
            QCheckBox:focus { background: #d6ebfc; border-radius: 6px; }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 10, 12)
        layout.setSpacing(8)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setWordWrap(True)
        self.title.setMinimumWidth(0)
        self.title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_font = self.title.font()
        title_font.setPointSizeF(max(12, title_font.pointSizeF() + 2))
        title_font.setBold(True)
        self.title.setFont(title_font)
        text_layout.addWidget(self.title)
        self.details = QLabel()
        self.details.setWordWrap(True)
        self.details.setStyleSheet("color: #536e84;")
        detail_font = self.details.font()
        detail_font.setPointSizeF(max(9, title_font.pointSizeF() - 3))
        self.details.setFont(detail_font)
        text_layout.addWidget(self.details)
        layout.addLayout(text_layout, 1)
        self.checkbox = QCheckBox()
        self.checkbox.setMinimumSize(36, 36)
        layout.addWidget(self.checkbox, 0, Qt.AlignmentFlag.AlignTop)
        self.delete_button = QPushButton("×")
        self.delete_button.setFixedSize(36, 36)
        self.delete_button.setAutoDefault(False)
        self.delete_button.setStyleSheet(CONTROL_STYLE + "QPushButton { font-size: 22px; padding: 0px; }")
        layout.addWidget(self.delete_button, 0, Qt.AlignmentFlag.AlignTop)
        self.update_note(note)
        self.checkbox.toggled.connect(lambda checked: self.completion_changed.emit(self.note_id, checked))
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.note_id))

    def update_note(self, note):
        self.title.setText(note["text"])
        font = self.title.font()
        font.setStrikeOut(note["completed"])
        self.title.setFont(font)
        self.title.setStyleSheet("color: #63788b;" if note["completed"] else "color: #24476a;")
        due = datetime.fromisoformat(note["due_at"]).astimezone()
        minutes = note.get("reminder_minutes", DEFAULT_REMINDER_MINUTES)
        status = "Completed" if note["completed"] else "Pending"
        self.details.setText(
            f"Due date: {due:%Y-%m-%d}\nTime: {due:%H:%M %Z}\n"
            f"Remind {minutes} minute{'s' if minutes != 1 else ''} before · {status}")
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(note["completed"])
        self.checkbox.blockSignals(False)
        label = f"Completed: {note['text']}"
        self.checkbox.setAccessibleName(label)
        self.checkbox.setToolTip("Uncheck to mark pending" if note["completed"] else "Check to mark complete")
        self.delete_button.setAccessibleName(f"Delete task: {note['text']}")
        self.delete_button.setToolTip("Delete task…")


class NotesDialog(QDialog):
    note_completed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.rows = {}
        self.setWindowTitle("View notes — SuperDpet")
        self.setWindowIcon(icon('notes'))
        self.resize(560, 420)
        self.setMinimumSize(360, 260)
        layout = QVBoxLayout(self)
        self.empty_label = QLabel("No notes yet. Left-click the pet to add one.")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cards = QWidget()
        self.cards_layout = QVBoxLayout(self.cards)
        self.cards_layout.setContentsMargins(0, 0, 4, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()
        self.scroll.setWidget(self.cards)
        layout.addWidget(self.scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        style_button_box(buttons)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.store.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.empty_label.setVisible(not self.store.notes)
        ids = {note["id"] for note in self.store.notes}
        for note_id in list(self.rows):
            if note_id not in ids:
                row = self.rows.pop(note_id)
                self.cards_layout.removeWidget(row)
                row.hide()
                row.deleteLater()
        for note in self.store.notes:
            row = self.rows.get(note["id"])
            if row is None:
                row = TaskCard(note, self.cards)
                row.completion_changed.connect(self.set_completed)
                row.delete_requested.connect(self.delete_task)
                self.rows[note["id"]] = row
                self.cards_layout.insertWidget(self.cards_layout.count() - 1, row)
            else:
                row.update_note(note)

    def set_completed(self, note_id, completed):
        note = next((n for n in self.store.notes if n["id"] == note_id), None)
        if note is None or note["completed"] == completed:
            return
        try:
            self.store.set_completed(note_id, completed)
        except OSError as error:
            self.refresh()
            QMessageBox.warning(self, "Task status not saved", str(error))
            return
        if completed:
            self.note_completed.emit()

    def delete_task(self, note_id):
        note = next((n for n in self.store.notes if n["id"] == note_id), None)
        if note is None:
            return
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle("Delete task?")
        confirmation.setIcon(QMessageBox.Icon.Question)
        confirmation.setTextFormat(Qt.TextFormat.PlainText)
        confirmation.setText("Delete this task and cancel its future reminder?")
        preview = note["text"]
        confirmation.setInformativeText(preview if len(preview) <= 240 else preview[:240] + "…")
        confirmation.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirmation.setDefaultButton(QMessageBox.StandardButton.No)
        confirmation.setEscapeButton(QMessageBox.StandardButton.No)
        if confirmation.exec() != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete(note_id)
        except OSError as error:
            QMessageBox.warning(self, "Note not deleted", str(error))
