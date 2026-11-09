"""Çalma listesi senkronizasyon motoru.

- Her çalma listesi, YouTube'daki orijinal adıyla Müzik klasörü altında bir
  klasöre sahip olur; takip her zaman Playlist ID üzerinden yürür.
- Her klasörde kendine ait 'indirilenler.txt' arşivi tutulur; arşivdeki
  videolar kesinlikle tekrar indirilmez.
- Standart: en iyi ses kalitesi -> MP3 320 kbps, gömülü metadata + kapak.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import ConfigStore
from .parser import playlist_url
from .runner import Runner, parse_line
from .timestamps import fix_timestamps_in_dir
from .utils import sanitize_filename

ARCHIVE_NAME = "indirilenler.txt"

# Dosya adındaki 'NN - ' numara öneki
INDEX_RE = re.compile(r"^(\d+) - ")


class SyncCancelled(Exception):
    """Kullanıcı senkronizasyonu iptal etti."""


def _archive_ids(path: Path) -> list[str]:
    """Arşiv dosyasındaki video id'lerini kayıt sırasıyla döndürür."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [line.split()[-1] for line in text.splitlines() if line.strip()]


def renumber_new_files(folder: Path, new_ids: list[str]) -> list[Path]:
    """Yeni inen dosyaları 'NN - ' numaralandırmasına alır.

    Numara, klasördeki mevcut en büyük NN'den devam eder (256, 257, ...) —
    playliste sonradan eklenen şarkılar %(playlist_index) yerine bu sırayı
    alır. Dosyalar '<başlık> [<id>].<uzantı>' şablonuyla indiği için [id]
    eki üzerinden eşleştirilir; sonuç 'NN - <başlık>.<uzantı>' olur.
    """
    renamed: list[Path] = []
    if not new_ids or not folder.exists():
        return renamed

    files = [p for p in folder.iterdir() if p.is_file()]
    max_idx = 0
    for p in files:
        m = INDEX_RE.match(p.name)
        if m:
            max_idx = max(max_idx, int(m.group(1)))

    for video_id in new_ids:
        tag = f"[{video_id}]"
        src = next((p for p in files if tag in p.stem), None)
        if src is None:
            continue  # dosya yok (dönüştürme hatası vb.) — atla
        title = src.stem
        if title.endswith(tag):
            title = title[: -len(tag)].rstrip()
        max_idx += 1
        dest = folder / f"{max_idx:02d} - {title}{src.suffix}"
        src.rename(dest)
        renamed.append(dest)
    return renamed


