"""Detect whether any application currently holds the webcam, on Windows.

Windows records camera access in the per-user "consent store" registry hive
whenever an app uses the modern MediaCapture/DirectShow camera APIs (this
covers Teams, Zoom, Meet-in-browser, Slack, OBS, the built-in Camera app,
etc.). Each app gets a subkey with LastUsedTimeStart/LastUsedTimeStop
FILETIME values; while the camera is actively open, LastUsedTimeStop is 0.
"""
from __future__ import annotations

import ctypes
import logging
import subprocess
import threading
from ctypes import wintypes
from typing import Callable

import winreg

logger = logging.getLogger(__name__)

_CONSENT_STORE = (
    r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam"
)


def _subkey_names(key: winreg.HKEYType) -> list[str]:
    names = []
    index = 0
    while True:
        try:
            names.append(winreg.EnumKey(key, index))
        except OSError:
            break
        index += 1
    return names


def _entry_in_use(key: winreg.HKEYType) -> bool:
    try:
        start, _ = winreg.QueryValueEx(key, "LastUsedTimeStart")
    except FileNotFoundError:
        return False
    try:
        stop, _ = winreg.QueryValueEx(key, "LastUsedTimeStop")
    except FileNotFoundError:
        stop = 0
    return bool(start) and not stop


def _process_running(image_name: str) -> bool:
    """Return True if a process with this exact image name is running.

    If an app is force-closed, crashes, or the PC is restarted while it
    holds the webcam open, Windows can leave LastUsedTimeStop at 0 forever
    for that app, permanently marking the webcam "in use" even though
    nothing is actually using it. This cross-check catches that: a
    NonPackaged entry only counts as in use if its owning process is
    actually still running.
    """
    try:
        result = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh", "/fi", f"imagename eq {image_name}"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except OSError:
        return True  # can't check; assume running rather than wrongly clear DND
    return image_name.lower() in result.stdout.lower()


def is_webcam_in_use() -> bool:
    """Return True if any app is currently holding the webcam open."""
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CONSENT_STORE)
    except FileNotFoundError:
        return False

    with root:
        for name in _subkey_names(root):
            if name == "NonPackaged":
                try:
                    nonpackaged = winreg.OpenKey(root, "NonPackaged")
                except FileNotFoundError:
                    continue
                with nonpackaged:
                    for exe_name in _subkey_names(nonpackaged):
                        with winreg.OpenKey(nonpackaged, exe_name) as exe_key:
                            if not _entry_in_use(exe_key):
                                continue
                            image_name = exe_name.replace("#", "\\").rsplit("\\", 1)[-1]
                            if _process_running(image_name):
                                return True
                continue

            with winreg.OpenKey(root, name) as app_key:
                if _entry_in_use(app_key):
                    return True

    return False


# --- Event-driven watching, via RegNotifyChangeKeyValue -------------------
#
# winreg has no binding for RegNotifyChangeKeyValue, so we call into
# advapi32/kernel32 directly with ctypes. This blocks a background thread
# on the registry key instead of polling it.

_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_advapi32.RegNotifyChangeKeyValue.argtypes = [
    wintypes.HKEY,
    wintypes.BOOL,
    wintypes.DWORD,
    wintypes.HANDLE,
    wintypes.BOOL,
]
_advapi32.RegNotifyChangeKeyValue.restype = ctypes.c_long

_kernel32.CreateEventW.argtypes = [
    wintypes.LPVOID,
    wintypes.BOOL,
    wintypes.BOOL,
    wintypes.LPCWSTR,
]
_kernel32.CreateEventW.restype = wintypes.HANDLE

_kernel32.WaitForMultipleObjects.argtypes = [
    wintypes.DWORD,
    ctypes.POINTER(wintypes.HANDLE),
    wintypes.BOOL,
    wintypes.DWORD,
]
_kernel32.WaitForMultipleObjects.restype = wintypes.DWORD

_kernel32.SetEvent.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

_REG_NOTIFY_CHANGE_NAME = 0x00000001
_REG_NOTIFY_CHANGE_LAST_SET = 0x00000004
_WAIT_OBJECT_0 = 0x00000000
_INFINITE = 0xFFFFFFFF


class WebcamWatcher:
    """Runs a background thread that blocks on the webcam registry key and
    invokes `callback(in_use: bool)` whenever the usage state changes.

    This does no polling: the thread sleeps in a Win32 wait until Windows
    itself signals that something under the consent-store key changed, then
    re-checks `is_webcam_in_use()` and re-arms the wait.
    """

    def __init__(self, callback: Callable[[bool], None]):
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._stop_handle = _kernel32.CreateEventW(None, True, False, None)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("WebcamWatcher already started")
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        _kernel32.SetEvent(self._stop_handle)
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def __enter__(self) -> "WebcamWatcher":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()
        _kernel32.CloseHandle(self._stop_handle)

    def _run(self) -> None:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CONSENT_STORE)
        except FileNotFoundError:
            logger.error(
                "Registry key for webcam consent not found. Use the camera "
                "once (e.g. open the Camera app) so Windows creates it, then restart."
            )
            return

        last_state = is_webcam_in_use()
        self._callback(last_state)

        try:
            key_handle = wintypes.HKEY(int(key))
            while True:
                notify_handle = _kernel32.CreateEventW(None, True, False, None)
                try:
                    status = _advapi32.RegNotifyChangeKeyValue(
                        key_handle,
                        True,  # watch the whole subtree (per-app subkeys)
                        _REG_NOTIFY_CHANGE_NAME | _REG_NOTIFY_CHANGE_LAST_SET,
                        notify_handle,
                        True,  # asynchronous: signals notify_handle later
                    )
                    if status != 0:
                        raise ctypes.WinError(ctypes.get_last_error())

                    handles = (wintypes.HANDLE * 2)(notify_handle, self._stop_handle)
                    result = _kernel32.WaitForMultipleObjects(2, handles, False, _INFINITE)

                    if result == _WAIT_OBJECT_0 + 1:  # stop() was called
                        return

                    new_state = is_webcam_in_use()
                    if new_state != last_state:
                        last_state = new_state
                        self._callback(new_state)
                finally:
                    _kernel32.CloseHandle(notify_handle)
        finally:
            key.Close()


if __name__ == "__main__":
    print("Webcam in use right now:", is_webcam_in_use())
    print("Watching for changes, press Ctrl+C to stop...")
    with WebcamWatcher(lambda active: print("Webcam in use:", active)):
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
