"""Application-local inactivity and centralized high-level pet transitions.

IdleController retains blink/wave presentation substates. This controller owns
the sleep deadline and arbitrates their priority against sleep and reminders.
"""

from enum import Enum, auto

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QWidget


class PetState(Enum):
    IDLE = auto()
    WAVING = auto()
    SITTING = auto()
    SLEEPING = auto()
    REMINDER = auto()


class SleepController(QObject):
    INACTIVITY_MS = 30_000

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.state = self.resting_state()
        self.started = False
        self.stopped = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(self.INACTIVITY_MS)
        self.timer.timeout.connect(self.enter_sleep)
        QApplication.instance().installEventFilter(self)

    def resting_state(self):
        return PetState.SITTING if self.window.pose == 'sitting' else PetState.IDLE

    @property
    def sleeping(self):
        return self.state == PetState.SLEEPING

    def blocked(self):
        w = self.window
        return (self.stopped or w.quitting or w.dev_mode or not w.isVisible()
                or w.isMinimized() or w.reminder_active
                or (not self.sleeping and (w.dragging or w.system_drag
                                          or w.press_position is not None))
                or any(isinstance(widget, (QMenu, QDialog)) and widget.isVisible()
                       for widget in QApplication.topLevelWidgets()))

    def transition(self, target):
        """Only writer of high-level state; sleep always cancels normal motion."""
        if target == self.state:
            return
        w = self.window
        was_sleeping = self.sleeping
        if target == PetState.SLEEPING:
            w.idle.pause()
            w.hide_interaction()
            self.timer.stop()
            w.pet.stop_action()
        self.state = target
        if was_sleeping:
            w.pet.stop_action()
            w.pet.show_frame('open')  # pose is never changed by sleep
        if target == PetState.SLEEPING:
            w.pet.show_frame('sleep')
            w.pet.play_action('sleep')
        elif was_sleeping:
            self.refresh()
            w.idle.refresh()

    def start(self):
        if not self.stopped and self.window.isVisible():
            self.started = True
            self.refresh()

    def activity(self):
        if self.stopped:
            return
        if self.sleeping:
            self.transition(self.resting_state())
        self.timer.stop()
        self.refresh()

    def refresh(self):
        if not self.started or self.stopped:
            return
        if self.blocked():
            if self.sleeping:
                self.transition(self.resting_state())
            self.timer.stop()
        elif not self.sleeping and not self.timer.isActive():
            self.timer.start()

    def enter_sleep(self):
        if self.started and not self.blocked():
            self.transition(PetState.SLEEPING)
        else:
            self.refresh()

    def reminder_changed(self):
        self.transition(PetState.REMINDER if self.window.reminder_active
                        else self.resting_state())
        self.activity()

    def eventFilter(self, watched, event):
        # Qt events only: no OS hooks, cursor polling or global movement tracking.
        if self.stopped or not isinstance(watched, QWidget):
            return False
        kind = event.type()
        # Defer left-button wake to the pet's confirmed short-click handler.
        # Dragging, including native compositor moves, keeps sleep animating.
        if self.sleeping and watched in (self.window, self.window.pet):
            if (kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                         QEvent.Type.MouseButtonDblClick)
                    and event.button() == Qt.MouseButton.LeftButton):
                return False
            if kind == QEvent.Type.MouseMove and event.buttons() & Qt.MouseButton.LeftButton:
                return False
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                    QEvent.Type.MouseButtonDblClick, QEvent.Type.KeyPress,
                    QEvent.Type.Wheel) or (kind == QEvent.Type.MouseMove and event.buttons()):
            self.activity()
        if isinstance(watched, (QMenu, QDialog)) and kind in (QEvent.Type.Show, QEvent.Type.Hide):
            self.activity()
            QTimer.singleShot(0, self.refresh)
        elif watched is self.window and kind in (
                QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange):
            # Native dragging can change window state. Only actual hiding or
            # minimizing should end sleep, not compositor state notifications.
            if kind != QEvent.Type.WindowStateChange:
                self.activity()
            QTimer.singleShot(0, self.start if kind == QEvent.Type.Show else self.refresh)
        return False

    def stop(self):
        self.stopped = True
        self.timer.stop()
        self.window.pet.stop_action()
        QApplication.instance().removeEventFilter(self)
