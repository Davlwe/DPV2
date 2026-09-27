"""Visible desktop check; intentionally refuses the offscreen/minimal backends.

Run from the checkout: .venv/bin/python tests/native_interaction_check.py
Uses temporary note/preferences files and captures only the pet widget.
"""

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QElapsedTimer, QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

import main
from notes_dialog import NotesDialog
from preferences import Preferences
from storage import NoteStore


app = QApplication([])
app.setApplicationName('SuperDpet native interaction check')
if app.platformName() in ('offscreen', 'minimal'):
    raise SystemExit('This check requires the real desktop backend.')
temporary = tempfile.TemporaryDirectory(prefix='superdpet-native-')
store = NoteStore(Path(temporary.name) / 'notes.json')
main.NoteStore = lambda: store
preferences = Preferences(Path(temporary.name) / 'preferences.json')
preferences.startup_permission = False
window = main.PetWindow(preferences)
output = Path(main.__file__).parent / 'assets' / 'diagnostics'
save_captures = '--no-captures' not in sys.argv
if save_captures:
    output.mkdir(exist_ok=True)
clock = QElapsedTimer()
state = {'stage': 'initial', 'passed': False, 'error': None}
captures = {}


def fail(error):
    state['error'] = str(error)
    print('FAIL:', error, flush=True)
    window.close()


def click():
    try:
        state['stage'] = 'wave'
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(144, 190))
        assert window.idle.state == 'waving'
        assert window.note_actions.isVisible()
    except Exception as error:
        fail(error)


def check_remaining_features():
    try:
        window.hide_interaction()
        window.idle.finish_blink()
        modal = QDialog(window)
        modal.setModal(True)
        modal.show()
        app.processEvents()
        assert window.idle.state == 'paused'
        modal.close()
        app.processEvents()
        assert window.idle.blink_timer.isActive()

        # Exercise real note persistence/completion without touching user notes.
        store.add('Native check note', datetime.now(timezone.utc) + timedelta(hours=1))
        notes = NotesDialog(store, window)
        notes.note_completed.connect(window.idle.completed)
        notes.setModal(True)
        notes.show()
        notes.list_widget.setCurrentRow(0)
        notes.complete_selected()
        assert store.notes[0]['completed']
        notes.close()
        app.processEvents()
        assert window.pet.action_kind == 'happy'

        store.add('Native reminder check', datetime.now(timezone.utc) + timedelta(minutes=4))
        window.check_reminders()
        assert window.reminder_dialog.isVisible()
        assert store.notes[-1]['reminded']
        assert window.pet.action_kind == 'alert'
        window.idle.start_wave()
        assert window.idle.state != 'waving'
        window.reminder_dialog.reject()
        app.processEvents()
        assert window.idle.blink_timer.isActive()

        QTest.mouseClick(window, Qt.MouseButton.RightButton, pos=QPoint(144, 190))
        assert window.settings_menu.isVisible()
        window.settings_menu.hide()
        # Recover a compositor-consumed release without ever playing a wave.
        window.dragging = True
        window.system_drag = True
        window.press_position = QPoint(10, 10)
        window.idle.pause()
        QTest.qWait(750)
        window.idle.refresh()
        assert not window.dragging and not window.system_drag
        assert window.idle.blink_timer.isActive()
        state['passed'] = True
        print('PASS native desktop: painted blink, wave, resumed blink, modal recovery, '
              'notes, completion, reminder, right-click, drag recovery.', flush=True)
        window.close()
        assert window.idle.stopped
        assert not window.idle.wave_timer.isActive()
    except Exception as error:
        fail(error)


def frame(name, revision):
    try:
        if revision != window.pet.frame_revision:
            return
        stage = state['stage']
        if stage == 'initial' and name == 'blink':
            assert clock.elapsed() <= 5100, f'First visible blink delayed: {clock.elapsed()}ms'
            print(f'Native backend {app.platformName()}: first PAINT blink at {clock.elapsed()}ms', flush=True)
            captures['blink'] = window.pet.grab().toImage()
            if save_captures:
                captures['blink'].save(str(output / 'native_standing_blink.png'))
            assert captures['blink'] != captures['open']
            state['stage'] = 'initial_restore'
        elif stage == 'initial_restore' and name == 'open':
            QTimer.singleShot(100, click)
            state['stage'] = 'click_pending'
        elif stage == 'wave' and name == 'wave':
            image = window.pet.grab().toImage()
            assert image != captures['open'] and image != captures['blink']
            if save_captures:
                image.save(str(output / 'native_standing_wave.png'))
            assert window.idle.wave_timer.isActive()
            state['stage'] = 'wave_restore'
        elif stage == 'wave_restore' and name == 'open':
            assert window.idle.blink_timer.isActive()
            assert window.note_actions.isVisible()
            assert window.bubble.text() in main.GREETINGS
            state['stage'] = 'resume'
        elif stage == 'resume' and name == 'blink':
            print(f'PAINT blink resumed after wave at {clock.elapsed()}ms', flush=True)
            state['stage'] = 'other_checks'
            QTimer.singleShot(250, check_remaining_features)
    except Exception as error:
        fail(error)


window.pet.frame_painted.connect(frame, Qt.ConnectionType.QueuedConnection)
window.show()
window.idle.start()
clock.start()
app.processEvents()
captures['open'] = window.pet.grab().toImage()
if save_captures:
    captures['open'].save(str(output / 'native_standing_open.png'))
QTimer.singleShot(100, lambda: window.tray_notice.accept() if hasattr(window, 'tray_notice') else None)
QTimer.singleShot(16000, lambda: fail('Native check timed out') if not state['passed'] else None)
app.exec()
temporary.cleanup()
raise SystemExit(0 if state['passed'] and state['error'] is None else 1)
