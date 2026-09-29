# SuperDpet

**Tagline:** A desktop companion that helps you jot down notes and remember what comes next.

## Inspiration and problem

Small tasks and ideas are easy to forget while working at a computer. Opening a separate task manager adds friction. SuperDpet explores a friendlier way to capture those thoughts: a little companion on your desktop with notes and reminders a click away.

## What it does

SuperDpet is a local desktop pet that combines an animated character with a simple task notebook. Click the pet to see a greeting and open Add Note or View Notes. Each note has a due date, local due time, and a reminder one, five, or ten minutes before it is due. You can mark tasks complete or delete them with confirmation.

The companion blinks, waves, sits, and sleeps after inactivity. Its mood color reflects pending, overdue, or completed tasks. A reminder window and orange glow draw attention to a due reminder. The pet can be dragged around the desktop, and optional startup and system-tray controls fit it into everyday use.

## How we built it

The application uses Python and PySide6, the Python bindings for Qt 6. Qt widgets provide the transparent pet window, forms, menus, and task cards. Transparent PNG frames, timers, and property animations create blinking, waving, and breathing. Separate idle and sleep controllers coordinate transitions so a stale animation callback does not interrupt sleep or a reminder.

Notes are stored as local JSON with unique IDs, completion state, UTC timestamps, reminder lead times, and reminder history. The UI displays local times. Qt's QSaveFile commits file updates before the application changes its visible stored state. Preferences are stored separately. Unreadable data is preserved, with saving disabled to avoid overwriting it.

A timer checks reminders every 250 milliseconds while the app runs. Completed and already-reminded notes are excluded; missed, unshown reminders are caught up on relaunch. Mood is calculated from task state using deterministic rules. No language model, remote API, training pipeline, or dataset is required at runtime.

OpenAI Codex assisted with development, debugging, testing, and documentation. AI image-generation/editing tools assisted with character sprites, and Pillow supports local asset preparation. Available prompts are preserved in the repository.

## Challenges and methodology

The central implementation challenge was coordinating overlapping interactions: a click should wave, a drag should move the pet, and dialogs, reminders, and sleep must not fight the blink timer. The implementation separates animation state from persistent pose and task data. Automated tests exercise state transitions, reminders, persistence, startup registration, and asset consistency; native GUI checks cover behavior that offscreen tests cannot establish.

## Accomplishments

The result is a working desktop companion with persistent notes, configurable reminder lead times, task completion, and coordinated animation. In the September 29, 2026 submission-preparation run, all 66 automated tests passed using Qt's offscreen backend. This does not establish native Windows/macOS compatibility or actual sign-in behavior.

## What we learned

A small desktop interface still needs careful state management. Keeping storage, reminder rules, mood rules, and animation controllers separate makes behavior easier to verify. Local storage also keeps the core workflow usable without an account or internet connection.

## What's next

Potential improvements include editing existing notes, packaged installers, saved window positions, and broader native-platform testing. These are future work, not current features.

## Source

https://github.com/Davlwe/DPV2

## Current limitations

The app must be running to display reminders. Notes are local unencrypted JSON; there is no cloud synchronization. The owner has tried the macOS GUI and reported a stale outline during pose changes. A fix is prepared but needs macOS verification. Native Windows GUI and real sign-in behavior still need testing. The character reference's ownership and artwork licensing are not established by the available provenance files.
