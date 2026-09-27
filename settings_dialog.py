"""Explicit startup permission and a reversible Settings control."""

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QMessageBox, QVBoxLayout, QComboBox,
)
from reminders import REMINDER_CHOICES


class SettingsDialog(QDialog):
    def __init__(self, preferences, startup, parent=None, first_run=False):
        super().__init__(parent)
        self.preferences = preferences
        self.startup = startup
        self.first_run = first_run
        self.setWindowTitle("Startup permission — SuperDpet" if first_run else "Settings — SuperDpet")
        self.resize(450, 240)
        layout = QVBoxLayout(self)
        explanation = QLabel(
            "Would you like SuperDpet to open automatically when you sign in?\n\n"
            "This is optional and off by default. You can change it here later. "
            "Quit stops the app and reminders for the current session."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.start_at_login = QCheckBox("Start SuperDpet when I sign in")
        layout.addWidget(self.start_at_login)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        reminder_label = QLabel("Default reminder for new notes:")
        layout.addWidget(reminder_label)
        self.reminder_default = QComboBox()
        for minutes in REMINDER_CHOICES:
            self.reminder_default.addItem(f"{minutes} minute{'s' if minutes != 1 else ''}", minutes)
        self.reminder_default.setCurrentIndex(self.reminder_default.findData(preferences.default_reminder_minutes))
        reminder_label.setBuddy(self.reminder_default)
        layout.addWidget(self.reminder_default)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        if first_run:
            self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("No thanks")
        # Enter must never grant startup permission accidentally.
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setAutoDefault(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setDefault(True)
        layout.addWidget(self.buttons)
        self.refresh()

    def refresh(self):
        error = self.startup.unsupported_reason
        if self.preferences.load_error:
            error = (
                f"Preferences could not be loaded: {self.preferences.load_error}\n"
                "The file was left untouched. Startup changes are disabled."
            )
        try:
            registered = self.startup.is_enabled() if not error else False
        except (OSError, ValueError) as problem:
            error = f"Could not inspect startup registration: {problem}"
            registered = False
        self.start_at_login.setChecked(registered and self.preferences.startup_permission is True)
        self.start_at_login.setEnabled(not error)
        self.reminder_default.setEnabled(not self.preferences.load_error)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(not self.preferences.load_error)
        self.status.setText(error or (
            "Enabled for your next sign-in. Keep this app and its Python environment in their current locations."
            if self.start_at_login.isChecked() else
            "Off. Check the box and click Save to allow startup for your user account."
        ))

    def save(self):
        allowed = self.start_at_login.isChecked()
        minutes = self.reminder_default.currentData()
        try:
            # Save consent first. The --startup entry point refuses to launch
            # without it, even if removing an old OS entry subsequently fails.
            if self.start_at_login.isEnabled():
                self.preferences.save_startup_permission(allowed, minutes)
            else:
                # WSL/unsupported startup must not disable ordinary preferences
                # or silently alter existing startup consent/registration.
                self.preferences.save_default_reminder_minutes(minutes)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Preferences not saved", str(error))
            return
        if not self.start_at_login.isEnabled():
            self.accept()
            return
        try:
            self.startup.set_enabled(allowed)
        except (OSError, ValueError) as error:
            self.refresh()
            QMessageBox.warning(
                self, "Startup registration not updated",
                f"Your permission choice was saved, but the system entry could not be updated:\n{error}\n\n"
                "Open Settings to retry. Turning permission off prevents startup launches "
                "even if an old entry could not be removed.",
            )
            return
        self.accept()

    def reject(self):
        if self.first_run and self.preferences.startup_permission is None:
            try:
                self.preferences.save_startup_permission(False)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "Startup preference not saved", str(error))
        super().reject()
