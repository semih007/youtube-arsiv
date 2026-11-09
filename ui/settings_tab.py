"""Ayarlar sekmesi: yt-dlp / ffmpeg yolları ve indirme klasörü."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.config import ConfigStore, verify_tool


class SettingsTab(ttk.Frame):
    def __init__(self, parent, config: ConfigStore, on_paths_changed):
        super().__init__(parent, padding=12)
        self.config = config
        self.on_paths_changed = on_paths_changed

        frame = ttk.Frame(self)
        frame.pack(fill="x")

        # yt-dlp
        ttk.Label(frame, text="yt-dlp dosyası:").grid(row=0, column=0, sticky="w", pady=4)
        self.ytdlp_var = tk.StringVar(value=str(self.config.data.get("yt_dlp_path", "")))
        ttk.Entry(frame, textvariable=self.ytdlp_var, width=60).grid(row=0, column=1, padx=6, pady=4)
        ttk.Button(frame, text="Gözat…", command=lambda: self._browse_exe(self.ytdlp_var)).grid(row=0, column=2)

        # ffmpeg
        ttk.Label(frame, text="ffmpeg dosyası:").grid(row=1, column=0, sticky="w", pady=4)
        self.ffmpeg_var = tk.StringVar(value=str(self.config.data.get("ffmpeg_path", "")))
        ttk.Entry(frame, textvariable=self.ffmpeg_var, width=60).grid(row=1, column=1, padx=6, pady=4)
        ttk.Button(frame, text="Gözat…", command=lambda: self._browse_exe(self.ffmpeg_var)).grid(row=1, column=2)

        # indirme kökü
        ttk.Label(frame, text="İndirme klasörü:").grid(row=2, column=0, sticky="w", pady=4)
        self.root_var = tk.StringVar(value=str(self.config.data.get("download_root", "")))
        ttk.Entry(frame, textvariable=self.root_var, width=60).grid(row=2, column=1, padx=6, pady=4)
        ttk.Button(frame, text="Gözat…", command=self._browse_folder).grid(row=2, column=2)

        # Doğrula + Kaydet
        ttk.Button(frame, text="Doğrula", command=self._verify).grid(row=3, column=1, sticky="e", pady=(6, 0))
        ttk.Button(frame, text="Kaydet", command=self._save).grid(row=3, column=2, pady=(6, 0))

        self.verify_label = ttk.Label(self, text="", foreground="gray", justify="left")
        self.verify_label.pack(anchor="w", pady=(10, 0))

        ttk.Label(
            self,
            text="Not: config.json uygulama klasöründe tutulur; klasör taşındığında\n"
                 "ayarlar korunur. yt-dlp/ffmpeg uygulama klasöründeyse yolları göreli\n"
                 "girin (ör. yt-dlp.exe) — böylece her makinede otomatik bulunur.",
            foreground="gray", justify="left",
        ).pack(anchor="w", pady=(14, 0))

    # ----------------------------------------------------------------

    def _browse_exe(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            parent=self, filetypes=[("Çalıştırılabilir", "*.exe"), ("Tüm dosyalar", "*.*")],
        )
        if path:
            var.set(path)

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(parent=self)
        if path:
            self.root_var.set(path)

    def _verify(self) -> None:
        """Doğrulamayı arka planda çalıştırır (GUI donmasın).

        Sonuç, ana thread'de after ile yoklanarak alınır; worker thread
        tkinter'a asla dokunmaz.
        """
        paths = {
            "yt-dlp": self.ytdlp_var.get().strip(),
            "ffmpeg": self.ffmpeg_var.get().strip(),
        }
        self.verify_label.config(text="Doğrulanıyor…", foreground="gray")
        result: dict = {}

        def work():
            for name, path in paths.items():
                result[name] = verify_tool(path) if path else None

        t = threading.Thread(target=work, daemon=True)
        t.start()

        def poll():
            if t.is_alive():
                self.after(100, poll)
                return
            lines = []
            for name in ("yt-dlp", "ffmpeg"):
                version = result.get(name)
                if version:
                    lines.append(f"✓ {name}: {version}")
                elif paths[name]:
                    lines.append(f"✗ {name}: çalıştırılamadı")
                else:
                    lines.append(f"✗ {name}: dosya seçilmedi")
            self.verify_label.config(text="\n".join(lines))

        self.after(100, poll)

    def _save(self) -> None:
        self.config.data["yt_dlp_path"] = self.ytdlp_var.get().strip()
        self.config.data["ffmpeg_path"] = self.ffmpeg_var.get().strip()
        root = self.root_var.get().strip()
        if root:
            self.config.data["download_root"] = root
        self.config.save()
        messagebox.showinfo("Kaydedildi", "Ayarlar kaydedildi.", parent=self)
        if self.on_paths_changed:
            self.on_paths_changed()
