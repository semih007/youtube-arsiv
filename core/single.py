r"""Tekil video/şarkı indirme modülü (çalma listelerinden tamamen bağımsız).

- Format sorgulama: core.formats.query_video (--dump-json)
- Üç indirme türü:
    1. Sadece Ses      -> seçilen format/kalite, ffmpeg ile dönüşüm (MP3/AAC/...)
    2. Sadece Video    -> seçilen DASH video akışı, dönüştürmesiz
    3. Ses + Video     -> seçilen video + ses akışı, ffmpeg ile kayıpsız mux
- İndirme yeri: <Müzik>\Tekil\ ; bu klasörde de 'indirilenler.txt' arşivi
  tutulur -> aynı video ikinci kez indirilmez.
"""

from __future__ import annotations

from pathlib import Path

from .config import ConfigStore
from .formats import FormatInfo, VideoInfo, query_video
from .runner import Runner
from .timestamps import fix_timestamps_in_dir

ARCHIVE_NAME = "indirilenler.txt"
SINGLE_FOLDER_NAME = "Tekil"

# Ses dönüşümü için desteklenen hedef formatlar
AUDIO_FORMATS = ["mp3", "aac", "m4a", "flac", "opus", "ogg", "wav"]
# MP3/AAC gibi kayıplı formatlar için kalite seçenekleri
AUDIO_QUALITIES = ["320K", "256K", "192K", "128K", "96K"]


class SingleCancelled(Exception):
    """Kullanıcı indirmeyi iptal etti."""


class SingleDownloader:
    def __init__(self, config: ConfigStore, runner: Runner):
        self.config = config
        self.runner = runner

    # ---------------------------------------------------------------- klasörler

    def single_folder(self) -> Path:
        folder = self.config.download_root / SINGLE_FOLDER_NAME
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def archive_path(self) -> Path:
        return self.single_folder() / ARCHIVE_NAME

    def already_downloaded(self, video_id: str) -> bool:
        """Video daha önce tekil olarak indirilmiş mi?"""
        archive = self.archive_path()
        if not archive.exists():
            return False
        try:
            ids = archive.read_text(encoding="utf-8").split()
        except OSError:
            return False
        return video_id in ids

    # ---------------------------------------------------------------- sorgu

    def query(self, url: str) -> VideoInfo:
        return query_video(self.runner, url)

    # ---------------------------------------------------------------- argüman üretimi

    def _common_args(self, info: VideoInfo) -> list[str]:
        archive = self.archive_path()
        out_tmpl = str(self.single_folder() / "%(title)s [%(id)s].%(ext)s")
        return [
            "--download-archive", str(archive),
            "--no-overwrites",
            "--embed-metadata",
            "-o", out_tmpl,
            "--no-playlist",
            info.webpage_url,
        ]

    def audio_args(
        self,
        info: VideoInfo,
        source_format_id: str | None = None,
        audio_format: str = "mp3",
        quality: str | None = "320K",
    ) -> list[str]:
        """Sadece Ses indirme argümanları.

        source_format_id None ise 'bestaudio' (en iyi ham ses) kullanılır.
        audio_format 'orijinal' ise hiç dönüşüm yapılmaz.
        """
        args = ["-f", source_format_id or "bestaudio"]
        if audio_format and audio_format.lower() != "orijinal":
            args += ["-x", "--audio-format", audio_format]
            if quality and audio_format.lower() in ("mp3", "aac", "ogg"):
                args += ["--audio-quality", quality]
        if audio_format and audio_format.lower() in ("mp3", "m4a"):
            args += ["--embed-thumbnail"]
        return args + self._common_args(info)

    def video_args(self, info: VideoInfo, format_id: str) -> list[str]:
        """Sadece Video (sessiz) indirme argümanları — dönüştürme yok."""
        return ["-f", format_id] + self._common_args(info)

    def mux_args(self, info: VideoInfo, video_format_id: str, audio_format_id: str) -> list[str]:
        """Ses + Video: seçilen iki ham akışı ffmpeg ile kayıpsız birleştirir.

        Birleştirme stream-copy (yeniden kodlama yok) ile yapılır; kapsayıcı
        codec uyumuna göre mp4 / webm / mkv seçilir.
        """
        vf = info.get_format(video_format_id)
        af = info.get_format(audio_format_id)
        if vf is None or af is None:
            raise RuntimeError("Seçilen formatlar bulunamadı; lütfen tekrar sorgulayın.")
        container = choose_container(vf, af)
        return [
            "-f", f"{video_format_id}+{audio_format_id}",
            "--merge-output-format", container,
        ] + self._common_args(info)

    # ---------------------------------------------------------------- indirme

    def download(self, args: list[str], on_line=None) -> Path:
        """Hazırlanan argümanlarla indirir ve zaman damgalarını sabitler."""
        code = self.runner.run(args, on_line=on_line)
        if self.runner.cancelled:
            raise SingleCancelled()
        if code not in (0, 1):
            raise RuntimeError(f"yt-dlp hata kodu döndürdü: {code}")
        fix_timestamps_in_dir(self.single_folder())
        return self.single_folder()


def choose_container(video_fmt: FormatInfo, audio_fmt: FormatInfo) -> str:
    """Codec uyumuna göre kayıpsız birleştirme kapsayıcısını seçar.

    - H.264/H.265 + AAC  -> mp4
    - VP8/VP9/AV1 + Opus -> webm
    - diğer tüm kombinasyonlar -> mkv (her codec'i kabul eder)
    """
    v = (video_fmt.vcodec or "").lower()
    a = (audio_fmt.acodec or "").lower()

    mp4_video = any(c in v for c in ("avc1", "h264", "h265", "hevc"))
    mp4_audio = "mp4a" in a or "aac" in a
    webm_video = any(c in v for c in ("vp8", "vp9", "av01"))
    webm_audio = "opus" in a or "vorbis" in a

    if mp4_video and mp4_audio:
        return "mp4"
    if webm_video and webm_audio:
        return "webm"
    return "mkv"
