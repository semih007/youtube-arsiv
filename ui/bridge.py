"""Arka plan iş parçacıklarından GUI'ye güvenli mesaj geçişi."""

from __future__ import annotations

import queue
import tkinter as tk


class UIBridge:
    """Worker thread'lerden gelen olayları tkinter ana döngüsüne taşır.

    Kullanım: worker içinden bridge.post({...}) çağrılır; ana pencere
    bridge.on_event ile olayları yakalar.
    """

    def __init__(self, root, poll_ms: int = 80):
        self.root = root
        self._queue: queue.Queue = queue.Queue()
        self._handlers: list = []
        self._poll_ms = poll_ms
        self._stopped = False
        self._schedule()

    def on_event(self, handler) -> None:
        self._handlers.append(handler)

    def post(self, event: dict) -> None:
        """Worker thread'lerden güvenle çağrılabilir."""
        self._queue.put(event)

    def stop(self) -> None:
        """Pencere kapatılırken çağrılır: after döngüsünü durdurur."""
        self._stopped = True

    # ------------------------------------------------------------ log kolaylıkları

    def log(self, text: str) -> None:
        self.post({"type": "log", "text": text})

    def progress(self, percent: float | None = None, status: str | None = None) -> None:
        self.post({"type": "progress", "percent": percent, "status": status})

    def state(self, busy: bool, status: str | None = None) -> None:
        self.post({"type": "state", "busy": busy, "status": status})

    # ------------------------------------------------------------ iç

    def _schedule(self) -> None:
        if self._stopped:
            return
        try:
            self.root.after(self._poll_ms, self._poll)
        except tk.TclError:
            # pencere çoktan yok edilmiş olabilir
            self._stopped = True

    def _poll(self) -> None:
        while True:
            try:
                event = self._queue.get_nowait()
            except queue.Empty:
                break
            for handler in self._handlers:
                try:
                    handler(event)
                except Exception:
                    pass
        self._schedule()
