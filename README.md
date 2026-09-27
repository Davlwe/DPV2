# SuperDpet

SuperDpet is a local desktop companion that pairs an animated character with notes,
due-time reminders, and a task-aware mood. This GIBC V2 **Track 3** submission
explores a friendly desktop interface for everyday task management.

## Features

- Standing and sitting poses, saved between launches.
- A matching wave for each pose, randomized greetings, and automatic blinking.
- Dragging to reposition the pet without triggering a greeting.
- Add Note and View Notes, per-task completion checkboxes, and confirmed deletion.
- Reminders 1, 5, or 10 minutes before a note's due time.
- Mood colors based on pending, overdue, and completed tasks.
- Right-click settings, optional startup at sign-in, tray controls where available,
  and an explicit Quit action.

The app runs locally. It does not need an API key, an AI service, or an internet
connection during normal use. Installing dependencies requires package access.

## Setup and launch

Use **Python 3.14** for the demonstrated setup (tested with Python 3.14.4).
Other Python versions have not been verified for this submission. A graphical
desktop is required. The pinned dependencies are PySide6 6.11.2 for the app and
Pillow 12.3.0 for asset preparation and image tests; pytest is not required.

Clone or download this repository, then open a terminal in its root directory
(the directory containing `main.py`). All commands below run from that directory.

### Linux / WSL

Ensure Python 3.14 and its `venv` support are installed. On WSL, a working GUI
display such as WSLg is also required.

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

### macOS

Install Python 3.14 and run the same commands as Linux from a graphical desktop
session. Native macOS GUI and sign-in behavior still need platform testing.

### Windows (PowerShell)

Install native Windows Python 3.14, then run:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

These commands use the virtual environment directly; activation is optional.
Create the environment on the machine you will use rather than copying `.venv`
from another operating system. There is no packaged installer in this repository.

## Walkthrough

1. **Click:** short left-click the pet to see a wave, a randomly selected greeting,
   and **Add Note** / **View Notes**. The controls hide after about four seconds
   of inactivity. Clicking again restarts the greeting and wave.
2. **Drag:** hold the left button and move the pet. Dragging hides the controls
   and cancels a wave; releasing a drag does not trigger another wave.
3. **Change pose:** right-click and choose **Sit down** or **Stand up**. Standing
   is the initial default. Sitting clicks remain seated throughout their wave.
   The saved pose returns after restarting; waving does not change it.
4. **Add a note:** enter text, choose a local due date/time, and select a reminder.
   **1, 5, and 10 minutes mean minutes before the due time**, not minutes from now.
   For example, a 10:00 due time with a 5-minute reminder alerts at 09:55.
5. **View notes:** each task has a card with its text, local due time, and reminder
   lead time. Check the box on the right to complete it; uncheck to mark it pending
   again. Completed titles are dimmed and struck through. The adjacent **×** button
   deletes that task after confirmation, including any future reminder. Changes
   save immediately. Editing task text and due times is not currently offered.
6. **Reminders:** an orange glow and a separate reminder window announce matching
   notes. Dismiss the reminder to resume normal greetings and blinking. The app
   must remain running for reminders; Quit stops them. On relaunch, unshown
   reminders whose trigger time has passed are caught up once. Completed or
   already-reminded notes do not trigger again.
   Unchecking a task preserves its reminder history: an already-shown reminder
   will not repeat, while an unshown reminder follows the original due time.
7. **Settings and exit:** right-click **Settings** to set the default reminder for
   future notes and manage startup where supported. **Quit** exits completely.
   When a tray is available, **Hide Pet** leaves reminder checks running and
   **Show Pet** restores the pet.

Both poses blink at randomized intervals of 2–5 seconds. Dragging, waving, modal
forms, and active reminders pause blinking; it resumes afterward. Ordinary
menus and the informational tray notice do not suspend blinking.

### Mood

| Mood | Color | Meaning |
|---|---|---|
| Calm | Blue | No pending tasks, without an active completion mood |
| Focused | Turquoise | Pending tasks, none overdue |
| Concerned | Rose | At least one pending task has reached its due time |
| Happy | Gold | The last pending task was completed during this session |

Hover over the pet or tray icon for counts and the mood name. Overdue counts are
included in pending counts. Completing a task also produces a brief celebration.
Happy persists until a new pending task is added or all completed notes are
removed; restarting with only completed notes begins Calm. Orange reminder glow
has priority over the task mood and restores the current mood after dismissal.

## Local data and startup

Notes are stored in `notes.json`; pose, reminder defaults, and startup consent are
stored separately in `preferences.json`. Both use Qt's application data location,
not the checkout. Typical locations are:

