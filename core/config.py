"""Yapılandırma: config.json yükleme/kaydetme, taşınabilir yol çözümleme.

Taşınabilirlik kuralları:
  - config.json her zaman uygulamanın çalıştırıldığı kök klasörde aranır/oluşturulur.
  - Kayıtlı yol göreliyse uygulama köküne göre çözülür.
  - Bulunamazsa uygulama kökü, tools/ alt klasörü ve PATH taranır.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def get_app_root() -> Path:
    """Uygulamanın kök klasörü (betik olarak çalışırken proje kökü,
    PyInstaller exe olarak çalışırken exe'nin klasörü)."""
    if getattr(sys, "frozen", False):  # PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = get_app_root()
CONFIG_PATH = APP_ROOT / "config.json"
TOOLS_DIR = APP_ROOT / "tools"

DEFAULT_CONFIG: dict = {
    "yt_dlp_path": "yt-dlp.exe",
    "ffmpeg_path": "ffmpeg.exe",
    "download_root": "",  # boşsa Müzik klasörü kullanılır
    "playlists": [],      # [{"id": ..., "title": ..., "added_at": ...}]
    "audio": {"format": "mp3", "quality": "320K"},
}


def get_music_folder() -> Path:
    """Windows standart Müzik klasörünü bulur (yerelleştirilmiş adlar dahil)."""
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Music {1BD126E5-79AE-4DBF-8DDB-1C77AC863A4C}
        folderid_music = _GUID(
            0x1BD126E5, 0x79AE, 0x4DBF,
            (ctypes.c_ubyte * 8)(0x8D, 0xDB, 0x1C, 0x77, 0xAC, 0x86, 0x3A, 0x4C),
        )

        shgfp = ctypes.windll.shell32.SHGetKnownFolderPath
        shgfp.argtypes = [
            ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        path_ptr = ctypes.c_wchar_p()
        if shgfp(ctypes.byref(folderid_music), 0, None, ctypes.byref(path_ptr)) == 0:
            path = Path(path_ptr.value)
            if path.exists():
                return path
    except Exception:
        pass
    return Path.home() / "Music"


def verify_tool(path: Path) -> str | None:
    """Aracın çalıştığını doğrular; başarılıysa sürüm bilgisini döndürür."""
    if not path or not Path(path).exists():
        return None
    is_ffmpeg = "ffmpeg" in Path(path).name.lower()
    try:
        out = subprocess.run(
            [str(path), "-version" if is_ffmpeg else "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    lines = (out.stdout or out.stderr or "").strip().splitlines()
    return lines[0] if lines else None


class ConfigStore:
    """config.json okuma/yazma ve yol çözümleme."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else CONFIG_PATH
        self.data: dict = {}

    # ---------------------------------------------------------------- yükle/kaydet

    def load(self) -> dict:
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}
        else:
            self.data = {}

        # Eksik anahtarları varsayılanlarla tamamla
        merged = dict(DEFAULT_CONFIG)
        if isinstance(self.data.get("audio"), dict):
            merged["audio"] = {**DEFAULT_CONFIG["audio"], **self.data["audio"]}
        for key, value in self.data.items():
            if key != "audio":
                merged[key] = value
        if not isinstance(merged.get("playlists"), list):
            merged["playlists"] = []
        if not merged.get("download_root"):
            merged["download_root"] = str(get_music_folder())
        self.data = merged
        return self.data

    def save(self) -> None:
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @property
    def exists(self) -> bool:
        return self.path.exists()

    # ---------------------------------------------------------------- yol çözümleme

    def resolve_tool(self, key: str) -> Path | None:
        """Config'deki araç yolunu taşınabilir kurallara göre çözer.

        Sıra: (1) config yolu (göreliyse uygulama köküne göre),
        (2) uygulama kökü ve tools/ alt klasörü,
        (3) sistem PATH'i.
        """
        raw = self.data.get(key) or ""
        default_name = "yt-dlp.exe" if "yt_dlp" in key else "ffmpeg.exe"

        if raw:
            p = Path(raw)
            candidate = p if p.is_absolute() else (APP_ROOT / p)
            if candidate.exists():
                return candidate

        name = Path(raw).name if raw else default_name
        for folder in (APP_ROOT, TOOLS_DIR):
            cand = folder / name
            if cand.exists():
                return cand

        which = shutil.which(name)
        if which:
            return Path(which)
        return None

    # ---------------------------------------------------------------- yardımcılar

    @property
    def download_root(self) -> Path:
        return Path(self.data.get("download_root") or get_music_folder())

    def find_playlist(self, playlist_id: str) -> dict | None:
        for entry in self.data.get("playlists", []):
            if entry.get("id") == playlist_id:
                return entry
        return None

    def add_playlist(self, playlist_id: str, title: str) -> dict:
        entry = self.find_playlist(playlist_id)
        if entry:
            entry["title"] = title
        else:
            from datetime import date

            entry = {
                "id": playlist_id,
                "title": title,
                "added_at": date.today().isoformat(),
            }
            self.data["playlists"].append(entry)
        self.save()
        return entry

    def remove_playlist(self, playlist_id: str) -> None:
        playlists = self.data.get("playlists", [])
        self.data["playlists"] = [p for p in playlists if p.get("id") != playlist_id]
        self.save()
