"""Hızlı core katmanı duman testi (ağ gerektirmez).

Çalıştırma: python tests/smoke_core.py  (proje kökünden)
"""

from pathlib import Path

import core.config as cfg
import core.parser as parser
import core.runner as runner
import core.formats as formats
import core.sync as sync
import core.single as single
import core.timestamps as timestamps
import core.utils as utils

print("[1] core import OK")

music = cfg.get_music_folder()
print(f"[2] Muzik klasoru: {music}  (var mi: {music.exists()})")

name = utils.sanitize_filename('A/B: "Test" *Liste*?')
assert "/" not in name and ":" not in name and "?" not in name and "*" not in name
print(f"[3] sanitize_filename OK: {name}")

# ConfigStore: geçici dosyada yükle/kaydet/yol çözümleme
tmp = Path("tests/_tmp_config.json")
store = cfg.ConfigStore(tmp)
store.load()
store.data["yt_dlp_path"] = "yt-dlp.exe"
store.save()
loaded = cfg.ConfigStore(tmp)
loaded.load()
assert loaded.data["yt_dlp_path"] == "yt-dlp.exe"
assert tmp.exists()
tmp.unlink()
print("[4] ConfigStore kaydet/yukle OK")

# resolve_tool: tools/ içindeki yt-dlp bulunmalı
store2 = cfg.ConfigStore()
store2.load()
resolved = store2.resolve_tool("yt_dlp_path")
print(f"[5] resolve_tool yt-dlp: {resolved}")
assert resolved is not None and resolved.exists(), "tools/yt-dlp.exe bulunamadi"

# parse_line örnekleri
info = runner.parse_line("[download] Downloading item 3 of 25")
assert info.get("item") == 3 and info.get("total") == 25
info = runner.parse_line("[download]  45.3% of    3.5MiB at  ...")
assert abs(info.get("percent", 0) - 45.3) < 0.01
print("[6] parse_line OK")

# parser karışık URL
t = parser.parse("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLwIOf35e8aFWECZ4pGw-7rCrFwEhX3rzz&index=1")
assert t.video_id == "dQw4w9WgXcQ" and t.playlist_id == "PLwIOf35e8aFWECZ4pGw-7rCrFwEhX3rzz"
print("[7] parser OK")

# choose_container kuralları
from core.formats import FormatInfo

vf_h264 = FormatInfo(format_id="137", ext="mp4", kind="video", vcodec="avc1.640028", acodec="none")
af_aac = FormatInfo(format_id="140", ext="m4a", kind="audio", vcodec="none", acodec="mp4a.40.2")
vf_vp9 = FormatInfo(format_id="248", ext="webm", kind="video", vcodec="vp9", acodec="none")
af_opus = FormatInfo(format_id="251", ext="webm", kind="audio", vcodec="none", acodec="opus")
assert single.choose_container(vf_h264, af_aac) == "mp4"
assert single.choose_container(vf_vp9, af_opus) == "webm"
assert single.choose_container(vf_h264, af_opus) == "mkv"
print("[8] choose_container OK")

print("\nTUM CORE DUMAN TESTLERI GECTI")
