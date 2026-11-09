"""YouTube Arşiv — giriş noktası.

Kullanım (betik olarak):
    python main.py

İlk açılışta yt-dlp ve ffmpeg yolları sorulur ve config.json'a kaydedilir;
sonraki açılışlarda hatırlanır. Uygulama klasörü bütün olarak taşınabilir.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk

from core.config import ConfigStore
from core.runner import kill_all_active
from ui.app import App
from ui.setup_dialog import run_first_time_setup


def _shutdown() -> None:
    """Uygulamadan çıkış: kalan tüm alt süreçleri öldür ve process'i garantili kapat.

    os._exit, daemon thread'ler pipe okumasında bloklanmış olsa bile
    process'in kesin ölmesini sağlar (exe'nin arka planda kalmasını önler).
    """
    kill_all_active()
    os._exit(0)


def main() -> int:
    root = tk.Tk()
    root.withdraw()  # kurulum diyaloğu öncesi ana pencereyi gizle

    config = ConfigStore()
    config.load()

    # İlk kurulum: config.json yoksa VEYA araçlar çözümlenemiyorsa
    tools_ok = (
        config.resolve_tool("yt_dlp_path") is not None
        and config.resolve_tool("ffmpeg_path") is not None
    )
    if not config.exists or not tools_ok:
        if not run_first_time_setup(root, config):
            root.destroy()
            _shutdown()

    root.deiconify()
    App(root, config)
    root.mainloop()
    _shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
