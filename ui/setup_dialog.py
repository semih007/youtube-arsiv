"""İlk kurulum sihirbazı: yt-dlp ve ffmpeg yolları + indirme klasörü.

İlk açılışta çalışır, doğrulama yapar ve config.json'a kaydeder.
Uygulama klasöründe yt-dlp.exe / ffmpeg.exe varsa otomatik algılanır.

Thread notu: Doğrulama alt süreçleri arka planda çalışır (GUI donmasın).
Sonuçlar kuyruk üzerinden ana thread'e aktarılır; worker thread'ler
asla doğrudan tkinter çağırmaz. (Diyalog wait_window ile açıkken
worker'dan after() çağrısı "main thread is not in main loop" hatası
fırlatır ve sessizce ölür — eski sürümdeki "Kaydet ve Başla çalışmıyor"
hatasının nedeni buydu.)
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core.config import APP_ROOT, TOOLS_DIR, verify_tool


class SetupDialog(tk.Toplevel):
    def __init__(self, root, config):
        super().__init__(root)
        self.config = config
        self.result = False  # True = kurulum tamamlandı

        # Worker thread'lerden ana thread'e olay aktarımı
        self._events: queue.Queue = queue.Queue()
        self._drain_alive = True

        self.title("YouTube Arşiv — İlk Kurulum")
        self.resizable(False, False)
        # NOT: transient(root) KULLANILMAZ — ana pencere withdraw() ile gizli
        # olduğundan transient diyalog da Windows'ta gizli kalır.
        self.grab_set()
        # Pencereyi öne getir
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))
        self.focus_force()

        # Ekranın ortasına yerleştir
        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"+{x}+{y}")

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Hoş geldiniz! İlk kez kullanıyorsunuz.\n"
                 "yt-dlp ve ffmpeg konumlarını gösterin; bir daha sorulmayacak.",
            justify="center",
        ).grid(row=0, column=0, columnspan=3, pady=(0, 12))

        # --- yt-dlp ---
        ttk.Label(frame, text="yt-dlp dosyası:").grid(row=1, column=0, sticky="w", pady=3)
        self.ytdlp_var = tk.StringVar(value=self._suggest("yt-dlp.exe"))
        ttk.Entry(frame, textvariable=self.ytdlp_var, width=55).grid(row=1, column=1, padx=6, pady=3)
        ttk.Button(frame, text="Gözat…", command=lambda: self._browse("yt-dlp")).grid(row=1, column=2, pady=3)
        self.ytdlp_status = ttk.Label(frame, text="", foreground="gray")
        self.ytdlp_status.grid(row=2, column=1, sticky="w")

        # --- ffmpeg ---
        ttk.Label(frame, text="ffmpeg dosyası:").grid(row=3, column=0, sticky="w", pady=3)
        self.ffmpeg_var = tk.StringVar(value=self._suggest("ffmpeg.exe"))
        ttk.Entry(frame, textvariable=self.ffmpeg_var, width=55).grid(row=3, column=1, padx=6, pady=3)
        ttk.Button(frame, text="Gözat…", command=lambda: self._browse("ffmpeg")).grid(row=3, column=2, pady=3)
        self.ffmpeg_status = ttk.Label(frame, text="", foreground="gray")
        self.ffmpeg_status.grid(row=4, column=1, sticky="w")

        ttk.Button(frame, text="Doğrula", command=self.verify_async).grid(row=5, column=1, pady=(4, 10), sticky="e")

        # --- indirme klasörü ---
        ttk.Label(frame, text="İndirme klasörü:").grid(row=6, column=0, sticky="w", pady=3)
        self.root_var = tk.StringVar(value=str(self.config.data.get("download_root") or ""))
        ttk.Entry(frame, textvariable=self.root_var, width=55).grid(row=6, column=1, padx=6, pady=3)
        ttk.Button(frame, text="Gözat…", command=self._browse_folder).grid(row=6, column=2, pady=3)
        ttk.Label(
            frame,
            text="Çalma listeleri bu klasörün altına, kendi adlarıyla iner.\n"
                 "Tekil indirmeler 'Tekil' alt klasörüne gider.",
            foreground="gray", justify="left",
        ).grid(row=7, column=1, sticky="w")

        # --- butonlar ---
        btns = ttk.Frame(frame)
        btns.grid(row=8, column=0, columnspan=3, pady=(14, 0))
        self.save_btn = ttk.Button(btns, text="Kaydet ve Başla", command=self._save)
        self.save_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="Çıkış", command=self._on_close).pack(side="left", padx=6)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Ana thread'de çalışan kuyruk işleyici (wait_window sırasında da işler)
        self.after(80, self._drain_events)

        # Algılanan yolları arka planda doğrula
        if self.ytdlp_var.get() or self.ffmpeg_var.get():
            self.after(150, self.verify_async)

    # ------------------------------------------------------------ yardımcılar

    def _suggest(self, exe_name: str) -> str:
        """Uygulama kökünde/tools'ta duran aracı otomatik öner."""
        for folder in (APP_ROOT, TOOLS_DIR):
            cand = folder / exe_name
            if cand.exists():
                return str(cand)
        return ""

    def _browse(self, tool: str) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title=f"{tool} dosyasını seçin",
            filetypes=[(f"{tool}", "*.exe"), ("Tüm dosyalar", "*.*")],
        )
        if path:
            (self.ytdlp_var if tool == "yt-dlp" else self.ffmpeg_var).set(path)
            self.verify_async()

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(parent=self, title="İndirme klasörünü seçin")
        if path:
            self.root_var.set(path)

    def _on_close(self) -> None:
        """X veya Çıkış: diyaloğu kapat (kurulum tamamlanmadı)."""
        self._drain_alive = False
        self.destroy()

    # ------------------------------------------------------------ doğrulama

    def verify_async(self) -> None:
        """Doğrula: araçları arka planda çalıştırır (GUI donmaz).

        Gösterilen konumdaki dosyayı gerçekten çalıştırır
        (yt-dlp --version / ffmpeg -version) ve sürüm bilgisini gösterir.
        """
        self.ytdlp_status.config(text="Doğrulanıyor…", foreground="gray")
        self.ffmpeg_status.config(text="Doğrulanıyor…", foreground="gray")
        threading.Thread(
            target=self._verify_worker,
            args=("ytdlp", self.ytdlp_var.get().strip()),
            daemon=True,
        ).start()
        threading.Thread(
            target=self._verify_worker,
            args=("ffmpeg", self.ffmpeg_var.get().strip()),
            daemon=True,
        ).start()

    def _verify_worker(self, key: str, path: str) -> None:
        """Worker thread: alt süreci çalıştırır, sonucu kuyruğa koyar."""
        version = verify_tool(path) if path else None
        self._events.put({"type": "verify", "key": key, "version": version, "empty": not path})

    # ------------------------------------------------------------ kaydetme

    def _save(self) -> None:
        """Kaydet ve Başla: doğrulamayı arka planda yapıp kaydeder."""
        ytdlp = self.ytdlp_var.get().strip()
        ffmpeg = self.ffmpeg_var.get().strip()
        if not ytdlp or not ffmpeg:
            messagebox.showwarning("Eksik bilgi", "yt-dlp ve ffmpeg yollarını gösterin.", parent=self)
            return
        # Butonu kilitle: kullanıcıya 'çalışıyor' geri bildirimi ver
        self.save_btn.config(state="disabled", text="Doğrulanıyor…")
        threading.Thread(target=self._save_worker, args=(ytdlp, ffmpeg), daemon=True).start()

    def _save_worker(self, ytdlp: str, ffmpeg: str) -> None:
        """Worker thread: her iki aracı doğrular, sonucu kuyruğa koyar."""
        results = {"ytdlp": verify_tool(ytdlp), "ffmpeg": verify_tool(ffmpeg)}
        self._events.put({"type": "save_done", "ytdlp": ytdlp, "ffmpeg": ffmpeg, "results": results})

    def _finish_save(self, ytdlp: str, ffmpeg: str, results: dict) -> None:
        """Ana thread: doğrulama sonuçlarına göre kaydeder ve kapatır."""
        if not results.get("ytdlp") or not results.get("ffmpeg"):
            bad = []
            if not results.get("ytdlp"):
                bad.append("yt-dlp")
            if not results.get("ffmpeg"):
                bad.append("ffmpeg")
            if not messagebox.askyesno(
                "Doğrulanamadı",
                f"{' ve '.join(bad)} çalıştırılamadı.\n"
                "Yine de bu yollarla kaydetmek istiyor musunuz?",
                parent=self,
            ):
                self.save_btn.config(state="normal", text="Kaydet ve Başla")
                return
        root_path = self.root_var.get().strip()
        self.config.data["yt_dlp_path"] = ytdlp
        self.config.data["ffmpeg_path"] = ffmpeg
        if root_path:
            self.config.data["download_root"] = root_path
        self.config.save()
        self.result = True
        self._drain_alive = False
        self.destroy()

    # ------------------------------------------------------------ olay kuyruğu

    def _drain_events(self) -> None:
        """Ana thread: worker sonuçlarını UI'ya uygular (80 ms'de bir)."""
        if not self._drain_alive:
            return
        try:
            while True:
                try:
                    event = self._events.get_nowait()
                except queue.Empty:
                    break
                self._handle_event(event)
        except tk.TclError:
            # pencere çoktan kapatılmış olabilir
            self._drain_alive = False
            return
        if self._drain_alive:
            self.after(80, self._drain_events)

    def _handle_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "verify":
            label = self.ytdlp_status if event["key"] == "ytdlp" else self.ffmpeg_status
            if event.get("empty"):
                label.config(text="Dosya seçilmedi.", foreground="gray")
            elif event.get("version"):
                label.config(text=f"✓ {event['version']}", foreground="#0a7d0a")
            else:
                label.config(text="✗ Çalıştırılamadı — yolu kontrol edin.", foreground="#c02020")
        elif kind == "save_done":
            self._finish_save(event["ytdlp"], event["ffmpeg"], event["results"])


def run_first_time_setup(root, config) -> bool:
    """İlk kurulum diyaloğunu açar. True = kurulum tamamlandı."""
    dialog = SetupDialog(root, config)
    root.wait_window(dialog)
    return dialog.result
