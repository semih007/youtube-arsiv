"""Küçük yardımcılar: dosya adı temizleme, boyut/süre biçimlendirme."""

from __future__ import annotations

import re

# Windows'ta dosya adlarında yasak karakterler
_INVALID_CHARS = '<>:"/\\|?*'
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename(name: str, max_len: int = 120) -> str:
    """Bir YouTube başlığını güvenli bir Windows klasör/dosya adına çevirir."""
    out = "".join("_" if c in _INVALID_CHARS else c for c in name)
    out = re.sub(r"\s+", " ", out).strip().rstrip(".")
    if not out:
        out = "Adsiz"
    if out.upper() in _RESERVED_NAMES:
        out = "_" + out
    if len(out) > max_len:
        out = out[:max_len].rstrip()
    return out


def human_size(num_bytes) -> str:
    """Bayt sayısını okunur boyut metnine çevirir ('12,4 MB' gibi)."""
    if not num_bytes:
        return "?"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f}".replace(".", ",") + f" {unit}"
        size /= 1024
    return "?"


def format_duration(seconds) -> str:
    """Saniyeyi '3:25' / '1:04:12' biçimine çevirir."""
    if seconds is None:
        return "?"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
