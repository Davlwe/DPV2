"""Task counts and session-only mood, independent of pet animations."""

from datetime import datetime, timezone

MOOD_REFRESH_MS = 1000
MOOD_COLORS = {
    "Calm": "#8CA9E8",
    "Focused": "#51CDBE",
    "Concerned": "#E28DA4",
    "Happy": "#F3D36B",
}


class TaskMood:
    def __init__(self):
        self.state = "Calm"
        self.pending = self.completed = self.overdue = 0

    def refresh(self, notes, now=None, completed_task=False):
        now = now or datetime.now(timezone.utc)
        pending = [note for note in notes if not note["completed"]]
        self.pending = len(pending)
        self.completed = len(notes) - self.pending
        self.overdue = sum(datetime.fromisoformat(note["due_at"]) <= now for note in pending)
        if self.overdue:
            self.state = "Concerned"
        elif self.pending:
            self.state = "Focused"
        elif self.completed and (completed_task or self.state == "Happy"):
            self.state = "Happy"
        else:
            self.state = "Calm"

    def description(self):
        return (f"{self.state} — {self.pending} pending, {self.completed} completed, "
                f"{self.overdue} overdue")
