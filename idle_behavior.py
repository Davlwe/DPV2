"""Non-blocking desktop-pet visuals and conservative autonomous movement."""

import random
from dataclasses import dataclass

from PySide6.QtCore import (
    QAbstractAnimation, QEasingCurve, QEvent, QObject, QPoint, QPointF,
    Property, QPropertyAnimation, QRectF, Qt, QTimer, QVariantAnimation,
)
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMenu


@dataclass(frozen=True)
class IdleSettings:
    bob_ms: int = 3200
    reminder_bob_ms: int = 1200
    bob_pixels: int = 8
    breath_ms: int = 4200
    breath_scale: float = 1.015
    pulse_gap_ms: tuple = (8000, 16000)
    pulse_ms: int = 2200
    wander_gap_ms: tuple = (15000, 30000)
    wander_ms: int = 6000
    wander_chance: float = 0.7
    wander_radius: int = 100
    guard_ms: int = 200


IDLE = IdleSettings()


class PetSprite(QLabel):
    """Paint the original pixmap smoothly; animation never rewrites the asset."""

    def __init__(self, parent):
        super().__init__(parent)
        self._breath = 1.0
        self._halo = 0.0

    def get_breath(self):
        return self._breath

    def set_breath(self, value):
        self._breath = value
        self.update()

    breath = Property(float, get_breath, set_breath)

    def get_halo(self):
        return self._halo

    def set_halo(self, value):
        self._halo = value
        self.update()

    halo = Property(float, get_halo, set_halo)

    def paintEvent(self, event):
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Breathe around the feet; transparent asset padding accommodates growth.
        anchor = QPointF(self.width() / 2, self.height() * 0.94)
        painter.translate(anchor)
        painter.scale(self._breath, self._breath)
        painter.translate(-anchor)
        painter.drawPixmap(self.rect(), pixmap)
        if self._halo:
            # Soft turquoise light over the existing halo, without a new image.
            painter.translate(self.width() * 0.50, self.height() * 0.115)
            painter.rotate(-12)
            painter.scale(1, 0.35)
            radius = self.width() * 0.16
            gradient = QRadialGradient(QPointF(0, 0), radius)
            gradient.setColorAt(0, QColor(175, 255, 245, 0))
            gradient.setColorAt(0.60, QColor(140, 255, 238, round(100 * self._halo)))
            gradient.setColorAt(1, QColor(140, 255, 238, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawEllipse(QRectF(-radius, -radius, 2 * radius, 2 * radius))


class IdleController(QObject):
    """WAITING -> WANDERING; any interaction -> PAUSED; Quit -> STOPPED.

    Resuming always starts a fresh wait, never a stale movement destination.
    Decorative animation continues during dialogs, including reminder bobbing.
    """

    def __init__(self, window, settings=IDLE):
        super().__init__(window)
        self.window = window
        self.settings = settings
        self.state = "paused"
        self.stopped = False
        self.wander_screen = None
        self.bob = QPropertyAnimation(window.pet, b"pos", self)
        origin = window.pet.pos()
        self.configure_loop(self.bob, settings.bob_ms, origin,
                            origin - QPoint(0, settings.bob_pixels))
        self.breath = QPropertyAnimation(window.pet, b"breath", self)
        self.configure_loop(self.breath, settings.breath_ms, 1.0, settings.breath_scale)
        self.pulse = QPropertyAnimation(window.pet, b"halo", self)
        self.pulse.setDuration(settings.pulse_ms)
        self.pulse.setStartValue(0.0)
        self.pulse.setKeyValueAt(0.5, 1.0)
        self.pulse.setEndValue(0.0)
        self.pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.pulse.finished.connect(self.schedule_pulse)
        self.pulse_timer = QTimer(self)
        self.pulse_timer.setSingleShot(True)
        self.pulse_timer.timeout.connect(self.start_pulse)
        self.wander_timer = QTimer(self)
        self.wander_timer.setSingleShot(True)
        self.wander_timer.timeout.connect(self.try_wander)
        # Animate values instead of window.pos so each frame can recheck bounds
        # and interaction before applying a focus-neutral QWidget.move().
        self.travel = QVariantAnimation(self)
        self.travel.setDuration(settings.wander_ms)
        self.travel.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.travel.valueChanged.connect(self.move_step)
        self.travel.finished.connect(self.finish_wander)
        self.guard = QTimer(self)
        self.guard.setInterval(settings.guard_ms)
        self.guard.timeout.connect(self.refresh)
        QApplication.instance().installEventFilter(self)
        self.guard.start()

    @staticmethod
    def configure_loop(animation, duration, start, peak):
        animation.setDuration(duration)
        animation.setStartValue(start)
        animation.setKeyValueAt(0.5, peak)
        animation.setEndValue(start)
        animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        animation.setLoopCount(-1)

    def blocked(self):
        w = self.window
        return (self.stopped or w.quitting or not w.isVisible() or w.isMinimized()
                or w.press_position is not None or w.dragging or w.system_drag
                or bool(QApplication.mouseButtons())
                or any(control.isVisible() for control in
                       (w.bubble, w.note_actions, w.quit_button))
                or any(widget.isVisible() for widget in QApplication.topLevelWidgets()
                       if isinstance(widget, (QDialog, QMenu))))

    def pause(self):
        if self.stopped:
            return
        self.travel.stop()
        self.wander_timer.stop()
        self.pulse_timer.stop()
        self.pulse.stop()
        self.window.pet.halo = 0.0
        self.state = "paused"

    def refresh(self):
        if self.stopped:
            return
        visible = self.window.isVisible() and not self.window.isMinimized()
        for animation in (self.bob, self.breath):
            if visible:
                if animation.state() == QAbstractAnimation.State.Paused:
                    animation.resume()
                elif animation.state() == QAbstractAnimation.State.Stopped:
                    animation.start()
            elif animation.state() == QAbstractAnimation.State.Running:
                animation.pause()
        if self.blocked():
            self.pause()
        elif self.state == "paused":
            self.state = "waiting"
            self.schedule_wander()
            self.schedule_pulse()

    def schedule_wander(self):
        if not self.blocked():
            self.wander_timer.start(random.randint(*self.settings.wander_gap_ms))

    def schedule_pulse(self):
        if self.window.has_sprite and not self.blocked():
            self.pulse_timer.start(random.randint(*self.settings.pulse_gap_ms))

    def start_pulse(self):
        if self.blocked():
            self.pause()
        else:
            self.pulse.start()

    @staticmethod
    def bounded_position(position, area, size):
        # A full window cannot fit on a screen smaller than the window itself.
        if area.width() < size.width() or area.height() < size.height():
            return None
        return QPoint(max(area.left(), min(position.x(), area.right() - size.width() + 1)),
                      max(area.top(), min(position.y(), area.bottom() - size.height() + 1)))

    def try_wander(self):
        if self.blocked():
            self.pause()
            return
        # Native Wayland leaves top-level placement to the compositor. Keep all
        # local animation but do not request unsupported programmatic roaming.
        if (QApplication.platformName().startswith("wayland")
                or random.random() >= self.settings.wander_chance):
            self.schedule_wander()
            return
        w = self.window
        screen = w.screen()
        if screen is None:
            self.schedule_wander()
            return
        area = screen.availableGeometry()
        start = self.bounded_position(w.pos(), area, w.size())
        if start is None:
            self.schedule_wander()
            return
        radius = self.settings.wander_radius
        target = self.bounded_position(start + QPoint(random.randint(-radius, radius),
                                                     random.randint(-radius, radius)), area, w.size())
        self.wander_screen = screen
        self.travel.setStartValue(start)
        self.travel.setEndValue(target)
        self.state = "wandering"
        w.move(start)
        self.travel.start()

    def move_step(self, position):
        if self.state != "wandering":
            return
        if self.blocked() or self.wander_screen not in QApplication.screens():
            self.pause()
            return
        safe = self.bounded_position(position, self.wander_screen.availableGeometry(), self.window.size())
        if safe is None:
            self.pause()
        else:
            self.window.move(safe)

    def finish_wander(self):
        if not self.stopped:
            self.state = "waiting"
            self.schedule_wander()

    def eventFilter(self, watched, event):
        kind = event.type()
        relevant = (watched is self.window or isinstance(watched, (QDialog, QMenu))
                    or watched in (self.window.bubble, self.window.note_actions, self.window.quit_button))
        if kind == QEvent.Type.MouseButtonPress:
            # Runs before PetWindow records its drag origin.
            self.pause()
        if (relevant and kind in (QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange)):
            self.pause()
            QTimer.singleShot(0, self.refresh)
        elif kind == QEvent.Type.MouseButtonRelease:
            QTimer.singleShot(0, self.refresh)
        return False

    def stop(self):
        self.pause()
        self.stopped = True
        self.state = "stopped"
        for timer in (self.guard, self.wander_timer, self.pulse_timer):
            timer.stop()
        for animation in (self.bob, self.breath, self.pulse, self.travel):
            animation.stop()
        QApplication.instance().removeEventFilter(self)
