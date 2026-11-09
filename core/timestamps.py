"""Dosya zaman damgası koruması (Windows).

yt-dlp indirme sonrası dosyanın modification time'ını videoya ait upload
tarihine ayarır ve korur. Windows'ta creation time standart kütüphane ile
ayarlanamadığından ctypes + SetFileTime kullanılır: yeni inen her dosyanın
creation time'ı mtime'a eşitlenir. Daha önce sabitlenmiş dosyalara
dokunulmaz (yalnızca creation > modification olanlar işlenir).
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

# Unix epoch (1970) -> Windows FILETIME (1601) dönüşüm katsayısı (100 ns birim)
_EPOCH_DIFF = 116_444_736_000_000_000

_FILE_WRITE_ATTRIBUTES = 0x0100
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_NORMAL = 0x80
_INVALID_HANDLE = ctypes.c_void_p(-1).value


def set_creation_time(path: Path, unix_ts: float) -> bool:
    """Dosyanın creation time'ını verilen Unix zaman damgasına ayarlar."""
    try:
        import ctypes.wintypes as wintypes

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ]
        handle = kernel32.CreateFileW(
            str(path), _FILE_WRITE_ATTRIBUTES, 0, None,
            _OPEN_EXISTING, _FILE_ATTRIBUTE_NORMAL, None,
        )
        if not handle or handle == _INVALID_HANDLE:
            return False
        try:
            value = int(unix_ts * 10_000_000) + _EPOCH_DIFF
            ctime = wintypes.FILETIME(value & 0xFFFFFFFF, value >> 32)
            kernel32.SetFileTime.argtypes = [
                ctypes.c_void_p, ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ]
            ok = bool(kernel32.SetFileTime(handle, ctypes.byref(ctime), None, None))
            return ok
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def fix_timestamps_in_dir(folder: Path) -> list[Path]:
    """Klasördeki yeni inen dosyaların creation time'ını mtime'a eşitler.

    Yalnızca creation time > modification time olan dosyalar işlenir; bu da
    doğal olarak sadece az önce inen dosyalar demektir. Daha önce sabitlenmiş
    dosyalar (creation == mtime) asla değiştirilmez.

    Dönüş: sabitlenen dosyaların listesi.
    """
    fixed: list[Path] = []
    if not folder.exists():
        return fixed
    for entry in folder.iterdir():
        if not entry.is_file():
            continue
        try:
            st = os.stat(entry)
        except OSError:
            continue
        # Windows'ta st_ctime = creation time
        if st.st_ctime > st.st_mtime + 1:
            if set_creation_time(entry, st.st_mtime):
                fixed.append(entry)
    return fixed