class SyncEngine:
    """Kayıtlı çalma listelerini yönetir ve senkronize eder."""

    def __init__(self, config: ConfigStore, runner: Runner):
        self.config = config
        self.runner = runner

    # ---------------------------------------------------------------- sorgu

    def fetch_title(self, playlist_id: str, timeout: int = 180) -> str:
        """Çalma listesinin YouTube'daki güncel adını çeker.

        Yalnızca liste üst verisi istenir (--flat-playlist, tek giriş);
        böylece sorgu hızlı olur ve video indirilmez.
        """
        proc = self.runner.run_capture(
            ["--flat-playlist", "--playlist-items", "1:1", "-J", playlist_url(playlist_id)],
            timeout=timeout,
        )
        if proc.returncode != 0:
            # Boş liste gibi durumlarda tek-giriş sınırı hataya düşebilir;
            # o durumda kısıt olmadan (yalnızca üst veri) tekrar dene
            proc = self.runner.run_capture(
                ["--flat-playlist", "-J", playlist_url(playlist_id)],
                timeout=timeout,
            )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip().splitlines()
            msg = next((l for l in err if "ERROR" in l), err[0] if err else "bilinmeyen hata")
            raise RuntimeError(f"Çalma listesi bilgisi alınamadı:\n{msg}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Çalma listesi yanıtı çözümlenemedi: {exc}") from exc
        return data.get("title") or playlist_id

    # ---------------------------------------------------------------- klasör yönetimi

    def playlist_folder(self, entry: dict) -> Path:
        return self.config.download_root / sanitize_filename(entry.get("title") or entry["id"])

    def archive_path(self, folder: Path) -> Path:
        return folder / ARCHIVE_NAME

    def update_folder(self, playlist_id: str, current_title: str) -> dict:
        """Klasörü güncel YouTube adına göre oluşturur/günceller.

        Liste YouTube'da yeniden adlandırıldıysa eski klasör (arşivi ve
        dosyalarıyla birlikte) yeni ada taşınır. Config kaydı güncellenir.
        """
        entry = self.config.find_playlist(playlist_id)
        if entry is None:
            entry = self.config.add_playlist(playlist_id, current_title)

        root = self.config.download_root
        old_folder = self.playlist_folder(entry)
        new_folder = root / sanitize_filename(current_title)

        if old_folder != new_folder and old_folder.exists():
            if not new_folder.exists():
                old_folder.rename(new_folder)
            else:
                # Hedef klasör zaten varsa: arşivi birleştir, dosyaları taşı
                old_archive = self.archive_path(old_folder)
                new_archive = self.archive_path(new_folder)
                if old_archive.exists():
                    existing = new_archive.read_text(encoding="utf-8") if new_archive.exists() else ""
                    new_archive.write_text(
                        existing + old_archive.read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )
                for item in old_folder.iterdir():
                    if not (new_folder / item.name).exists():
                        try:
                            item.rename(new_folder / item.name)
                        except OSError:
                            pass
                try:
                    old_folder.rmdir()
                except OSError:
                    pass

        entry["title"] = current_title
        self.config.save()
        new_folder.mkdir(parents=True, exist_ok=True)
        return entry

    # ---------------------------------------------------------------- senkronizasyon

    def sync_playlist(self, playlist_id: str, on_line=None, extra_args: list[str] | None = None) -> Path:
        """Tek bir çalma listesini senkronize eder. Klasör yolunu döndürür.

        extra_args: yt-dlp'ye ek argümanlar (yalnızca test için; normalde None).
        """
        entry = self.config.find_playlist(playlist_id)
        if entry is None:
            raise RuntimeError(f"Çalma listesi kayıtlı değil: {playlist_id}")

        folder = self.playlist_folder(entry)
        folder.mkdir(parents=True, exist_ok=True)
        archive = self.archive_path(folder)
        # [id] eki: aynı başlıklı iki video dosya çakışması yapmasın ve
        # yeni inen dosyalar video id'siyle eşlenebilsin (aşağıda
        # renumber_new_files 'NN - ' şemasına çevirir).
        out_tmpl = str(folder / "%(title)s [%(id)s].%(ext)s")

        args = [
            "-f", "bestaudio",  # her zaman en iyi ham ses akışı
            "-x", "--audio-format", "mp3", "--audio-quality", "320K",
            "--embed-metadata",
            "--embed-thumbnail",
            "--download-archive", str(archive),
            "--ignore-errors",  # silinmiş/uluslararası kısıtlı video diğerlerini bloklamasın
            "--no-overwrites",
            "-o", out_tmpl,
            playlist_url(playlist_id),
        ]
        if extra_args:
            args = args[:-1] + list(extra_args) + [args[-1]]
        ids_before = set(_archive_ids(archive))
        code = self.runner.run(args, on_line=on_line)
        if self.runner.cancelled:
            raise SyncCancelled()

        # Yeni inenler: mevcut en büyük numaradan devam ederek numaralandır
        new_ids = [i for i in _archive_ids(archive) if i not in ids_before]
        renumber_new_files(folder, new_ids)

        # Yeni inen dosyaların zaman damgalarını sabitle
        fixed = fix_timestamps_in_dir(folder)

        # --ignore-errors bazı sorunlu videolarda 0 dönmeyebilir; bu normal
        if code not in (0, 1):
            raise RuntimeError(f"yt-dlp hata kodu döndürdü: {code}")
        return folder

    def sync_all(self, on_line=None, on_playlist_start=None) -> list[Path]:
        """Kayıtlı tüm çalma listelerini sırayla senkronize eder."""
        folders: list[Path] = []
        entries = list(self.config.data.get("playlists", []))
        for entry in entries:
            if self.runner.cancelled:
                break
            playlist_id = entry["id"]
            if on_playlist_start:
                on_playlist_start(entry)
            try:
                folders.append(self.sync_playlist(playlist_id, on_line=on_line))
            except SyncCancelled:
                break
        return folders

    # ---------------------------------------------------------------- ekleme

    def add_from_url(self, playlist_id: str) -> dict:
        """URL'den ayıklanan ID'yi kaydeder; başlığı YouTube'dan çeker."""
        title = self.fetch_title(playlist_id)
        return self.config.add_playlist(playlist_id, title)
