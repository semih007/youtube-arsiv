"""Tekil video format sorgulama: --dump-json ile kullanılabilir tüm akışlar."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .utils import format_duration, human_size


@dataclass
class FormatInfo:
    """Tek bir yt-dlp format kaydı."""

    format_id: str
    ext: str
    kind: str = "both"  # "audio" | "video" | "both"
    resolution: str = ""
    fps: int | None = None
    vcodec: str = ""
    acodec: str = ""
    tbr: float | None = None  # toplam kbps
    abr: float | None = None  # ses kbps
    filesize: int | None = None
    filesize_approx: int | None = None
    note: str = ""

    @property
    def size_bytes(self) -> int | None:
        return self.filesize or self.filesize_approx

    def display(self) -> tuple[str, str, str, str, str, str, str]:
        """Treeview satırı: (Tür, ID, Uzantı, Kalite, Codec, Bitrate, Boyut)."""
        if self.kind == "audio":
            quality = f"{int(self.abr)} kbps" if self.abr else self.note or "-"
            codec = self.acodec or "-"
        elif self.kind == "video":
            quality = self.resolution or "-"
            if self.fps:
                quality += f" {self.fps}fps"
            codec = self.vcodec or "-"
        else:
            quality = self.resolution or self.note or "-"
            codec = f"{self.vcodec} + {self.acodec}".strip(" +")
        kind_tr = {"audio": "Ses", "video": "Video", "both": "Ses+Video"}[self.kind]
        bitrate = f"{int(self.tbr)} kbps" if self.tbr else "-"
        return (kind_tr, self.format_id, self.ext, quality, codec, bitrate, human_size(self.size_bytes))


@dataclass
class VideoInfo:
    """Sorgulanan videonun özet bilgi + format listesi."""

    video_id: str
    title: str = ""
    duration: int = 0
    uploader: str = ""
    webpage_url: str = ""
    formats: list[FormatInfo] = field(default_factory=list)

    @property
    def duration_str(self) -> str:
        return format_duration(self.duration)

    def audio_formats(self) -> list[FormatInfo]:
        return [f for f in self.formats if f.kind == "audio"]

    def video_formats(self) -> list[FormatInfo]:
        return [f for f in self.formats if f.kind == "video"]

    def get_format(self, format_id: str) -> FormatInfo | None:
        for f in self.formats:
            if f.format_id == format_id:
                return f
        return None


def _classify(fmt: dict) -> str | None:
    """Formatı sınıflandırır; kullanılmayacaksa None döner."""
    vcodec = (fmt.get("vcodec") or "none").lower()
    acodec = (fmt.get("acodec") or "none").lower()
    ext = (fmt.get("ext") or "").lower()

    # Storyboard / resim akışlarını atla
    if ext == "mhtml" or "storyboard" in (fmt.get("note") or "").lower():
        return None
    if vcodec == "none" and acodec == "none":
        return None

    if vcodec == "none" and acodec != "none":
        return "audio"
    if vcodec != "none" and acodec == "none":
        return "video"
    return "both"


def query_video(runner, url: str, timeout: int = 120) -> VideoInfo:
    """yt-dlp --dump-single-json ile videonun bilgilerini ve formatlarını çeker."""
    proc = runner.run_capture(
        ["-J", "--no-playlist", url],
        timeout=timeout,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        # Hata mesajından ilk anlamlı satırı al
        for line in err.splitlines():
            if "ERROR" in line:
                err = line
                break
        raise RuntimeError(f"Video bilgisi alınamadı:\n{err or 'Bilinmeyen hata'}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Video yanıtı çözümlenemedi: {exc}") from exc

    info = VideoInfo(
        video_id=data.get("id") or "",
        title=data.get("title") or "",
        duration=data.get("duration") or 0,
        uploader=data.get("uploader") or data.get("channel") or "",
        webpage_url=data.get("webpage_url") or url,
    )

    for fmt in data.get("formats", []):
        kind = _classify(fmt)
        if kind is None:
            continue
        info.formats.append(
            FormatInfo(
                format_id=str(fmt.get("format_id") or fmt.get("format_note") or "?"),
                ext=fmt.get("ext") or "",
                kind=kind,
                resolution=fmt.get("resolution") or "",
                fps=int(fmt["fps"]) if fmt.get("fps") else None,
                vcodec=fmt.get("vcodec") or "",
                acodec=fmt.get("acodec") or "",
                tbr=fmt.get("tbr"),
                abr=fmt.get("abr"),
                filesize=fmt.get("filesize"),
                filesize_approx=fmt.get("filesize_approx"),
                note=fmt.get("format_note") or "",
            )
        )

    # Ses: bitrate'e göre azalan; Video: çözünürlük+fps azalan sırala
    info.formats.sort(
        key=lambda f: (
            {"audio": 0, "video": 1, "both": 2}[f.kind],
            -(f.abr or f.tbr or 0),
            -((int(f.resolution.rstrip("p")) if f.resolution.rstrip("p").isdigit() else 0)),
        )
    )
    return info
