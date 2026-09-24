"""The fixed reminder rule, separate from timers and windows."""

from datetime import datetime, timedelta, timezone


REMINDER_LEAD = timedelta(minutes=30)


def pending_reminders(notes, now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    return [
        note for note in notes
        if not note["completed"] and not note.get("reminded", False)
        and now >= datetime.fromisoformat(note["due_at"]) - REMINDER_LEAD
    ]
