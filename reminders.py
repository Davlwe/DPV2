"""Per-note reminder timing, separate from timers and windows."""

from datetime import datetime, timedelta, timezone


REMINDER_CHOICES = (1, 5, 10)
DEFAULT_REMINDER_MINUTES = 5


def validate_reminder_minutes(value):
    if type(value) is not int or value not in REMINDER_CHOICES:
        raise ValueError("Reminder lead time must be 1, 5, or 10 minutes.")
    return value


def pending_reminders(notes, now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    return [
        note for note in notes
        if not note["completed"] and not note.get("reminded", False)
        and now >= datetime.fromisoformat(note["due_at"]) - timedelta(
            minutes=validate_reminder_minutes(note.get("reminder_minutes", DEFAULT_REMINDER_MINUTES)))
    ]
