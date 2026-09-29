"""Render real application widgets with isolated sample data for submission.

Run: QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 .venv/bin/python scripts/capture_submission.py
These are widget captures, not full-desktop screenshots or native-platform checks.
"""
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
import main
from storage import NoteStore
from preferences import Preferences
from notes_dialog import AddNoteDialog, NotesDialog

app = QApplication([])
app.setApplicationName('SuperDpet submission capture')
output = Path(__file__).resolve().parents[1] / 'submission' / 'screenshots'
output.mkdir(parents=True, exist_ok=True)

def capture(widget, name):
    widget.show()
    app.processEvents()
    QTest.qWait(80)
    if not widget.grab().save(str(output / name)):
        raise RuntimeError(f'Could not save {name}')

with tempfile.TemporaryDirectory(prefix='superdpet-submission-') as directory:
    store = NoteStore(Path(directory) / 'notes.json')
    prefs = Preferences(Path(directory) / 'preferences.json')
    prefs.startup_permission = False
    now = datetime.now(timezone.utc)
    store.add('Sketch ideas for the next project', now + timedelta(hours=2), 5)
    store.add('Take a break and stretch', now + timedelta(hours=1), 1)
    store.add('Review today’s progress', now + timedelta(hours=3), 10)
    store.set_completed(store.notes[2]['id'], True)
    with patch.object(main, 'NoteStore', return_value=store), patch.object(
        main.PetWindow, 'setup_tray', lambda w: setattr(w, 'tray', Mock())
    ):
        pet = main.PetWindow(prefs)
    pet.show()
    pet.idle.start()
    pet.bubble.setText('Wanna add a note or reminder?')
    pet.show_interaction()
    pet.idle.start_wave()
    capture(pet, '01-pet.png')
    add = AddNoteDialog(store, pet)
    add.text_input.setPlainText('Write down the idea before I forget it')
    capture(add, '02-add-note.png')
    add.close()
    notes = NotesDialog(store, pet)
    capture(notes, '03-view-notes.png')
    notes.close()
    pet.close()
print(f'Saved three real widget captures to {output}')
