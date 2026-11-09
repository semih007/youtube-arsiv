"""Çalma Listeleri sekmesi: kayıtlı listeler + 'Tümünü Senkronize Et'."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from core.config import ConfigStore
from core.runner import Runner, parse_line
from core.sync import SyncEngine, SyncCancelled
from .bridge import UIBridge


class SyncTab(ttk.Frame):
    def __init__(self, parent, config: ConfigStore, bridge: UIBridge, get_runner_paths):
        """get_runner_paths: () -> (yt_dlp_path, ffmpeg_path) çağrısı."""
        super().__init__(parent, padding=10)
        self.config = config
        self.bridge = bridge
        self.get_runner_paths = get_runner_paths
        self._worker: threading.Thread | None = None
        self._current_runner: Runner | None = None

        self._build()
        self.refresh_list()

    # ---------------------------------------------------------------- arayüz

    def _build(self) -> None:
        # Araç çubuğu
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 8))
        self.add_btn = ttk.Button(toolbar, text="＋ Çalma Listesi Ekle", command=self.add_playlist)
        self.add_btn.pack(side="left")
        self.remove_btn = ttk.Button(toolbar, text="－ Kaldır", command=self.remove_playlist)
        self.remove_btn.pack(side="left", padx=(8, 0))
        self.sync_btn = ttk.Button(toolbar, text="⟳ Tümünü Senkronize Et", command=self.sync_all)
        self.sync_btn.pack(side="left", padx=(16, 0))
        self.cancel_btn = ttk.Button(toolbar, text="■ İptal", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="right")

        # Liste
        columns = ("baslik", "id")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=8)
        self.tree.heading("baslik", text="Çalma Listesi")
        self.tree.heading("id", text="Playlist ID")
        self.tree.column("baslik", width=420, anchor="w")
        self.tree.column("id", width=260, anchor="w")
        self.tree.pack(fill="both", expand=True)

        # İlerleme
        progress_frame = ttk.Frame(self)
        progress_frame.pack(fill="x", pady=(8, 0))
        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.status_label = ttk.Label(progress_frame, text="Hazır", width=52, anchor="w")
        self.status_label.pack(side="left", padx=(8, 0))

        # Günlük
        self.log_text = tk.Text(self, height=8, state="disabled", wrap="none")
        self.log_text.pack(fill="both", expand=True, pady=(8, 0))

        self.bridge.on_event(self._on_event)

    def refresh_list(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for entry in self.config.data.get("playlists", []):
            self.tree.insert("", "end", values=(entry.get("title", ""), entry.get("id", "")))

    def log(self, text: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.add_btn.config(state=state)
        self.remove_btn.config(state=state)
        self.sync_btn.config(state=state)
        self.cancel_btn.config(state="normal" if busy else "disabled")
        if not busy:
            self.progress_bar.config(value=0)
            self.status_label.config(text="Hazır")

    # ------------------------------------------------------------ olay işleme

    def _on_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "log":
            self.log(event["text"])
        elif kind == "progress":
            if event.get("percent") is not None:
                self.progress_bar.config(value=event["percent"])
            if event.get("status"):
                self.status_label.config(text=event["status"])
        elif kind == "state":
            if event.get("busy"):
                self._set_busy(True)
                if event.get("status"):
                    self.status_label.config(text=event["status"])
            else:
                self.refresh_list()
                self._set_busy(False)
                if event.get("status"):
                    self.status_label.config(text=event["status"])

    # ------------------------------------------------------------ ekleme / kaldırma

    def add_playlist(self) -> None:
        from core.parser import ParseError, parse

        url = simpledialog.askstring(
            "Çalma Listesi Ekle",
            "Çalma listesi bağlantısını yapıştırın:\n"
            "ör. https://www.youtube.com/playlist?list=PLxxxx",
            parent=self,
        )
        if not url:
            return
        try:
            target = parse(url)
        except ParseError as exc:
            messagebox.showerror("Geçersiz bağlantı", str(exc), parent=self)
            return
        if not target.playlist_id:
            messagebox.showwarning(
                "Playlist bulunamadı",
                "Girdide çalma listesi ID'si yok.\n"
                "Bağlantıda 'list=' parametresi bulunmalı.",
                parent=self,
            )
            return
        playlist_id = target.playlist_id
        if self.config.find_playlist(playlist_id):
            messagebox.showinfo("Zaten kayıtlı", "Bu çalma listesi zaten ekli.", parent=self)
            return

        self._set_busy(True)
        self.status_label.config(text="Liste bilgisi alınıyor…")

        def work():
            try:
                ytdlp, ffmpeg = self.get_runner_paths()
                runner = Runner(ytdlp, ffmpeg)
                engine = SyncEngine(self.config, runner)
                entry = engine.add_from_url(playlist_id)
                self.bridge.log(f"✓ Eklendi: {entry['title']} ({playlist_id})")
            except Exception as exc:
                self.bridge.log(f"✗ Eklenemedi: {exc}")
            finally:
                self.bridge.state(busy=False, status="Hazır")

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def remove_playlist(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Seçim yok", "Önce listeden bir çalma listesi seçin.", parent=self)
            return
        values = self.tree.item(selection[0], "values")
        title, playlist_id = values[0], values[1]
        if not messagebox.askyesno(
            "Kaldır",
            f"'{title}' listesi kayıtlardan kaldırılsın mı?\n"
            "İndirilmiş dosyalar diskte kalır.",
            parent=self,
        ):
            return
        self.config.remove_playlist(playlist_id)
        self.refresh_list()

    # ------------------------------------------------------------ senkronizasyon

    def sync_all(self) -> None:
        playlists = self.config.data.get("playlists", [])
        if not playlists:
            messagebox.showinfo("Liste boş", "Önce bir çalma listesi ekleyin.", parent=self)
            return
        self._set_busy(True)
        self.bridge.state(busy=True, status="Senkronizasyon başlıyor…")
        self.log("— Tümünü Senkronize Et —")

        def work():
            try:
                ytdlp, ffmpeg = self.get_runner_paths()
                runner = Runner(ytdlp, ffmpeg)
                self._current_runner = runner
                engine = SyncEngine(self.config, runner)
                ok_count = 0
                for index, entry in enumerate(playlists, start=1):
                    playlist_id = entry["id"]
                    title = entry.get("title", playlist_id)
                    if runner.cancelled:
                        break
                    self.bridge.log(f"[{index}/{len(playlists)}] {title}")
                    self.bridge.progress(status=f"[{index}/{len(playlists)}] {title}")
                    try:
                        # YouTube'daki güncel ada göre klasörü güncelle
                        current_title = engine.fetch_title(playlist_id)
                        engine.update_folder(playlist_id, current_title)
                        engine.sync_playlist(playlist_id, on_line=self._make_line_handler(title))
                        ok_count += 1
                    except SyncCancelled:
                        self.bridge.log("■ İptal edildi")
                        break
                    except Exception as exc:
                        self.bridge.log(f"✗ Hata: {exc}")
                else:
                    self.bridge.log(f"✓ Senkronizasyon tamamlandı ({ok_count}/{len(playlists)} liste)")
                    self.bridge.state(busy=False, status=f"Tamamlandı ({ok_count}/{len(playlists)})")
                    return
                self.bridge.state(busy=False, status="İptal edildi")
            except Exception as exc:
                self.bridge.log(f"✗ Beklenmeyen hata: {exc}")
                self.bridge.state(busy=False, status="Hata")
            finally:
                self._current_runner = None

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _make_line_handler(self, playlist_title: str):
        """yt-dlp çıktı satırlarını GUI olaylarına çevirir."""

        def handle(line: str) -> None:
            info = parse_line(line)
            # Sadece önemli satırları günlüğe yaz
            if (
                info.get("destination")
                or info.get("archived")
                or info.get("error")
                or info.get("warning")
                or "ExtractAudio" in line
                or "Deleting original" in line
            ):
                self.bridge.log(line)
            parts = []
            if "item" in info:
                parts.append(f"{info['item']}/{info['total']}")
            if "percent" in info:
                parts.append(f"%{info['percent']:.0f}")
            if parts:
                self.bridge.progress(
                    percent=info.get("percent"),
                    status=f"{playlist_title} — {' • '.join(parts)}",
                )

        return handle

    def cancel(self) -> None:
        if self._current_runner:
            self._current_runner.cancel()
            self.status_label.config(text="İptal ediliyor…")
