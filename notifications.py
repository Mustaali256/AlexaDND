"""Desktop toast notifications on Windows."""
from __future__ import annotations

from windows_toasts import Toast, WindowsToaster

_toaster = WindowsToaster("AlexaDND")


def notify(title: str, message: str) -> None:
    toast = Toast()
    toast.text_fields = [title, message]
    _toaster.show_toast(toast)


if __name__ == "__main__":
    notify("AlexaDND", "Test notification.")
