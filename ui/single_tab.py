"""Tekil İndir sekmesi: URL sorgula -> format seç -> indir.

Üç mod: Sadece Ses / Sadece Video (sessiz) / Ses + Video (kayıpsız mux).
İndirme yeri: <Müzik>\\Tekil\\ — arşiv sayesinde aynı video ikinci kez inmez.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from core.config import ConfigStore
from core.formats import VideoInfo
from core.parser import ParseError, parse, video_url
from core.runner import Runner, parse_line
from core.single import AUDIO_FORMATS, AUDIO_QUALITIES, SingleCancelled, SingleDownloader
from .bridge import UIBridge

MODE_AUDIO = "audio"
MODE_VIDEO = "video"
MODE_MUX = "mux"

MODE_LABELS = {
    MODE_AUDIO: "Sadece Ses",
    MODE_VIDEO: "Sadece Video (sessiz)",
    MODE_MUX: "Ses + Video (birleşik)",
}


class SingleTab(ttk.Frame):
    def __init__(self, parent, config: ConfigStore, bridge: UIBridge, get_runner_paths):
        super().__init__(parent, padding=10)
        self.config = config
        self.bridge = bridge
        self.get_runner_paths = get_runner_paths
        self.info: VideoInfo | None = None
        self._worker: threading.Thread | None = None
        self._current_runner: Runner | None = None
        self.mode = tk.StringVar(value=MODE_AUDIO)
        self.audio_format = tk.StringVar(value="mp3")
        self.audio_quality = tk.StringVar(value="320K")

        self._build()
        self.bridge.on_event(self._on_event)
        self._on_mode_changed()

    # ---------------------------------------------------------------- arayüz

    def _build(self) -> None:
        # URL satırı
        url_frame = ttk.Frame(self)
        url_frame.pack(fill="x")
        ttk.Label(url_frame, text="Bağlantı:").pack(side="left")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.url_entry.bind("<Return>", lambda e: self.query())
        self.query_btn = ttk.Button(url_frame, text="Sorgula", command=self.query)
        self.query_btn.pack(side="left")

        # Video bilgisi
        info_frame = ttk.LabelFrame(self, text="Video Bilgisi", padding=8)
        info_frame.pack(fill="x", pady=(8, 6))
        self.info_label = ttk.Label(info_frame, text="Bağlantıyı yapıştırıp 'Sorgula'ya basın.", foreground="gray")
        self.info_label.pack(anchor="w")

        # Mod seçimi
        self.mode_frame = ttk.LabelFrame(self, text="İndirme Türü", padding=8)
        self.mode_frame.pack(fill="x", pady=(0, 6))
        for value, label in MODE_LABELS.items():
            ttk.Radiobutton(
                self.mode_frame, text=label, value=value, variable=self.mode,
                command=self._on_mode_changed,
            ).pack(side="left", padx=(0, 18))

        # Ses ayarları (yalnızca ses modunda görünür)
        self.audio_frame = ttk.LabelFrame(self, text="Ses Ayarları", padding=8)
        self.audio_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(self.audio_frame, text="Hedef format:").grid(row=0, column=0, sticky="w")
        self.audio_format_combo = ttk.Combobox(
            self.audio_frame, textvariable=self.audio_format,
            values=AUDIO_FORMATS + ["orijinal"], state="readonly", width=12,
        )
        self.audio_format_combo.grid(row=0, column=1, padx=(6, 16))
        ttk.Label(self.audio_frame, text="Kalite:").grid(row=0, column=2, sticky="w")
        self.audio_quality_combo = ttk.Combobox(
            self.audio_frame, textvariable=self.audio_quality,
            values=AUDIO_QUALITIES, state="readonly", width=8,
        )
        self.audio_quality_combo.grid(row=0, column=3, padx=6)
        ttk.Label(
            self.audio_frame,
            text="Kaynak akış seçilmezse en iyi ham ses kullanılır. 'orijinal' = dönüşümsüz.\n"
                 "Not: YouTube'da gerçek FLAC yoktur; FLAC seçimi lossy kaynağın transkodudur.",
            foreground="gray", justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))

        # Format listeleri
        trees_frame = ttk.Frame(self)
        trees_frame.pack(fill="both", expand=True)
        columns = ("id", "uzanti", "kalite", "codec", "bitrate", "boyut")
        headings = ("ID", "Uzantı", "Kalite", "Codec", "Bitrate", "Boyut")

        audio_side = ttk.LabelFrame(trees_frame, text="Ses Akışları", padding=4)
        audio_side.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.audio_tree = ttk.Treeview(audio_side, columns=columns, show="headings", height=7)
        for col, head in zip(columns, headings):
            self.audio_tree.heading(col, text=head)
        self.audio_tree.column("id", width=60, anchor="w")
        self.audio_tree.column("uzanti", width=55, anchor="w")
        self.audio_tree.column("kalite", width=110, anchor="w")
        self.audio_tree.column("codec", width=90, anchor="w")
        self.audio_tree.column("bitrate", width=70, anchor="w")
        self.audio_tree.column("boyut", width=70, anchor="w")
        audio_scroll = ttk.Scrollbar(audio_side, orient="vertical", command=self.audio_tree.yview)
        self.audio_tree.configure(yscrollcommand=audio_scroll.set)
        self.audio_tree.pack(side="left", fill="both", expand=True)
        audio_scroll.pack(side="left", fill="y")
        self.audio_tree.bind("<<TreeviewSelect>>", lambda e: self._clear_selection(self.video_tree))

        video_side = ttk.LabelFrame(trees_frame, text="Video Akışları", padding=4)
        video_side.pack(side="left", fill="both", expand=True, padx=(4, 0))
        self.video_tree = ttk.Treeview(video_side, columns=columns, show="headings", height=7)
        for col, head in zip(columns, headings):
            self.video_tree.heading(col, text=head)
        self.video_tree.column("id", width=60, anchor="w")
        self.video_tree.column("uzanti", width=55, anchor="w")
        self.video_tree.column("kalite", width=130, anchor="w")
        self.video_tree.column("codec", width=90, anchor="w")
        self.video_tree.column("bitrate", width=70, anchor="w")
        self.video_tree.column("boyut", width=70, anchor="w")
        video_scroll = ttk.Scrollbar(video_side, orient="vertical", command=self.video_tree.yview)
        self.video_tree.configure(yscrollcommand=video_scroll.set)
        self.video_tree.pack(side="left", fill="both", expand=True)
        video_scroll.pack(side="left", fill="y")
        self.video_tree.bind("<<TreeviewSelect>>", lambda e: self._clear_selection(self.audio_tree))

        ttk.Label(
            self,
            text="Kaynak akış seçmek isteğe bağlıdır: seçilmezse en iyi kalite kullanılır. "
                 "'Ses + Video' modunda ayrıca birer ses ve video akışı seçin.",
            foreground="gray",
        ).pack(anchor="w", pady=(4, 0))

        # İlerleme + günlük
        progress_frame = ttk.Frame(self)
        progress_frame.pack(fill="x", pady=(8, 0))
        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.status_label = ttk.Label(progress_frame, text="Hazır", width=46, anchor="w")
        self.status_label.pack(side="left", padx=(8, 0))

        self.log_text = tk.Text(self, height=6, state="disabled", wrap="none")
        self.log_text.pack(fill="both", expand=True, pady=(8, 0))

        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(8, 0))
        self.download_btn = ttk.Button(btns, text="⤓ İndir", command=self.download, state="disabled")
        self.download_btn.pack(side="left")
        self.cancel_btn = ttk.Button(btns, text="■ İptal", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))

    # ---------------------------------------------------------------- mod yönetimi

    def _on_mode_changed(self) -> None:
        if self.mode.get() == MODE_AUDIO:
            # Ses ayarlarını 'İndirme Türü' çerçevesinin hemen altında tut
            self.audio_frame.pack(fill="x", pady=(0, 6), after=self.mode_frame)
        else:
            self.audio_frame.pack_forget()
        self._update_hint()

    def _update_hint(self) -> None:
        mode = self.mode.get()
        hint = {
            MODE_AUDIO: "Seçim: ses akışı (isteğe bağlı) + hedef format/kalite.",
            MODE_VIDEO: "Seçim: bir video akışı — ses içermez, dönüştürme yapılmaz.",
            MODE_MUX: "Seçim: bir video + bir ses akışı — ffmpeg ile kayıpsız birleştirilir.",
        }[mode]
        self.status_label.config(text=hint)

    # ------------------------------------------------------------ olay işleme

    def _on_event(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "info":
            self._show_info(event["info"])
        elif kind == "log":
            self.log_text.config(state="normal")
            self.log_text.insert("end", event["text"] + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        elif kind == "progress":
            if event.get("percent") is not None:
                self.progress_bar.config(value=event["percent"])
            if event.get("status"):
                self.status_label.config(text=event["status"])
        elif kind == "state":
            busy = event.get("busy")
            self.query_btn.config(state="disabled" if busy else "normal")
            self.download_btn.config(
                state="disabled" if busy or self.info is None else "normal"
            )
            self.cancel_btn.config(state="normal" if busy else "disabled")
            if not busy:
                self.progress_bar.config(value=0)
                if event.get("status"):
                    self.status_label.config(text=event["status"])

    def _set_busy(self, busy: bool) -> None:
        self.query_btn.config(state="disabled" if busy else "normal")
        self.download_btn.config(state="disabled" if busy or self.info is None else "normal")
        self.cancel_btn.config(state="normal" if busy else "disabled")

    # ---------------------------------------------------------------- yardımcılar

    @staticmethod
    def _clear_selection(tree: ttk.Treeview) -> None:
        for item in tree.selection():
            tree.selection_remove(item)

    def _selected_format_id(self, tree: ttk.Treeview) -> str | None:
        selection = tree.selection()
        if not selection:
            return None
        return str(tree.item(selection[0], "values")[0])

    def log(self, text: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ---------------------------------------------------------------- sorgulama

    def query(self) -> None:
        raw = self.url_var.get().strip()
        if not raw:
            messagebox.showinfo("Boş", "Önce bir bağlantı yapıştırın.", parent=self)
            return
        try:
            target = parse(raw)
        except ParseError as exc:
            messagebox.showerror("Geçersiz bağlantı", str(exc), parent=self)
            return
        if not target.video_id:
            messagebox.showwarning(
                "Video yok",
                "Girdide video ID'si bulunamadı.\n"
                "Tekil indirme için 'watch?v=…' bağlantısı veya video ID gerekir.",
                parent=self,
            )
            return
        url = video_url(target.video_id)
        self._set_busy(True)
        self.status_label.config(text="Sorgulanıyor…")

        def work():
            try:
                ytdlp, ffmpeg = self.get_runner_paths()
                runner = Runner(ytdlp, ffmpeg)
                info = SingleDownloader(self.config, runner).query(url)
                self.info = info
                self.bridge.post({"type": "info", "info": info})
                self.bridge.log(f"✓ {info.title}")
            except Exception as exc:
                self.info = None
                self.bridge.log(f"✗ {exc}")
                self.bridge.state(busy=False, status="Sorgu hatası")
                return
            self.bridge.state(busy=False, status="Sorgu tamam")

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _show_info(self, info: VideoInfo) -> None:
        self.info_label.config(
            text=f"{info.title}  •  {info.duration_str}  •  {info.uploader}",
            foreground="black",
        )
        self.audio_tree.delete(*self.audio_tree.get_children())
        self.video_tree.delete(*self.video_tree.get_children())
        for fmt in info.formats:
            _, fmt_id, ext, quality, codec, bitrate, size = fmt.display()
            row = (fmt_id, ext, quality, codec, bitrate, size)
            target = self.audio_tree if fmt.kind == "audio" else self.video_tree
            target.insert("", "end", values=row)
        self.download_btn.config(state="normal")

    # ---------------------------------------------------------------- indirme

    def download(self) -> None:
        if self.info is None:
            return
        mode = self.mode.get()

        # Arşiv ön kontrolü: aynı video tekrar inmesin
        ytdlp, ffmpeg = self.get_runner_paths()
        downloader = SingleDownloader(self.config, Runner(ytdlp, ffmpeg))
        if downloader.already_downloaded(self.info.video_id):
            messagebox.showinfo(
                "Zaten indirilmiş",
                "Bu video daha önce tekil olarak indirilmiş.\n"
                "Tekrar indirmek için Tekil klasöründeki 'indirilenler.txt'\n"
                "dosyasından ilgili satırı silin.",
                parent=self,
            )
            return

        audio_id = self._selected_format_id(self.audio_tree)
        video_id_fmt = self._selected_format_id(self.video_tree)

        try:
            if mode == MODE_AUDIO:
                args = downloader.audio_args(
                    self.info,
                    source_format_id=audio_id,
                    audio_format=self.audio_format.get(),
                    quality=self.audio_quality.get(),
                )
            elif mode == MODE_VIDEO:
                if not video_id_fmt:
                    messagebox.showwarning(
                        "Seçim yok",
                        "Bir video akışı seçin (Video Akışları listesinden).",
                        parent=self,
                    )
                    return
                args = downloader.video_args(self.info, video_id_fmt)
            else:  # mux
                if not video_id_fmt or not audio_id:
                    messagebox.showwarning(
                        "Seçim eksik",
                        "Birleştirme için bir video VE bir ses akışı seçin.",
                        parent=self,
                    )
                    return
                args = downloader.mux_args(self.info, video_id_fmt, audio_id)
        except Exception as exc:
            messagebox.showerror("Hazırlanamadı", str(exc), parent=self)
            return

        self._set_busy(True)
        self.bridge.state(busy=True, status="İndiriliyor…")
        self.log(f"— {self.info.title} —")
        self.log("yt-dlp " + " ".join(args[1:]))

        def work():
            try:
                runner = Runner(ytdlp, ffmpeg)
                self._current_runner = runner
                downloader = SingleDownloader(self.config, runner)
                folder = downloader.download(args, on_line=self._line_handler)
                self.bridge.log(f"✓ Tamamlandı: {folder}")
                self.bridge.state(busy=False, status="Tamamlandı")
            except SingleCancelled:
                self.bridge.log("■ İptal edildi")
                self.bridge.state(busy=False, status="İptal edildi")
            except Exception as exc:
                self.bridge.log(f"✗ Hata: {exc}")
                self.bridge.state(busy=False, status="Hata")
            finally:
                self._current_runner = None

        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _line_handler(self, line: str) -> None:
        info = parse_line(line)
        if (
            info.get("destination")
            or info.get("archived")
            or info.get("error")
            or "Merger" in line
            or "ExtractAudio" in line
        ):
            self.bridge.log(line)
        if "percent" in info:
            self.bridge.progress(percent=info["percent"], status=f"İndiriliyor %{info['percent']:.0f}")

    def cancel(self) -> None:
        if self._current_runner:
            self._current_runner.cancel()
            self.status_label.config(text="İptal ediliyor…")
