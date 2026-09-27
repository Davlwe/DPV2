"""Standing idle: a still image with brief, randomized, interruptible blinks."""

import random
import math
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QEvent, QObject, QRectF, QTimer, Qt, Property, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMenu


@dataclass(frozen=True)
class IdleSettings:
    blink_gap_ms: tuple = (2000, 5000)
    blink_duration_ms: tuple = (120, 180)
    guard_ms: int = 200
    wave_ms: int = 950
    presentation_timeout_ms: int = 1200
    happy_ms: int = 900
    alert_ms: int = 1200


IDLE = IdleSettings()
BLINK_DIAGNOSTICS = True  # Temporary: set False to silence terminal diagnostics.


def blink_log(message):
    if BLINK_DIAGNOSTICS:
        print(f"[blink {datetime.now():%H:%M:%S.%f}] {message}", flush=True)


class PetSprite(QLabel):
    """Both frames share a canvas and a fixed, mouse-transparent image layer."""

    frame_painted = Signal(str, int)

    def __init__(self, parent):
        super().__init__(parent)
        self.open_frame = None
        self.blink_frame = None
        self.wave_frame = None
        self.frame_name = "open"
        self.frame_revision = 0
        self._painted_revision = -1
        self.blinking = False
        self.action_kind = None
        self._action_phase = 0.0
        self.action_animation = QPropertyAnimation(self, b'action_phase', self)
        self.action_animation.setStartValue(0.0)
        self.action_animation.setEndValue(1.0)
        self.action_animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.action_animation.finished.connect(self.stop_action)

    def get_action_phase(self):
        return self._action_phase

    def set_action_phase(self, value):
        self._action_phase = value
        self.update()

    action_phase = Property(float, get_action_phase, set_action_phase)

    def play_action(self, kind):
        self.stop_action()
        self.action_kind = kind
        self.action_animation.setDuration({'wave': IDLE.wave_ms, 'happy': IDLE.happy_ms,
                                           'alert': IDLE.alert_ms}[kind])
        self.action_animation.setLoopCount(-1 if kind == 'alert' else 1)
        self.action_animation.start()
        blink_log(f'ACTION {kind}')

    def stop_action(self):
        self.action_animation.stop()
        self.action_kind = None
        self._action_phase = 0.0
        self.update()

    def set_frames(self, open_frame, blink_frame, wave_frame=None):
        self.open_frame = open_frame
        self.blink_frame = (blink_frame if not blink_frame.isNull()
                            and blink_frame.size() == open_frame.size() else None)
        self.wave_frame = (wave_frame if wave_frame is not None and not wave_frame.isNull()
                           and wave_frame.size() == open_frame.size() else None)
        if self.wave_frame is None:
            print('[SuperDpet ERROR] Wave asset missing/invalid; using standing-frame greeting motion.', flush=True)
        self.show_frame('open')
        if self.blink_frame is None:
            print('[SuperDpet ERROR] Blink image missing/invalid or mismatched canvas; using open-eye sprite.', flush=True)
        blink_log(f"ASSETS open={open_frame.width()}x{open_frame.height()} "
                  f"blink_loaded={self.blink_frame is not None}")
        blink_log("SPRITE open-eye applied (initial)")

    def show_frame(self, name):
        frames = {'open': self.open_frame, 'blink': self.blink_frame, 'wave': self.wave_frame}
        frame = frames[name]
        if frame is None:
            frame = self.blink_frame if name == 'wave' and self.blink_frame is not None else self.open_frame
        self.frame_name = name
        self.blinking = name == 'blink' and self.blink_frame is not None
        self.frame_revision += 1
        if frame is not None:
            self.setPixmap(frame)  # The actual visible QLabel, not a separate buffer.
            self.update()
            effect = self.graphicsEffect()
            if effect is not None and effect.isEnabled():
                effect.update()
        blink_log(f'SPRITE {name} applied revision={self.frame_revision}')

    def set_blinking(self, closed):
        self.show_frame('blink' if closed else 'open')

    def paintEvent(self, event):
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(256, self.width(), self.height())
        image_rect = QRectF((self.width() - side) / 2, (self.height() - side) / 2, side, side)
        pulse = math.sin(math.pi * self._action_phase) ** 2
        if self.action_kind == 'wave':
            # Brief greeting motion only; standing idle stays completely still.
            painter.translate(image_rect.center().x(), image_rect.bottom())
            painter.rotate(0.8 * math.sin(4 * math.pi * self._action_phase) * pulse)
            painter.translate(-image_rect.center().x(), -image_rect.bottom())
        elif self.action_kind:
            painter.translate(0, -pulse * (5 if self.action_kind == 'alert' else 10))
        painter.drawPixmap(image_rect, pixmap, QRectF(pixmap.rect()))
        if self.action_kind in ('happy', 'alert'):
            color = QColor('#FFB347' if self.action_kind == 'alert' else '#51DCCA')
            color.setAlpha(round(220 * pulse))
            painter.setPen(QPen(color, 2))
            if self.action_kind == 'alert':
                painter.drawEllipse(QRectF(image_rect.center().x() - 28, image_rect.top() + 20, 56, 13))
            else:
                for x, y in ((55, 95), (225, 125), (70, 205), (210, 220)):
                    painter.drawLine(x-5, y, x+5, y)
                    painter.drawLine(x, y-5, x, y+5)
        painter.end()
        if self._painted_revision != self.frame_revision:
            self._painted_revision = self.frame_revision
            blink_log(f'PAINT {self.frame_name} revision={self.frame_revision}')
            self.frame_painted.emit(self.frame_name, self.frame_revision)


