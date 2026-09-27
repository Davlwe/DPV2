"""Local note persistence, independent of the pet interface."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QIODevice, QSaveFile, QStandardPaths, QObject, Signal
from reminders import DEFAULT_REMINDER_MINUTES, validate_reminder_minutes


class NoteStore(QObject):
    changed = Signal()

    def __init__(self, path=None):
        super().__init__()
        self.path = Path(path) if path is not None else Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        ) / "notes.json"
        self.notes = []
        self.load_error = None
        try:
            self.notes = self._load()
        except (OSError, ValueError, TypeError, KeyError) as error:
            # Never replace unreadable data with an empty list.
            self.load_error = str(error)

    def _load(self):
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        notes = json.loads(raw)
        if not isinstance(notes, list):
            raise ValueError("Expected a list of notes.")
        ids = set()
        for note in notes:
            if not isinstance(note, dict):
                raise ValueError("Invalid note record.")
            if not isinstance(note["id"], str) or not note["id"] or note["id"] in ids:
                raise ValueError("Invalid or duplicate note ID.")
            ids.add(note["id"])
            if not isinstance(note["text"], str) or not note["text"].strip():
                raise ValueError("Invalid note text.")
            if type(note["completed"]) is not bool:
                raise ValueError("Invalid completion state.")
            # Notes saved before reminders existed have not been reminded yet.
            note.setdefault("reminded", False)
            if type(note["reminded"]) is not bool:
                raise ValueError("Invalid reminder state.")
            note.setdefault("reminder_minutes", DEFAULT_REMINDER_MINUTES)
            validate_reminder_minutes(note["reminder_minutes"])
            due = datetime.fromisoformat(note["due_at"])
            if due.tzinfo is None:
                raise ValueError("Due time must include a time zone.")
        return notes

    def _save(self, notes):
        if self.load_error is not None:
            raise OSError("Notes could not be loaded. Existing data has been left untouched.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(notes, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        file = QSaveFile(str(self.path))
        if not file.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(file.errorString())
        if file.write(data) != len(data):
            error = file.errorString()
            file.cancelWriting()
            raise OSError(error)
        if not file.commit():
            raise OSError(file.errorString())
        # Only update the visible state after saving succeeds.
        self.notes = notes
        self.changed.emit()

    def add(self, text, due, reminder_minutes=DEFAULT_REMINDER_MINUTES):
        validate_reminder_minutes(reminder_minutes)
        text = text.strip()
        if not text:
            raise ValueError("Please enter some note text.")
        if due.tzinfo is None:
            raise ValueError("Please choose a valid due time.")
        note = {
            "id": str(uuid4()),
            "text": text,
            "due_at": due.astimezone(timezone.utc).isoformat(),
            "completed": False,
            "reminded": False,
            "reminder_minutes": reminder_minutes,
        }
        self._save(self.notes + [note])

    def complete(self, note_id):
        self._save([
            dict(note, completed=True) if note["id"] == note_id else note
            for note in self.notes
        ])

    def mark_reminded(self, note_ids):
        self._save([
            dict(note, reminded=True) if note["id"] in note_ids else note
            for note in self.notes
        ])

    def delete_completed(self, note_id):
        """Delete only the selected completed note, leaving pending notes intact."""
        self._save([
            note for note in self.notes
            if not (note["id"] == note_id and note["completed"])
        ])