| Platform | Approximate directory |
|---|---|
| Linux / WSL | `~/.local/share/SuperDpet/` (or under `XDG_DATA_HOME`) |
| Windows | `%APPDATA%\SuperDpet\` |
| macOS | `~/Library/Application Support/SuperDpet/` |

Locations can vary with OS configuration. Files contain local, unencrypted JSON;
there is no cloud synchronization. Do not upload personal data files. Quit the
app before backing up or restoring them. Unreadable data is left untouched and
saving is disabled rather than replacing it with an empty file.

Startup is optional and off by default. On supported desktops, the first launch
asks for consent. **No thanks** declines; Settings can change the choice later.
Registration uses the current user's Windows Run entry, Linux XDG autostart
entry, or macOS LaunchAgent. It points to this checkout and its Python interpreter.
If either moves, launch manually and save the setting again. Disable startup
before removing the checkout. Quit stops the current session; it does not revoke
permission for the next sign-in.

## Platform limitations

- **Test coverage:** automated tests and visible Wayland checks were run in the
  development environment. Native Windows/macOS GUI and actual sign-in behavior
  are not yet verified. Mocked OS-registration tests are not native sign-in tests.
- **Tray:** some desktops do not provide a system tray. The app displays an
  informational notice and stays accessible; hiding to the tray is unavailable.
- **WSL:** GUI use needs a working display. Startup registration is intentionally
  disabled; the Linux app does not register a Windows sign-in application.
- **Wayland:** the compositor controls window placement and native dragging.
  Synthetic input can produce popup-grab warnings; physical menu and drag
  gestures should also be checked on the intended demo machine.
- **Qt/display setup:** a headless shell cannot show the pet. Linux may require
  distribution-specific Qt display libraries. A platform-plugin error should be
  resolved for the desktop environment rather than using offscreen mode to demo.
- **Window behavior:** the pet is not always-on-top and may be covered by other
  windows. Position is not persisted across restarts. The tray uses a small
  blue-and-white pet-face icon; native tray menus may follow the OS styling.
- **One instance at a time:** there is no instance lock or concurrent data merge.
  Running multiple pets against the same data can overwrite updates.
- **Timing:** reminders are checked while the app runs and can be delayed during
  sleep or suspension. They are not an operating-system alarm service.

## Development and verification

### Automated tests

Install `requirements.txt` first. Tests use Python's built-in `unittest`, temporary
note/preferences storage, and mocked startup registration.

Linux/macOS/WSL:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
```

Windows PowerShell:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:QT_QPA_PLATFORM
```

Offscreen tests cannot prove compositor behavior. From a graphical session,
without `QT_QPA_PLATFORM=offscreen`, run the visible checks one at a time:

```bash
.venv/bin/python tests/native_interaction_check.py --no-captures
.venv/bin/python tests/native_pose_check.py
```

On Windows, substitute `.venv\Scripts\python.exe`. The native pose check currently
uses a machine-specific temporary capture path that may require adaptation on
Windows; it is not an application runtime requirement. Native tests use temporary
data, simulate input, and close their test pet. Avoid interacting with the test
window while they run. Manually verify both pose-specific waves, resumed blinking,
seated dragging, menu switching, notes, reminder timing, tray fallback, and Quit.
Verify startup through actual sign-out/sign-in on each target native platform.

Without `--no-captures`, the interaction check writes generated screenshots under
`assets/diagnostics/`, which is ignored by Git. Capture outputs are not required
to run the app. Timing and animation guards live in `idle_behavior.py`.

### Developer mode and diagnostics

Both switches are **off by default** and enabled only by the exact value `1`.
Normal launches do not expose the developer reminder action.

```bash
SUPERDPET_DEV_MODE=1 .venv/bin/python main.py
SUPERDPET_DEBUG=1 .venv/bin/python main.py
```

`SUPERDPET_DEV_MODE` exposes **Developer test: create reminder in 5 seconds** in
the right-click menu. Selecting it creates a real, persistent `[DEVELOPER TEST]`
note using the current reminder lead time. Use separate test data or complete
and delete test notes before a demo; switching developer mode off does not delete
existing notes. The automated tests use isolated data instead.

`SUPERDPET_DEBUG` enables routine blink, paint, sprite, and drag diagnostics.
Actionable asset errors and storage error messages remain available without it.
The switches are independent and should be unset for the public demo.

In PowerShell, set `$env:SUPERDPET_DEV_MODE = "1"` or
`$env:SUPERDPET_DEBUG = "1"`, launch with `.venv\Scripts\python.exe main.py`, then
remove the chosen variable with `Remove-Item Env:SUPERDPET_DEV_MODE` or
`Remove-Item Env:SUPERDPET_DEBUG` before normal use.

## AI assistance and asset provenance

UI icons are drawn locally with Qt using rounded blue-to-white badges and dark
blue symbols. They scale to the requested size without an additional dependency.
Buttons retain text labels, with hover, pressed, focus, and disabled treatments.
The pet character artwork is separate from these UI icons.

Development was assisted by **OpenAI Codex**, including implementation, debugging,
tests, and documentation. The runtime uses local Python/Qt logic; greetings are
selected from predefined text and moods are derived from task counts.

The original character reference is retained as `assets/reference.png`. Character
sprites and animation variants were created with AI image-generation/editing
assistance based on that reference, with local image preparation and resizing.
Available generation prompts and export notes are preserved in `assets/*prompt*.txt`.
Those files record the available provenance, not a complete reproduction pipeline
for every asset, and do not establish ownership of the original reference.

Runtime uses the six 1024px standing/sitting open-eye, blink, and wave sprites.
The current 256px variants, reference image, and prompt files are retained.
Unused legacy idle/full-body/blink exports have been removed. Preserved prompts
may name those historical exports; they are not required by the running app.
`scripts/prepare_superdpet.py` is a legacy reference-preparation utility that
writes the older idle sprites; it is not needed for setup and does not generate
the current animation set.

## License

No license has been selected yet. This repository does not currently grant an
open-source license for its code or artwork. Code licensing and rights to the
reference and generated assets must be clarified before reuse or redistribution.
