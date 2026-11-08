from __future__ import annotations

import os
import subprocess
from pathlib import Path


def copy_files(paths: list[str]) -> None:
    if os.name != "nt":
        raise RuntimeError("Copying files to the clipboard only works on Windows.")
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE

    class DROPFILES(ctypes.Structure):
        _fields_ = [("pFiles", wintypes.DWORD), ("pt", wintypes.POINT), ("fNC", wintypes.BOOL), ("fWide", wintypes.BOOL)]

    files = ("\0".join(str(Path(p).resolve()) for p in paths) + "\0\0").encode("utf-16-le")
    header = DROPFILES(pFiles=ctypes.sizeof(DROPFILES), fWide=True)
    size = ctypes.sizeof(DROPFILES) + len(files)
    handle = kernel32.GlobalAlloc(0x0042, size)
    if not handle:
        raise RuntimeError("Couldn't allocate clipboard memory.")
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, ctypes.byref(header), ctypes.sizeof(DROPFILES))
    ctypes.memmove(ptr + ctypes.sizeof(DROPFILES), files, len(files))
    kernel32.GlobalUnlock(handle)
    for _ in range(10):
        if user32.OpenClipboard(None):
            break
        import time
        time.sleep(0.05)
    else:
        kernel32.GlobalFree(handle)
        raise RuntimeError("The clipboard is busy. Try again.")
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(15, handle):
            kernel32.GlobalFree(handle)
            raise RuntimeError("Windows refused the clipboard data.")
    finally:
        user32.CloseClipboard()


def show_in_explorer(path: str) -> None:
    if os.name == "nt":
        subprocess.Popen(["explorer.exe", f"/select,{Path(path).resolve()}"], shell=False)
