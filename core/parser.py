"""YouTube URL ve ID ayıklama.

Kabul edilen girişler:
  - https://www.youtube.com/playlist?list=PLxxxx
  - https://www.youtube.com/watch?v=VIDEOID&list=PLxxxx&index=1
  - https://youtu.be/VIDEOID
  - https://music.youtube.com/watch?v=VIDEOID&list=PLxxxx
  - Çıplak playlist ID (PL... / UU... vb.)
  - Çıplak 11 karakterlik video ID
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

PLAYLIST_ID_RE = re.compile(r"[?&]list=([A-Za-z0-9_-]+)")
VIDEO_ID_RE = re.compile(r"[?&]v=([A-Za-z0-9_-]{11})")
SHORT_URL_VIDEO_RE = re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})")

# Çıplak ID kalıpları
BARE_PLAYLIST_RE = re.compile(r"^(PL|UU|OL|FL|LL|RD|RDMM)[A-Za-z0-9_-]{10,}$")
BARE_VIDEO_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_KNOWN_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
)


class ParseError(ValueError):
    """Geçersiz giriş hatası (Türkçe mesajla)."""


@dataclass
class ParsedTarget:
    """Ayıklanmış hedef: video ID ve/veya playlist ID."""

    video_id: str | None = None
    playlist_id: str | None = None

    @property
    def is_empty(self) -> bool:
        return self.video_id is None and self.playlist_id is None

    def __str__(self) -> str:
        parts = []
        if self.video_id:
            parts.append(f"video={self.video_id}")
        if self.playlist_id:
            parts.append(f"playlist={self.playlist_id}")
        return ", ".join(parts)


def parse(text: str) -> ParsedTarget:
    """Serbest metinden video ve/veya playlist ID'sini ayıklar.

    Hata durumunda ParseError (ValueError) fırlatır.
    """
    if not text or not text.strip():
        raise ParseError("Giriş boş.")

    text = text.strip().strip("<>\"'").strip()

    video_id: str | None = None
    playlist_id: str | None = None

    # 1) urlparse ile standart yol
    try:
        parsed = urlparse(text)
        host = (parsed.hostname or "").lower()
        if host in _KNOWN_HOSTS:
            qs = parse_qs(parsed.query)
            if not video_id and qs.get("v"):
                v = qs["v"][0]
                if BARE_VIDEO_RE.match(v):
                    video_id = v
            if not playlist_id and qs.get("list"):
                playlist_id = qs["list"][0]
            if not video_id and host.endswith("youtu.be") and parsed.path:
                m = re.match(r"^/([A-Za-z0-9_-]{11})", parsed.path)
                if m:
                    video_id = m.group(1)
    except ValueError:
        pass

    # 2) Regex yedeği — yalnızca metin bir YouTube bağlantısı gibiyse
    looks_youtube = "youtu" in text.lower()
    if looks_youtube:
        if playlist_id is None:
            m = PLAYLIST_ID_RE.search(text)
            if m:
                playlist_id = m.group(1)
        if video_id is None:
            m = VIDEO_ID_RE.search(text)
            if m:
                video_id = m.group(1)
            else:
                m = SHORT_URL_VIDEO_RE.search(text)
                if m:
                    video_id = m.group(1)

    # 3) Çıplak ID
    if playlist_id is None and video_id is None:
        if BARE_PLAYLIST_RE.match(text):
            playlist_id = text
        elif BARE_VIDEO_RE.match(text):
            video_id = text

    if playlist_id is None and video_id is None:
        raise ParseError(
            "Geçerli bir YouTube bağlantısı veya ID bulunamadı.\n"
            "Örnek: https://www.youtube.com/playlist?list=PLxxxxxxxx"
        )

    return ParsedTarget(video_id=video_id, playlist_id=playlist_id)


def playlist_url(playlist_id: str) -> str:
    return f"https://www.youtube.com/playlist?list={playlist_id}"


def video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
