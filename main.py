"""Mirror the webcam's in-use state to the Echo Dot's Do Not Disturb setting.

Event-driven: WebcamWatcher blocks on the registry instead of polling, and
calls back into here only when the webcam actually turns on or off.

Run `setup_login.py` once first to establish a saved Alexa session.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from alexa_dnd import AlexaDndController
from config import load_config
from notifications import notify
from webcam_monitor import WebcamWatcher

# Run headless via pythonw.exe (e.g. from Task Scheduler) has no console, so
# logging to stderr alone would be invisible. Always log to a file next to
# this script; also log to the console when one is actually attached.
_LOG_FILE = Path(__file__).resolve().parent / "alexadnd.log"
_handlers: list[logging.Handler] = [logging.FileHandler(_LOG_FILE, encoding="utf-8")]
if sys.stderr is not None:
    _handlers.append(logging.StreamHandler())

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=_handlers
)
logger = logging.getLogger(__name__)


async def run() -> None:
    config = load_config()
    controller = AlexaDndController(config)
    await controller.ensure_logged_in()

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def on_change(camera_active: bool) -> None:
        if camera_active:
            notify("Webcam active", f"Setting '{config.device_name}' to Do Not Disturb.")

        # Called from the watcher's background thread; hop onto the asyncio
        # loop and wait for the DND call to finish before re-arming the
        # registry wait, so overlapping toggles can't race each other.
        future = asyncio.run_coroutine_threadsafe(controller.set_dnd(camera_active), loop)
        try:
            future.result()
        except Exception:
            logger.exception("Failed to update DND for webcam state=%s", camera_active)

    watcher = WebcamWatcher(on_change)
    watcher.start()
    logger.info("Watching webcam (event-driven) for device '%s'", config.device_name)

    try:
        await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        watcher.stop()
        await controller.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
