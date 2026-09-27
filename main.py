import sys
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, QElapsedTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QGraphicsDropShadowEffect, QLabel, QMenu, QMessageBox,
    QPlainTextEdit, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from notes_dialog import AddNoteDialog, NotesDialog
from storage import NoteStore
from reminders import pending_reminders
from preferences import Preferences
from settings_dialog import SettingsDialog
from startup import StartupRegistration
from idle_behavior import IdleController, PetSprite
from mood import TaskMood, MOOD_COLORS, MOOD_REFRESH_MS

GREETINGS = ("Hi, how can I help you today?", "Wanna add a note or reminder?")


class PetWindow(QWidget):
    def __init__(self, preferences=None):
        super().__init__()
        self.quitting = False
        self.reminder_active = False
        self.drag_activity = QElapsedTimer()
        self.drag_activity.start()
        self.saved_pet_position = None
        self.store = NoteStore()
        self.preferences = preferences if preferences is not None else Preferences()
        self.startup = StartupRegistration()
        self.setWindowTitle("SuperDpet — My Desktop Pet")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        sprite = QPixmap(str(Path(__file__).resolve().parent / "assets" / "superdpet_standing_1024.png"))
        self.has_sprite = not sprite.isNull()
        self.setFixedSize(288, 400) if self.has_sprite else self.setFixedSize(200, 270)
        self.press_position = None
        self.dragging = False
        self.system_drag = False
        self.drag_threshold = QApplication.startDragDistance()
        self.setMouseTracking(True)

        # The window and hit area stay fixed during idle and reaction animations.
        self.pet = PetSprite(self)
        if self.has_sprite:
            self.pet.setGeometry(0, 48, 288, 288)
            self.pet.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Keep source resolution for smooth painting and aligned blink swaps.
            blink = QPixmap(str(Path(__file__).resolve().parent / "assets" / "superdpet_standing_blink_1024.png"))
            wave = QPixmap(str(Path(__file__).resolve().parent / "assets" / "superdpet_standing_wave_1024.png"))
            self.pet.set_frames(sprite, blink, wave)
            print('[SuperDpet] Using standing open/blink/wave sprites from assets/.', flush=True)
            self.pet.setStyleSheet("background: transparent;")
            self.reminder_glow = QGraphicsDropShadowEffect(self.pet)
            self.reminder_glow.setOffset(0, 0)
            self.reminder_glow.setBlurRadius(20)
            self.reminder_glow.setColor(QColor("#FFB347"))
            self.pet.setGraphicsEffect(self.reminder_glow)
            self.reminder_glow.setEnabled(False)
        else:
            print('[SuperDpet ERROR] Cannot load assets/superdpet_standing_1024.png; using blue square fallback.', flush=True)
            self.pet.setGeometry(50, 80, 100, 100)
            fallback = QPixmap(100, 100)
            fallback.fill(QColor('#6C8CFF'))
            self.pet.set_frames(fallback, QPixmap())
        self.pet.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.pose = 'standing'
        self.pose_frames = {'standing': (self.pet.open_frame, self.pet.blink_frame,
                                         self.pet.wave_frame)}
        sitting = QPixmap(str(Path(__file__).resolve().parent / 'assets' / 'superdpet_sitting_1024.png'))
        sitting_blink = QPixmap(str(Path(__file__).resolve().parent / 'assets' / 'superdpet_sitting_blink_1024.png'))
        sitting_wave = QPixmap(str(Path(__file__).resolve().parent / 'assets' / 'superdpet_sitting_wave_1024.png'))
        if (self.has_sprite and not sitting.isNull() and not sitting_blink.isNull()
                and sitting.size() == sprite.size() == sitting_blink.size()):
            # Every transient frame belongs to the selected pose.
            self.pose_frames['sitting'] = (sitting, sitting_blink, sitting_wave)
        else:
            print('[SuperDpet ERROR] Sitting open/blink assets missing, invalid, or mismatched; using standing.', flush=True)
        if self.preferences.pose == 'sitting' and 'sitting' in self.pose_frames:
            self.pose = 'sitting'
            self.pet.set_frames(*self.pose_frames[self.pose])

        self.bubble = QLabel(self)
        self.bubble.setGeometry(8, 2, self.width() - 16, 52)
        self.bubble.setWordWrap(True)
        self.bubble.setMargin(4)
        self.bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubble.setStyleSheet(
            "background-color: white; color: #222222;"
            "border: 2px solid #6C8CFF; border-radius: 12px;"
        )
        self.bubble.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.bubble.hide()

        # All controls are hidden together when the interaction times out.
        self.note_actions = QWidget(self)
        self.note_actions.setGeometry((self.width() - 190) // 2, self.height() - 40, 190, 32)
        self.add_button = QPushButton("Add Note", self.note_actions)
        self.add_button.setGeometry(0, 0, 90, 30)
        self.add_button.clicked.connect(self.add_note)
        self.view_button = QPushButton("View Notes", self.note_actions)
        self.view_button.setGeometry(95, 0, 95, 30)
        self.view_button.clicked.connect(self.view_notes)
        self.note_actions.hide()

        # Mouse activity restarts the inactivity countdown.
        self.bubble_timer = QTimer(self)
        self.bubble_timer.setSingleShot(True)
        self.bubble_timer.setInterval(4000)
        self.bubble_timer.timeout.connect(self.hide_interaction)

        self.settings_menu = QMenu(self)
        self.pose_action = self.settings_menu.addAction(
            'Stand up' if self.pose == 'sitting' else 'Sit down', self.toggle_pose)
        self.pose_action.setEnabled('sitting' in self.pose_frames)
        self.settings_menu.addAction("Settings", self.show_settings)
        self.settings_menu.addAction("View notes", self.view_notes)
        self.settings_menu.addAction(
            "Developer test: create reminder in 5 seconds", self.create_test_reminder
        )
        self.settings_menu.addSeparator()
        self.settings_menu.addAction("Quit", self.close)
        self.settings_menu.aboutToShow.connect(self.bubble_timer.stop)
        self.settings_menu.aboutToHide.connect(self.restart_idle_timer)

        for control in (self.note_actions, self.add_button, self.view_button):
            control.setMouseTracking(True)
            control.installEventFilter(self)

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
        screen = self.screen()
        if screen is not None:
            self.move(screen.availableGeometry().center() - self.rect().center())
        self.idle = IdleController(self)
        self.mood = TaskMood()
        self.mood_timer = QTimer(self)
        self.mood_timer.setInterval(MOOD_REFRESH_MS)
        self.mood_timer.timeout.connect(self.refresh_mood)
        self.store.changed.connect(self.refresh_mood)
        self.refresh_mood()
        self.mood_timer.start()

    def toggle_pose(self):
        if self.quitting:
            return
        target = 'sitting' if self.pose == 'standing' else 'standing'
        if target not in self.pose_frames:
            print(f'[SuperDpet ERROR] Cannot switch to {target}; assets unavailable.', flush=True)
            return
        try:
            self.preferences.save_pose(target)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Pose not saved', str(error))
            return
        self.idle.pause()
        self.pet.stop_action()
        self.pose = target
        self.pet.set_frames(*self.pose_frames[target])
        self.pose_action.setText('Stand up' if target == 'sitting' else 'Sit down')
        self.pet.play_action('alert' if self.reminder_active else 'pose')
        self.apply_task_glow()
        self.idle.refresh()

    def refresh_mood(self, completed_task=False):
        if self.quitting:
            return
        self.mood.refresh(self.store.notes, completed_task=completed_task)
        description = self.mood.description()
        if self.store.load_error:
            description = "Task mood unavailable: notes could not be loaded"
        self.setToolTip(description)
        self.tray.setToolTip(f"SuperDpet — {description}")
        self.apply_task_glow()

    def apply_task_glow(self):
        color = QColor("#FFB347" if self.reminder_active else MOOD_COLORS[self.mood.state])
        if self.has_sprite:
            color.setAlpha(230 if self.reminder_active else 145)
            self.reminder_glow.setColor(color)
            self.reminder_glow.setBlurRadius(20 if self.reminder_active else 14)
            self.reminder_glow.setEnabled(True)
        elif self.pet.open_frame.toImage().pixelColor(0, 0) != color:
            self.pet.open_frame.fill(color)
            self.pet.show_frame(self.pet.frame_name)

    def task_completed(self):
        self.refresh_mood(completed_task=True)
        self.idle.completed()

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
        self.set_reminder_appearance(True)
        self.reminder_dialog.show()
        self.reminder_dialog.raise_()

    def finish_reminder(self, result):
        self.reminder_text.clear()
        self.set_reminder_appearance(False)

    def set_reminder_appearance(self, active):
        self.reminder_active = active
        self.apply_task_glow()
        if active:
            self.hide_interaction()
            self.idle.pause()
            self.pet.play_action('alert')
        else:
            self.pet.stop_action()
        QTimer.singleShot(0, self.idle.refresh)

    def create_test_reminder(self):
        minutes = self.preferences.default_reminder_minutes
        try:
            self.store.add(
                "[DEVELOPER TEST] Your reminder is working!",
                datetime.now(timezone.utc) + timedelta(minutes=minutes, seconds=5),
                minutes,
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
            "Reminders still work. Right-click the pet and choose Quit to exit completely.",
            QMessageBox.StandardButton.Ok, self,
        )
        # Re-evaluate after Qt finishes hiding the notice; do not retain its
        # paused state or override any other dialog that is still open.
        self.tray_notice.finished.connect(lambda _result: QTimer.singleShot(0, self.idle.refresh))
        # Informational only: keep the pet usable and blinking behind it.
        self.tray_notice.setWindowModality(Qt.WindowModality.NonModal)
        self.tray_notice.show()

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
        self.mood_timer.stop()
        self.bubble_timer.stop()
        self.idle.stop()
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
        AddNoteDialog(self.store, self,
                      default_reminder_minutes=self.preferences.default_reminder_minutes).exec()

    def view_notes(self):
        self.hide_interaction()
        dialog = NotesDialog(self.store, self)
        dialog.note_completed.connect(self.task_completed)
        dialog.exec()
        self.idle.refresh()

    def show_interaction(self):
        self.bubble.show()
        self.note_actions.show()
        self.restart_idle_timer()

    def hide_interaction(self):
        self.bubble_timer.stop()
        self.bubble.hide()
        self.note_actions.hide()

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
            self.end_drag()
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
                self.drag_activity.restart()
                self.hide_interaction()
                self.idle.pause()
                self.pet.stop_action()
                # X11/WSL, Windows and macOS support direct movement, retaining
                # mouse release delivery. Only Wayland requires compositor move.
                handle = self.windowHandle()
                self.system_drag = bool(QApplication.platformName().startswith('wayland')
                                        and handle and handle.startSystemMove())
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
                self.hide_interaction()
                message = random.choice(GREETINGS)
                if self.idle.start_wave():
                    self.bubble.setText(message)
                    self.show_interaction()
            self.idle.refresh()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def end_drag(self):
        self.press_position = None
        self.dragging = False
        self.system_drag = False

    def recover_finished_drag(self):
        # Native moves can consume the release event. Never let their bookkeeping
        # permanently block idle. Wayland gets a settling grace after last move.
        if self.dragging and not QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            if not self.system_drag or self.drag_activity.elapsed() >= 600:
                print('[pet] Drag release recovered; returning to idle', flush=True)
                self.end_drag()

    def moveEvent(self, event):
        if self.system_drag:
            self.drag_activity.restart()
        super().moveEvent(event)


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
    window.idle.start()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
