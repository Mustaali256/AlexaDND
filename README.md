# AlexaDND

Watches a Windows PC's webcam. While it's in use (a video call in Teams,
Zoom, Meet, etc.), it turns on Do Not Disturb for one Echo device; when the
camera stops, it turns DND back off. Optionally pops a desktop notification
when the webcam turns on.

Windows only, since webcam detection reads a Windows-specific registry key.

## How it works

- `webcam_monitor.py` reads Windows' per-app camera-usage registry
  (`ConsentStore\webcam`) to tell whether any app currently holds the
  webcam open. This covers apps using the standard Windows camera
  permission system (Teams, Zoom, browsers, Slack, the Camera app, etc.).
  It won't see something that bypasses that consent system entirely, which
  is rare for mainstream conferencing apps.
  - `is_webcam_in_use()` is a plain point-in-time check.
  - `WebcamWatcher` is event-driven: a background thread blocks on
    `RegNotifyChangeKeyValue` (no polling) and calls a callback with
    `True`/`False` only when the state actually changes. It has no
    dependency on Alexa, so it can be started and stopped, and tested, on
    its own.
- `alexa_dnd.py` uses [alexapy](https://gitlab.com/keatontaylor/alexapy) to
  log in to Amazon and flip DND on a named Echo device.
- `notifications.py` pops a Windows toast via `windows-toasts` when the
  webcam turns on.
- `main.py` wires a `WebcamWatcher` to both `notify()` and
  `AlexaDndController.set_dnd`.

## Requirements

- Windows 10 or 11
- Python 3.10+
- An Amazon account with at least one Echo device

## Setup

1. Install dependencies:
   ```
   py -m pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your Amazon email/password and
   the exact Echo device name as shown in the Alexa app (Devices > Echo &
   Alexa).
3. Run the one-time interactive login:
   ```
   py setup_login.py
   ```
   This opens your browser to Amazon's real sign-in page (see "Why a
   browser login?" below); sign in there like normal, including any
   captcha or 2FA prompt. The session is then saved under
   `.alexa_cookies/` so future runs don't need any interactive input.
4. Start watching:
   ```
   py main.py
   ```
   Leave it running while you work, or set it up to start automatically
   (see below).

Session cookies are reused automatically after step 3, so `main.py`
normally won't need any interactive input. Amazon sessions do eventually
expire; if `main.py` reports a login failure, just re-run `setup_login.py`.

### Why a browser login?

Amazon's plain email/password sign-in form gets flagged as automated and
silently redirected to a fake "create account" page instead of actually
signing in. `setup_login.py` works around this with `alexapy`'s proxy-based
login: it runs a small local server and has you sign in through your normal
browser, which behaves exactly like a real Amazon login (including any
captcha or 2FA), and captures the resulting session.

## Running it automatically at login

Use **Task Scheduler**, not a Windows service. A service runs in Session 0
with no access to your desktop or the saved cookie file under your user
profile, and can't prompt you if a reauth is ever needed. A scheduled task
set to run at logon stays in your normal user session (so it can see
`.alexa_cookies/`) while running with no visible window.

Point Task Scheduler at `pythonw.exe`, not `python.exe`. `python.exe` is a
console app, so pointing Task Scheduler at it (an easy mistake, since it's
what step 1 below finds first) opens a visible terminal window every time
the task runs. `pythonw.exe`, in the same folder, is the windowless
variant built for exactly this.

With no console attached, there's also nothing to show what's happening,
so `main.py` always writes to `alexadnd.log` next to it, in addition to
the console when one exists. Check that file to confirm it's running or
to debug a problem.

1. Find your Python install path:
   ```
   py -c "import sys; print(sys.executable)"
   ```
   `pythonw.exe` (windowless) lives next to that `python.exe`.
2. Open Task Scheduler > *Create Task...* (not *Basic Task*, so you get the
   "run whether user is logged on" options).
3. **General** tab: name it (e.g. "AlexaDND"). Leave "Run only when user is
   logged on" selected; this is what keeps it in your desktop session.
4. **Triggers** tab: *New...* > Begin the task **At log on**, for your user
   only.
5. **Actions** tab: *New...* >
   - Program/script: the full path to `pythonw.exe` from step 1
   - Add arguments: `main.py`
   - Start in: the full path to this project folder
6. **Conditions** tab: uncheck "Start the task only if the computer is on
   AC power" if this is a laptop.
7. Save. Right-click the task > *Run* to test it, then check
   `alexadnd.log`, Task Manager for a `pythonw.exe` process, or your Echo
   device's DND state when you open your webcam. No window should appear
   at any point.

If you already have a task pointed at `python.exe`, edit its Actions tab
to point at `pythonw.exe` instead of recreating the whole task.

## Troubleshooting

- **`python` isn't recognised, or opens the Microsoft Store**: Windows
  ships a `python`/`python3` command that's just a stub pointing at the
  Store ("App execution alias"). Use the `py` launcher instead (as in the
  commands above), which Python's own installer registers properly. If
  `py` also fails, install Python from
  [python.org](https://python.org) (not the Store), or go to *Settings >
  Apps > Advanced app settings > App execution aliases* and turn off the
  `python.exe`/`python3.exe` entries.
- **Multiple Python versions installed**: a bare `pip` on PATH may resolve
  to a different interpreter than `py` does, which can install packages
  where the interpreter you actually run can't see them. Pin an exact
  version for every command, e.g. `py -3.12 -m pip install ...` and
  `py -3.12 main.py`, instead of the unversioned `py`/`py -3`. Run
  `py -0p` to see which versions are installed and which one is currently
  the default.

## Note
- Amazon has no official public API for this. `alexapy` reverse-engineers
  the Alexa app's web endpoints, so a future Amazon change could break
  login or the DND call. This project isn't affiliated with Amazon.
