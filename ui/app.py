"""Ana pencere: sekmeli arayüz ve ortak durum yönetimi."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from core.config import ConfigStore
from core.runner import kill_all_active
from .bridge import UIBridge
from .settings_tab import SettingsTab
from .single_tab import SingleTab
from .sync_tab import SyncTab


class App:
    def __init__(self, root: tk.Tk, config: ConfigStore):
        self.root = root
        self.config = config
        self.bridge = UIBridge(root)

        root.title("YouTube Arşiv — Çalma Listesi Yedeği ve İndirici")
        root.geometry("1000x720")
        root.minsize(860, 600)

        # Pencere X ile kapatılırken arka plandaki yt-dlp/ffmpeg süreçlerini
        # de öldür: yoksa indirme exe kapansa bile arka planda sürer.
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=6, pady=6)

        self.sync_tab = SyncTab(notebook, config, self.bridge, self.get_runner_paths)
        notebook.add(self.sync_tab, text="  Çalma Listeleri  ")

        self.single_tab = SingleTab(notebook, config, self.bridge, self.get_runner_paths)
        notebook.add(self.single_tab, text="  Tekil İndir  ")

        self.settings_tab = SettingsTab(notebook, config, on_paths_changed=self._paths_changed)
        notebook.add(self.settings_tab, text="  Ayarlar  ")

        # Alt durum çubuğu
        self.statusbar = ttk.Label(
            root, text=self._status_text(), relief="sunken", anchor="w", padding=(6, 2),
        )
        self.statusbar.pack(side="bottom", fill="x")

    # ---------------------------------------------------------------- kapanma

    def _on_close(self) -> None:
        """X düğmesi: çalışan tüm indirmeleri durdur ve pencereyi kapat."""
        self.bridge.stop()
        try:
            kill_all_active()
        finally:
            self.root.destroy()

    # ---------------------------------------------------------------- ortak

    def get_runner_paths(self) -> tuple:
        """(yt_dlp_yolu, ffmpeg_yolu) — çözümlenmiş; çözülemezse hata verir."""
        ytdlp = self.config.resolve_tool("yt_dlp_path")
        ffmpeg = self.config.resolve_tool("ffmpeg_path")
        if ytdlp is None or ffmpeg is None:
            missing = []
            if ytdlp is None:
                missing.append("yt-dlp")
            if ffmpeg is None:
                missing.append("ffmpeg")
            raise RuntimeError(
                f"{' ve '.join(missing)} bulunamadı! "
                "Ayarlar sekmesinden yolunu güncelleyin."
            )
        return ytdlp, ffmpeg

    def _paths_changed(self) -> None:
        self.statusbar.config(text=self._status_text())

    def _status_text(self) -> str:
        ytdlp = self.config.resolve_tool("yt_dlp_path")
        ffmpeg = self.config.resolve_tool("ffmpeg_path")
        parts = []
        parts.append(f"yt-dlp: {ytdlp if ytdlp else 'BULUNAMADI'}")
        parts.append(f"ffmpeg: {ffmpeg if ffmpeg else 'BULUNAMADI'}")
        parts.append(f"İndirme: {self.config.download_root}")
        return "  |  ".join(str(p) for p in parts)
