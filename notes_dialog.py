"""Small dialogs for adding notes and marking them complete."""

from datetime import datetime, timezone

from PySide6.QtCore import QDateTime, Qt, Signal
from PySide6.QtWidgets import (
    QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout, QComboBox,
)
from reminders import REMINDER_CHOICES, DEFAULT_REMINDER_MINUTES, validate_reminder_minutes


class AddNoteDialog(QDialog):
    def __init__(self, store, parent=None, default_reminder_minutes=DEFAULT_REMINDER_MINUTES):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Add note — SuperDpet")
        self.resize(380, 260)
        layout = QFormLayout(self)
        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText("What would you like to remember?")
        layout.addRow("Note:", self.text_input)
        self.due_input = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.due_input.setCalendarPopup(True)
        self.due_input.setDisplayFormat("yyyy-MM-dd HH:mm")
        layout.addRow("Due (local time):", self.due_input)
        self.remind_me = QComboBox()
        for minutes in REMINDER_CHOICES:
            self.remind_me.addItem(f"{minutes} minute{'s' if minutes != 1 else ''} before", minutes)
        self.remind_me.setCurrentIndex(self.remind_me.findData(validate_reminder_minutes(default_reminder_minutes)))
        layout.addRow("Remind me:", self.remind_me)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save_note)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def save_note(self):
        self.due_input.interpretText()
        selected = self.due_input.dateTime()
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


class NotesDialog(QDialog):
    note_completed = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("View notes — SuperDpet")
        self.resize(420, 320)
        layout = QVBoxLayout(self)
        self.empty_label = QLabel("No notes yet. Left-click the pet to add one.")
        layout.addWidget(self.empty_label)
        self.list_widget = QListWidget()
        self.list_widget.setWordWrap(True)
        layout.addWidget(self.list_widget)
        self.complete_button = QPushButton("Mark selected note complete")
        self.complete_button.clicked.connect(self.complete_selected)
        layout.addWidget(self.complete_button)
        self.delete_button = QPushButton("Delete selected completed note")
        self.delete_button.clicked.connect(self.delete_selected)
        layout.addWidget(self.delete_button)
        self.list_widget.currentItemChanged.connect(self.update_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def refresh(self):
        self.list_widget.clear()
        self.empty_label.setVisible(not self.store.notes)
        for note in self.store.notes:
            due = datetime.fromisoformat(note["due_at"]).astimezone()
            state = "Complete" if note["completed"] else "Pending"
            item = QListWidgetItem(
                f"{note['text']}\nDue: {due:%Y-%m-%d %H:%M %Z}  |  {state}\n"
                f"Remind: {note.get('reminder_minutes', DEFAULT_REMINDER_MINUTES)} minute(s) before"
            )
            item.setData(Qt.ItemDataRole.UserRole, note["id"])
            self.list_widget.addItem(item)
        self.update_button()

    def update_button(self, *args):
        item = self.list_widget.currentItem()
        note_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.complete_button.setEnabled(any(
            note["id"] == note_id and not note["completed"] for note in self.store.notes
        ))
        self.delete_button.setEnabled(any(
            note["id"] == note_id and note["completed"] for note in self.store.notes
        ))

    def delete_selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        try:
            self.store.delete_completed(item.data(Qt.ItemDataRole.UserRole))
        except OSError as error:
            QMessageBox.warning(self, "Note not deleted", str(error))
            return
        self.refresh()

    def complete_selected(self):
        item = self.list_widget.currentItem()
        if item is None:
            return
        try:
            self.store.complete(item.data(Qt.ItemDataRole.UserRole))
        except OSError as error:
            QMessageBox.warning(self, "Completion not saved", str(error))
            return
        self.refresh()
        self.note_completed.emit()
