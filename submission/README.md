# Submission package

| Requirement | Prepared | Remaining |
|---|---|---|
| 01 Project description | [Copy-ready Devpost text](DEVPOST.md) | Paste into Devpost and review team claims |
| 02 Public source and README | [Public GitHub repository](https://github.com/Davlwe/DPV2), setup/prerequisites/usage in root README; visibility checked September 29, 2026 | Commit/push this new submission package if it should appear in the repository; verify final submitted revision |
| 03 Demo video | [3:20 recording plan and English narration](DEMO_SCRIPT.md) | Record, upload public/unlisted, and add actual URL |
| 04 Built With | [Technology inventory](BUILT_WITH.md) | Confirm actual hardware, development OS, and any additional AI tools |
| 05 Team information | Required fields below | Supply real full names and Devpost accounts; add every teammate to submission |
| 06 Screenshots | Three PNG captures linked below | Upload to Devpost |

## Screenshots and captions

1. [Pet and quick actions](screenshots/01-pet.png) — “Click the desktop companion to greet it and access Add Note or View Notes.”
2. [Add note](screenshots/02-add-note.png) — “Capture a thought with a local due date/time and a reminder before it is due.”
3. [View notes](screenshots/03-view-notes.png) — “Review pending and completed notes, due times, and reminder lead times.”

These are actual Qt widget renders at 2× scale using isolated sample data, captured with the offscreen backend. They are not AI-generated mockups, full-desktop captures, or proof of native OS integration. The pet image retains the window's transparency. Reproduce from the repository root:

```bash
QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 .venv/bin/python scripts/capture_submission.py
```

## Team details to fill in

For **every member**, collect real full name and Devpost profile URL, then add that account through the Devpost submission. Listing names in this file alone does not enroll teammates or meet the certificate requirement.

Team members: **Awaiting owner-provided names and profile links.**

Demo URL: **Awaiting recorded and uploaded video.**

Actual development hardware and OS: **Awaiting team confirmation.**

## Verification

September 29, 2026: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v` passed all 66 tests. This checks automated behavior; it does not verify every native desktop or startup at actual sign-in. No application code was changed for this submission package.

Before submitting, check that all links work while signed out, the final video runs 2–5 minutes and has English audio/subtitles, all three images are uploaded, and every teammate is added by their account. No Devpost submission or video upload has been performed by this preparation step.