class IdleController(QObject):
    """Single owner for idle, blink and wave transitions; no autonomous roaming."""

    def __init__(self, window, settings=IDLE):
        super().__init__(window)
        self.window = window
        self.settings = settings
        self.state = 'paused'
        self.started = False
        self.stopped = False
        self.last_pause_reasons = set()
        self.happy_pending = False
        self.pending_duration = 0
        self.blink_timer = self.timer(self.start_blink)
        self.reopen_timer = self.timer(self.finish_blink)
        self.wave_timer = self.timer(self.finish_wave)
        self.presentation_timer = self.timer(self.presentation_expired)
        self.guard = QTimer(self)
        self.guard.setInterval(settings.guard_ms)
        self.guard.timeout.connect(self.refresh)
        window.pet.frame_painted.connect(self.frame_presented, Qt.ConnectionType.QueuedConnection)
        QApplication.instance().installEventFilter(self)
        blink_log('CONTROLLER ready; waiting for window show')

    def timer(self, callback):
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setTimerType(Qt.TimerType.PreciseTimer)
        timer.timeout.connect(callback)
        return timer

    def start(self):
        if self.stopped or not self.window.isVisible():
            return
        if not self.started:
            self.started = True
            self.guard.start()
            blink_log('START shown window: idle watchdog active')
        self.refresh()

    def external_reasons(self):
        w = self.window
        reasons = set()
        for active, reason in (
            (self.stopped or w.quitting, 'quitting'),
            (not w.isVisible() or w.isMinimized(), 'pet hidden'),
            (w.dragging or w.system_drag, 'dragging'),
            (w.reminder_active or w.reminder_dialog.isVisible(), 'reminder active'),
        ):
            if active:
                reasons.add(reason)
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible() and widget.isModal():
                reasons.add('modal dialog: ' + (widget.windowTitle() or type(widget).__name__))
        return reasons

    def blocked(self):
        reasons = self.external_reasons()
        if self.state == 'waving':
            reasons.add('wave playing')
        for reason in sorted(reasons - self.last_pause_reasons):
            blink_log(f'PAUSE + {reason}')
        for reason in sorted(self.last_pause_reasons - reasons):
            blink_log(f'CLEAR - {reason}')
        self.last_pause_reasons = reasons
        return bool(reasons)

    def cancel_transient(self):
        for timer in (self.blink_timer, self.reopen_timer, self.wave_timer, self.presentation_timer):
            timer.stop()
        if self.window.pet.action_kind == 'wave':
            self.window.pet.stop_action()
        if self.window.pet.frame_name != 'open':
            self.window.pet.show_frame('open')

    def pause(self):
        if self.stopped:
            return
        self.cancel_transient()
        self.state = 'paused'

    def schedule_blink(self):
        if not self.started or self.stopped:
            return
        self.state = 'waiting'
        if self.window.pet.blink_frame is not None:
            delay = random.randint(*self.settings.blink_gap_ms)
            self.blink_timer.start(delay)
            blink_log(f'TIMER start delay={delay}ms active=True state=waiting')

    def refresh(self):
        if not self.started or self.stopped:
            return
        w = self.window
        w.recover_finished_drag()
        self.blocked()  # Report changed conditions, never accumulate stale flags.
        if self.external_reasons():
            self.pause()
            if w.dragging or w.system_drag or not w.isVisible():
                w.pet.stop_action()
            elif w.reminder_active and w.pet.action_kind != 'alert':
                w.pet.play_action('alert')
            return
        if self.state == 'waving':
            return
        if self.happy_pending:
            self.happy_pending = False
            w.pet.play_action('happy')
        if self.state == 'paused' or (self.state == 'waiting' and not self.blink_timer.isActive()
                                     and w.pet.blink_frame is not None):
            self.schedule_blink()
        elif self.state == 'blinking' and not (self.reopen_timer.isActive() or self.presentation_timer.isActive()):
            self.finish_blink()

    def start_blink(self):
        blink_log('TIMER fired: blink')
        if self.stopped or not self.started:
            return
        # A stale callback must never overwrite the waving frame.
        if self.state == 'waving':
            return
        if self.external_reasons():
            self.refresh()
            return
        if self.window.pet.blink_frame is None:
            return
        self.blink_timer.stop()
        self.pending_duration = random.randint(*self.settings.blink_duration_ms)
        self.state = 'blinking'
        self.presentation_timer.start(self.settings.presentation_timeout_ms)
        self.window.pet.show_frame('blink')

    def frame_presented(self, name, revision):
        if self.stopped or revision != self.window.pet.frame_revision:
            return
        if name == 'blink' and self.state == 'blinking' and not self.reopen_timer.isActive():
            self.presentation_timer.stop()
            self.reopen_timer.start(self.pending_duration)
            blink_log(f'BLINK visible; restore in {self.pending_duration}ms')
        elif name == 'wave' and self.state == 'waving' and not self.wave_timer.isActive():
            self.presentation_timer.stop()
            self.wave_timer.start(self.settings.wave_ms)
            blink_log(f'WAVE visible; restore in {self.settings.wave_ms}ms')

    def start_wave(self):
        if self.stopped or not self.started or self.external_reasons():
            return False
        self.cancel_transient()
        self.state = 'waving'
        self.presentation_timer.start(self.settings.presentation_timeout_ms)
        self.window.pet.show_frame('wave')
        self.window.pet.play_action('wave')
        self.blocked()
        return True

    def finish_wave(self):
        if self.stopped or self.state != 'waving':
            return
        blink_log('WAVE complete -> standing idle')
        self.pause()
        self.refresh()

    def finish_blink(self):
        if self.stopped or self.state == 'waving':
            return
        blink_log('BLINK complete -> standing idle')
        self.pause()
        self.refresh()

    def presentation_expired(self):
        # A hidden/occluded compositor surface might not paint. Never get stuck.
        blink_log('Frame presentation timeout; restoring idle and retrying later')
        self.pause()
        self.refresh()

    def completed(self):
        self.happy_pending = True
        self.refresh()

    def eventFilter(self, watched, event):
        kind = event.type()
        if watched is self.window and kind == QEvent.Type.Show:
            QTimer.singleShot(0, self.start)
        elif (watched is self.window or isinstance(watched, QDialog)) and kind in (
                QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange):
            QTimer.singleShot(0, self.refresh)
        elif kind == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self.window.system_drag:
                self.window.end_drag()
            QTimer.singleShot(0, self.refresh)
        return False

    def stop(self):
        if self.stopped:
            return
        self.pause()
        self.stopped = True
        self.state = 'stopped'
        self.guard.stop()
        self.window.pet.stop_action()
        QApplication.instance().removeEventFilter(self)
        blink_log('STOP all blink, wave and action timers stopped')
