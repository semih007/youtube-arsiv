"""Senkronizasyon numaralandırması testleri (ağ gerektirmez).

Senaryo: 255 şarkılık klasöre sonradan eklenen yeni şarkılar
'mevcut en büyük numara + 1' ile (256, 257, ...) adlandırılmalı;
%(playlist_index) kullanılmadığı için liste başına eklenen şarkı
'01' almamalı.

Çalıştırma:  PYTHONPATH=. python tests/test_numbering.py
"""

import sys
import tempfile
from pathlib import Path

from core.sync import _archive_ids, renumber_new_files

passed, failed = [], []


def check(name: str, condition: bool, detail: str = ""):
    status = "GECTI" if condition else "KALDI"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    (passed if condition else failed).append(name)


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_continues_from_max():
    """255'te kalan klasöre yeni şarkı -> 256, 257."""
    folder = Path(tempfile.mkdtemp(prefix="num_test_"))
    (folder / "01 - Eski Sarki.mp3").write_bytes(b"x")
    (folder / "255 - Son Sarki.mp3").write_bytes(b"x")
    (folder / "indirilenler.txt").write_text("youtube a\nyoutube b\n", encoding="utf-8")

    # yeni inen dosyalar: '<baslik> [<id>].<uzanti>' sablonuyla
    (folder / "Yeni Sarki [vid999].mp3").write_bytes(b"x")
    (folder / "Baska Yeni [vid888].mp3").write_bytes(b"x")

    renamed = renumber_new_files(folder, ["vid999", "vid888"])
    got = names(folder)
    check(
        "yeni sarkilar 256/257 aldi",
        "256 - Yeni Sarki.mp3" in got and "257 - Baska Yeni.mp3" in got,
        str(got),
    )
    check("eski dosyalar degismedi", "01 - Eski Sarki.mp3" in got and "255 - Son Sarki.mp3" in got)
    check("[id] eki kaldirildi", not any("[vid" in n for n in got))
    check("donus sirasi dogru", len(renamed) == 2)


def test_fresh_folder_starts_at_01():
    """Bos klasor -> 01, 02 (taze indirme sirasi)."""
    folder = Path(tempfile.mkdtemp(prefix="num_test_"))
    (folder / "Ilk [a1].mp3").write_bytes(b"x")
    (folder / "Ikinci [b2].mp3").write_bytes(b"x")
    renumber_new_files(folder, ["a1", "b2"])
    got = names(folder)
    check("taze indirme 01/02", "01 - Ilk.mp3" in got and "02 - Ikinci.mp3" in got, str(got))


def test_missing_file_skipped():
    """Id'nin dosyasi yoksa (donusum hatasi) sessizce atlanir."""
    folder = Path(tempfile.mkdtemp(prefix="num_test_"))
    (folder / "01 - Var.mp3").write_bytes(b"x")
    renamed = renumber_new_files(folder, ["yokboyle", "vidvar"])
    check("eksik dosya atlandi", renamed == [])


def test_empty_and_no_ids():
    """Bos liste / bos klasor guvenli."""
    folder = Path(tempfile.mkdtemp(prefix="num_test_"))
    check("bos liste no-op", renumber_new_files(folder, []) == [])
    check("bos klasor no-op", renumber_new_files(folder, ["x1"]) == [])


def test_archive_ids_order():
    """Arşiv satirlari indirme sirasyla donmeli."""
    folder = Path(tempfile.mkdtemp(prefix="num_test_"))
    arch = folder / "indirilenler.txt"
    arch.write_text("youtube id1\nyoutube id2\n\nyoutube id3\n", encoding="utf-8")
    check("arsiv id sirasi", _archive_ids(arch) == ["id1", "id2", "id3"])
    check("olmayan arsiv bos", _archive_ids(folder / "yok.txt") == [])


def test_title_containing_brackets():
    """Basliginda ' [x]' gecen sarkida yalniz gercek [id] eki soyulmali."""
    folder = Path(tempfile.mkdtemp(prefix="num_test_"))
    (folder / "Sarki [Remix] [vid42].mp3").write_bytes(b"x")
    renumber_new_files(folder, ["vid42"])
    got = names(folder)
    check("icerdeki parantez korundu", "01 - Sarki [Remix].mp3" in got, str(got))


def main() -> int:
    test_continues_from_max()
    test_fresh_folder_starts_at_01()
    test_missing_file_skipped()
    test_empty_and_no_ids()
    test_archive_ids_order()
    test_title_containing_brackets()
    print(f"\n===== SONUC: {len(passed)} gecti, {len(failed)} kaldi =====")
    for f in failed:
        print(f"  KALDI: {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
