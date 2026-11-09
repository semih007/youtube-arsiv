"""Gerçek ağ testleri: format sorgulama, tekil indirme, playlist senkronu.

İndirmeler GEÇİCİ klasöre yapılır; kullanıcının Müzik klasörüne dokunulmaz.
Çalıştırma:  python tests/test_real.py  (proje kökünden, PYTHONPATH=.)
"""

import os
import sys
import tempfile
import time
from pathlib import Path

from core.config import ConfigStore
from core.runner import Runner
from core.single import SingleDownloader
from core.sync import SyncEngine
from core.timestamps import fix_timestamps_in_dir

# Test videoyu ve playlist'i konsoldan değiştirilebilir kıl
TEST_VIDEO = os.environ.get("TEST_VIDEO", "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
TEST_PLAYLIST = os.environ.get("TEST_PLAYLIST", "PLwIOf35e8aFWECZ4pGw-7rCrFwEhX3rzz")

passed, failed = [], []


def check(name: str, condition: bool, detail: str = ""):
    status = "GECTI" if condition else "KALDI"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    (passed if condition else failed).append(name)


def new_config(temp_root: Path) -> ConfigStore:
    """Geçici indirme köküyle, tools/ araçlarını kullanan test config'i."""
    cfg = ConfigStore(Path(temp_root) / "config.json")
    cfg.load()
    cfg.data["download_root"] = str(temp_root)
    cfg.save()
    return cfg


def make_runner():
    ytdlp = ConfigStore().resolve_tool("yt_dlp_path")
    ffmpeg = ConfigStore().resolve_tool("ffmpeg_path")
    assert ytdlp and ffmpeg, "tools/ altında yt-dlp ve ffmpeg bulunamadı"
    return Runner(ytdlp, ffmpeg)


def test_formats():
    print("\n=== 1) Format sorgulama ===")
    runner = make_runner()
    info = SingleDownloader(new_config(Path(tempfile.mkdtemp())), runner).query(TEST_VIDEO)
    audios = info.audio_formats()
    videos = info.video_formats()
    print(f"    Video: {info.title} ({info.duration_str})")
    print(f"    Ses akışı: {len(audios)}  Video akışı: {len(videos)}")
    check("Format sorgulama", len(audios) >= 1 and len(videos) >= 1 and bool(info.video_id))
    return info


def test_single_download_audio(temp_root: Path):
    print("\n=== 2) Tekil indirme — Sadece Ses (MP3) ===")
    cfg = new_config(temp_root)
    downloader = SingleDownloader(cfg, make_runner())
    info = downloader.query(TEST_VIDEO)

    args = downloader.audio_args(info, audio_format="mp3", quality="320K")
    lines = []
    downloader.download(args, on_line=lines.append)
    folder = downloader.single_folder()
    mp3s = list(folder.glob("*.mp3"))
    check("MP3 indirildi", len(mp3s) >= 1, str(mp3s[0].name if mp3s else ""))
    archive_text = (folder / "indirilenler.txt").read_text(encoding="utf-8")
    check("Arşive yazıldı", info.video_id in archive_text)
    check("already_downloaded doğru", downloader.already_downloaded(info.video_id))
    size = mp3s[0].stat().st_size if mp3s else 0
    check("Dosya makul boyutta", 100_000 < size < 30_000_000, f"{size/1e6:.1f} MB")


def test_single_download_mux(temp_root: Path, mux_video: str):
    print("\n=== 3) Tekil indirme — Ses + Video (mux) ===")
    cfg = new_config(temp_root)
    downloader = SingleDownloader(cfg, make_runner())
    info = downloader.query(mux_video)

    # En küçük video akışı + en küçük ses akışını seç (test hızlı olsun)
    videos = sorted(info.video_formats(), key=lambda f: f.tbr or 9999)
    audios = sorted(info.audio_formats(), key=lambda f: f.abr or 999)
    if not videos or not audios:
        check("Mux için ayrık akış var", False, "video/ses akışı bulunamadı")
        return
    vf, af = videos[0], audios[0]
    print(f"    Video: {vf.format_id} {vf.resolution} {vf.vcodec} | Ses: {af.format_id} {af.acodec}")

    args = downloader.mux_args(info, vf.format_id, af.format_id)
    container = args[args.index("--merge-output-format") + 1]
    print(f"    Kapsayıcı: {container}")
    downloader.download(args)
    outs = [p for p in downloader.single_folder().glob("*.*") if p.suffix in (".mp4", ".webm", ".mkv")]
    check("Mux çıktısı üretildi", len(outs) >= 1, str(outs[0].name if outs else ""))
    check("Kapsayıcı doğru", outs and outs[0].suffix == "." + container)


def test_sync(temp_root: Path, playlist_id: str):
    print(f"\n=== 4) Playlist senkronu ({playlist_id}) — ilk 2 video ===")
    cfg = new_config(temp_root)
    engine = SyncEngine(cfg, make_runner())

    title = engine.fetch_title(playlist_id)
    print(f"    Liste adı: {title}")
    check("Başlık çekildi", bool(title) and title != playlist_id, title)

    engine.update_folder(playlist_id, title)
    engine.sync_playlist(playlist_id, extra_args=["--playlist-items", "1:2"])
    folder = engine.playlist_folder(engine.config.find_playlist(playlist_id))
    mp3s = list(folder.glob("*.mp3"))
    archive = folder / "indirilenler.txt"
    check("Klasör orijinal adda oluştu", folder.exists() and folder.name != playlist_id, folder.name)
    check("MP3'ler indirildi", len(mp3s) >= 1, f"{len(mp3s)} dosya")
    check("Arşiv dosyası var", archive.exists())

    # 2. çalıştırma: arşivdeki videolar tekrar INMEMELI
    before = {p.name: p.stat().st_mtime for p in mp3s}
    engine.sync_playlist(playlist_id, extra_args=["--playlist-items", "1:2"])
    after = {p.name: p.stat().st_mtime for p in folder.glob("*.mp3")}
    check("Tekrar indirme yok (arşiv)", before == after and len(after) == len(before))

    # Zaman damgaları: creation <= modification
    ok_ts = all(p.stat().st_ctime <= p.stat().st_mtime + 2 for p in folder.glob("*.mp3"))
    check("Zaman damgaları sabitlendi (creation <= mtime)", ok_ts)


def test_timestamps_directly(temp_root: Path):
    print("\n=== 5) Zaman damgası yardımcısı ===")
    f = temp_root / "deneme.txt"
    f.write_text("test", encoding="utf-8")
    from core.timestamps import set_creation_time

    ok = set_creation_time(f, 1_000_000_000)  # 2001-09-09
    st = f.stat()
    check(
        "set_creation_time çalışıyor",
        ok and abs(st.st_ctime - 1_000_000_000) < 5,
        f"ctime={st.st_ctime:.0f} (beklenen ~1000000000)",
    )


def main():
    print("Gerçek ağ testleri başlıyor (geçici klasöre indiriliyor)…")
    temp_root = Path(tempfile.mkdtemp(prefix="ytarsiv_test_"))
    print(f"Geçici kök: {temp_root}")

    try:
        test_single_download_audio(temp_root)
    except Exception as exc:
        print(f"!! Ses testi hatası: {exc}")
        failed.append(f"ses: {exc}")

    try:
        # Mux testi farklı video kullanır: aynı video arşiv nedeniyle ikinci kez inmez
        test_single_download_mux(temp_root, "https://www.youtube.com/watch?v=aqz-KE-bpKQ")
    except Exception as exc:
        print(f"!! Mux testi hatası: {exc}")
        failed.append(f"mux: {exc}")

    try:
        test_sync(temp_root, TEST_PLAYLIST)
    except Exception as exc:
        print(f"!! Senkron testi hatası: {exc}")
        failed.append(f"sync: {exc}")

    test_timestamps_directly(temp_root)

    print(f"\n===== SONUÇ: {len(passed)} geçti, {len(failed)} kaldı =====")
    for f in failed:
        print(f"  KALDI: {f}")
    print(f"(Geçici klasör: {temp_root} — elle silebilirsiniz)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
