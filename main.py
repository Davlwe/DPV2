import sys
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import QEvent, QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QLabel, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from notes_dialog import AddNoteDialog, NotesDialog
from storage import NoteStore
from reminders import REMINDER_LEAD, pending_reminders
from preferences import Preferences
from settings_dialog import SettingsDialog
from startup import StartupRegistration


class PetWindow(QWidget):
    def __init__(self, preferences=None):
        super().__init__()
        self.quitting = False
        self.saved_pet_position = None
        self.store = NoteStore()
        self.preferences = preferences if preferences is not None else Preferences()
        self.startup = StartupRegistration()
        self.setWindowTitle("SuperDpet — My Desktop Pet")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(200, 270)
        self.press_position = None
        self.dragging = False
        self.system_drag = False
        self.drag_threshold = QApplication.startDragDistance()
        self.setMouseTracking(True)

        # Child widgets live inside this window; only the square moves.
        self.pet = QLabel(self)
        self.pet.setGeometry(50, 80, 100, 100)
        self.pet.setStyleSheet("background-color: #6C8CFF;")
        self.pet.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.bubble = QLabel("Hello!", self)
        self.bubble.setGeometry(30, 10, 140, 45)
        self.bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubble.setStyleSheet(
            "background-color: white; color: #222222;"
            "border: 2px solid #6C8CFF; border-radius: 12px;"
        )
        self.bubble.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.bubble.hide()

        # All controls are hidden together when the interaction times out.
        self.note_actions = QWidget(self)
        self.note_actions.setGeometry(5, 230, 190, 32)
        self.add_button = QPushButton("Add note", self.note_actions)
        self.add_button.setGeometry(0, 0, 90, 30)
        self.add_button.clicked.connect(self.add_note)
        self.view_button = QPushButton("View notes", self.note_actions)
        self.view_button.setGeometry(95, 0, 95, 30)
        self.view_button.clicked.connect(self.view_notes)
        self.note_actions.hide()

        # Mouse activity restarts the inactivity countdown.
        self.bubble_timer = QTimer(self)
        self.bubble_timer.setSingleShot(True)
        self.bubble_timer.setInterval(4000)
        self.bubble_timer.timeout.connect(self.hide_interaction)

        self.settings_menu = QMenu(self)
        self.settings_menu.addAction("Settings", self.show_settings)
        self.settings_menu.addAction("View notes", self.view_notes)
        self.settings_menu.addAction(
            "Developer test: create reminder in 5 seconds", self.create_test_reminder
        )
        self.settings_menu.addSeparator()
        self.settings_menu.addAction("Quit", self.close)
        self.settings_menu.aboutToShow.connect(self.bubble_timer.stop)
        self.settings_menu.aboutToHide.connect(self.restart_idle_timer)

        # Keep an obvious exit available now that the title bar is gone.
        self.quit_button = QPushButton("Quit", self)
        self.quit_button.setGeometry(65, 195, 70, 28)
        self.quit_button.clicked.connect(self.close)
        self.quit_button.hide()
        for control in (self.note_actions, self.add_button, self.view_button, self.quit_button):
            control.setMouseTracking(True)
            control.installEventFilter(self)

        self.idle_animation = QPropertyAnimation(self.pet, b"pos", self)
        self.idle_animation.setDuration(3200)
        self.idle_animation.setStartValue(QPoint(50, 80))
        self.idle_animation.setKeyValueAt(0.5, QPoint(50, 72))
        self.idle_animation.setEndValue(QPoint(50, 80))
        self.idle_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.idle_animation.setLoopCount(-1)  # Repeat until the app closes.
        self.idle_animation.start()

        # A separate, non-modal message keeps long notes readable without
        # replacing the hello bubble or blocking dragging and note controls.
        self.reminder_dialog = QDialog(self)
        self.reminder_dialog.setWindowTitle("SuperDpet — Reminder")
        self.reminder_dialog.resize(380, 260)
        reminder_layout = QVBoxLayout(self.reminder_dialog)
        reminder_layout.addWidget(QLabel("Time to check your notes!"))
        self.reminder_text = QPlainTextEdit()
        self.reminder_text.setReadOnly(True)
        reminder_layout.addWidget(self.reminder_text)
        dismiss = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        dismiss.rejected.connect(self.reminder_dialog.reject)
        reminder_layout.addWidget(dismiss)
        self.reminder_dialog.finished.connect(self.finish_reminder)

        self.reminder_timer = QTimer(self)
        self.reminder_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.reminder_timer.setInterval(250)
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.setup_tray()
        QApplication.instance().aboutToQuit.connect(self.stop_background_work)
        if self.store.load_error is None:
            self.reminder_timer.start()
            QTimer.singleShot(0, self.check_reminders)

        if self.store.load_error is not None:
            QTimer.singleShot(0, self.show_load_error)
        QTimer.singleShot(0, self.offer_startup_permission)

    def offer_startup_permission(self):
        if (self.quitting or self.preferences.startup_permission is not None
                or self.preferences.load_error or self.startup.unsupported_reason):
            return
        # Let the tray/storage notices finish before asking for optional startup.
        if QApplication.activeModalWidget() is not None:
            QTimer.singleShot(250, self.offer_startup_permission)
            return
        self.show_settings()

    def show_settings(self):
        self.hide_interaction()
        first_run = (self.preferences.startup_permission is None
                     and not self.preferences.load_error and not self.startup.unsupported_reason)
        SettingsDialog(self.preferences, self.startup, self, first_run=first_run).exec()

    def check_reminders(self):
        if self.quitting:
            return
        notes = pending_reminders(self.store.notes)
        if not notes:
            return
        try:
            # Save first, so later timer ticks and restarts do not repeat them.
            self.store.mark_reminded({note["id"] for note in notes})
        except OSError as error:
            self.reminder_timer.stop()
            QMessageBox.warning(
                self, "Reminders paused: could not save",
                f"{error}\n\nFix the storage problem and restart the app to retry. "
                "These reminders have not been marked as shown.",
            )
            return
        for note in notes:
            due = datetime.fromisoformat(note["due_at"]).astimezone()
            self.reminder_text.appendPlainText(
                f"{note['text']}\nDue: {due:%Y-%m-%d %H:%M:%S %Z}\n"
            )
        self.pet.setStyleSheet("background-color: #FFB347;")
        self.idle_animation.setDuration(1200)
        self.reminder_dialog.show()
        self.reminder_dialog.raise_()

    def finish_reminder(self, result):
        self.reminder_text.clear()
        self.pet.setStyleSheet("background-color: #6C8CFF;")
        self.idle_animation.setDuration(3200)

    def create_test_reminder(self):
        try:
            self.store.add(
                "[DEVELOPER TEST] Your reminder is working!",
                datetime.now(timezone.utc) + REMINDER_LEAD + timedelta(seconds=5),
            )
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Test note not saved", str(error))

    def setup_tray(self):
        # Keep the process alive when only the tray is visible, including after
        # closing a notes or reminder dialog while the pet is hidden.
        QApplication.instance().setQuitOnLastWindowClosed(False)
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#6C8CFF"))
        self.tray = QSystemTrayIcon(QIcon(pixmap), self)
        self.tray.setToolTip("SuperDpet")
        self.tray_menu = QMenu(self)
        self.tray_menu.addAction("Show Pet", self.show_pet)
        self.tray_menu.addAction("Hide Pet", self.hide_pet)
        self.tray_menu.addAction("View Notes", self.view_notes)
        self.tray_menu.addAction("Settings", self.show_settings)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction("Quit", self.close)
        self.tray.setContextMenu(self.tray_menu)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        else:
            QTimer.singleShot(0, self.explain_missing_tray)

    def explain_missing_tray(self):
        if self.quitting:
            return
        self.tray_notice = QMessageBox(
            QMessageBox.Icon.Information, "System tray unavailable",
            "This desktop does not currently provide a system tray. "
            "The pet will stay accessible; hiding to the tray is unavailable.\n\n"
            "Reminders still work. Left-click the pet for the Quit button, "
            "or right-click it and choose Quit to exit completely.",
            QMessageBox.StandardButton.Ok, self,
        )
        self.tray_notice.open()

    def hide_pet(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.show_pet()
            self.explain_missing_tray()
            return
        if not self.isVisible():
            return
        self.saved_pet_position = QPoint(self.pos())
        reminder_visible = self.reminder_dialog.isVisible()
        self.hide_interaction()
        self.hide()
        # Hiding a parent can also hide its dialogs. An active reminder should
        # remain readable, and new reminders still open while the pet is hidden.
        if reminder_visible:
            self.reminder_dialog.show()

    def show_pet(self):
        if self.quitting:
            return
        if not self.isVisible() and self.saved_pet_position is not None:
            position = QPoint(self.saved_pet_position)
            screens = QApplication.screens()
            screen = next((s for s in screens if s.availableGeometry().contains(
                position + self.rect().center()
            )), QApplication.primaryScreen())
            if screen is not None:
                area = screen.availableGeometry()
                position.setX(max(area.left(), min(position.x(), area.right() - self.width() + 1)))
                position.setY(max(area.top(), min(position.y(), area.bottom() - self.height() + 1)))
            self.move(position)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def stop_background_work(self):
        self.quitting = True
        self.reminder_timer.stop()
        self.bubble_timer.stop()
        self.idle_animation.stop()
        self.tray.hide()

    def closeEvent(self, event):
        # Closing the pet still means Quit; only Hide Pet hides to the tray.
        self.stop_background_work()
        self.reminder_dialog.close()
        super().closeEvent(event)
        QApplication.instance().quit()

    def show_load_error(self):
        QMessageBox.warning(
            self, "Could not load notes",
            f"Your notes file could not be read:\n{self.store.path}\n\n"
            f"{self.store.load_error}\n\n"
            "The file has been left untouched. Saving is disabled for this session.",
        )

    def add_note(self):
        self.hide_interaction()
        AddNoteDialog(self.store, self).exec()

    def view_notes(self):
        self.hide_interaction()
        NotesDialog(self.store, self).exec()

    def show_interaction(self):
        self.bubble.show()
        self.note_actions.show()
        self.quit_button.show()
        self.restart_idle_timer()

    def hide_interaction(self):
        self.bubble_timer.stop()
        self.bubble.hide()
        self.note_actions.hide()
        self.quit_button.hide()

    def restart_idle_timer(self):
        if self.bubble.isVisible():
            self.bubble_timer.start()

    def eventFilter(self, watched, event):
        # Observe button activity without consuming their normal click events.
        if event.type() == QEvent.Type.MouseButtonPress:
            self.bubble_timer.stop()
        elif event.type() in (QEvent.Type.Enter, QEvent.Type.MouseMove,
                              QEvent.Type.MouseButtonRelease):
            if not QApplication.mouseButtons():
                self.restart_idle_timer()
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_position = event.globalPosition().toPoint()
            self.window_start = self.pos()
            self.dragging = False
            self.system_drag = False
            self.bubble_timer.stop()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.settings_menu.popup(event.globalPosition().toPoint())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.press_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            offset = event.globalPosition().toPoint() - self.press_position
            if not self.dragging and offset.manhattanLength() >= self.drag_threshold:
                self.dragging = True
                self.hide_interaction()
                # Let the desktop manage dragging where supported (including Wayland).
                handle = self.windowHandle()
                self.system_drag = bool(handle and handle.startSystemMove())
            if self.dragging and not self.system_drag:
                self.move(self.window_start + offset)
            event.accept()
        else:
            self.restart_idle_timer()
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.press_position is not None:
            offset = event.globalPosition().toPoint() - self.press_position
            is_click = not self.dragging and offset.manhattanLength() < self.drag_threshold
            self.press_position = None
            self.dragging = False
            self.system_drag = False
            if is_click:
                self.show_interaction()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("SuperDpet")
    preferences = Preferences()
    if "--startup" in sys.argv and (
        preferences.load_error or preferences.startup_permission is not True
        or StartupRegistration().unsupported_reason
    ):
        return 0
    window = PetWindow(preferences)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
