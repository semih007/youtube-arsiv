"""yt-dlp alt süreç sarmalayıcı: çıktı akışı, ilerleme ayrıştırma, iptal."""

from __future__ import annotations

import re
import subprocess
import threading

# yt-dlp çıktı kalıpları
PROGRESS_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
ITEM_RE = re.compile(r"\[download\] Downloading item (\d+) of (\d+)")
DEST_RE = re.compile(r"\[download\] Destination: (.+)")
ALREADY_RE = re.compile(r"has already been recorded in the archive")
ERROR_RE = re.compile(r"^ERROR:", re.IGNORECASE)
WARNING_RE = re.compile(r"^WARNING:", re.IGNORECASE)


# ---------------------------------------------------------------- süreç kaydı
# Canlı yt-dlp süreçleri burada tutulur; pencere kapatılırken hepsi
# ağaçlarıyla birlikte öldürülür (kill_all_active). Bu olmadan exe kapansa
# bile yt-dlp + ffmpeg arka planda indirmeye devam eder.

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_PROCS: set = set()


def _register(proc) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_PROCS.add(proc)


def _unregister(proc) -> None:
    with _ACTIVE_LOCK:
        _ACTIVE_PROCS.discard(proc)


def _kill_tree(proc) -> None:
    """Bir süreci TÜM alt süreçleriyle birlikte zorla öldürür.

    yt-dlp.exe (PyInstaller onefile) iki sürece ayrılır: bootloader + gerçek
    işçi. proc.terminate() yalnızca bootloader'ı öldürür; işçi ve onun
    başlattığı ffmpeg yaşamaya devam eder. taskkill /T tüm ağacı kapatır.
    """
    if proc.poll() is not None:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        # taskkill bulunamaz/bozulursa son çare: en azından kendisini öldür
        try:
            proc.kill()
        except OSError:
            pass


def kill_all_active() -> None:
    """Kayıtlı tüm canlı yt-dlp süreçlerini ağaçlarıyla öldürür.

    Pencere kapatılırken çağrılır: indirme yarıda kalır ama hiçbir süreç
    arka planda kalmaz.
    """
    with _ACTIVE_LOCK:
        procs = list(_ACTIVE_PROCS)
    for proc in procs:
        _kill_tree(proc)


def parse_line(line: str) -> dict:
    """Bir yt-dlp çıktı satırını yapılandırılmış bilgiye çevirir."""
    info: dict = {"raw": line}
    m = ITEM_RE.search(line)
    if m:
        info["item"] = int(m.group(1))
        info["total"] = int(m.group(2))
    m = PROGRESS_RE.search(line)
    if m:
        info["percent"] = float(m.group(1))
    m = DEST_RE.search(line)
    if m:
        info["destination"] = m.group(1).strip()
    if ALREADY_RE.search(line):
        info["archived"] = True
    if ERROR_RE.match(line.strip()):
        info["error"] = True
    if WARNING_RE.match(line.strip()):
        info["warning"] = True
    return info


class Runner:
    """Tek bir yt-dlp sürecini yönetir (akış veya tek-parça modu)."""

    def __init__(self, yt_dlp_path, ffmpeg_path=None):
        self.yt_dlp_path = str(yt_dlp_path)
        self.ffmpeg_path = str(ffmpeg_path) if ffmpeg_path else None
        self._process: subprocess.Popen | None = None
        self.cancelled = False

    # ---------------------------------------------------------------- iptal

    def cancel(self) -> None:
        """Çalışan süreci tüm alt süreçleriyle sonlandırır."""
        self.cancelled = True
        proc = self._process
        if proc is not None and proc.poll() is None:
            _kill_tree(proc)

    @property
    def is_running(self) -> bool:
        proc = self._process
        return proc is not None and proc.poll() is None

    # ---------------------------------------------------------------- komut hazırlama

    def _base_cmd(self) -> list[str]:
        cmd = [self.yt_dlp_path]
        # Windows'ta yt-dlp pipe'a yerel kod sayfasıyla (ör. Türkçe cp1254)
        # yazar; biz UTF-8 beklediğimiz için Türkçe karakterler bozulurdu.
        # --encoding ile çocuk süreci UTF-8 çıkışa zorlanır.
        cmd += ["--encoding", "utf-8"]
        if self.ffmpeg_path:
            cmd += ["--ffmpeg-location", self.ffmpeg_path]
        return cmd

    # ---------------------------------------------------------------- akış modu

    def run(self, args: list[str], on_line=None) -> int:
        """yt-dlp'yi çalıştırır; her çıktı satırı on_line(line) ile verilir.

        Dönüş: süreç çıkış kodu (iptal edilmişse -1).
        """
        self.cancelled = False
        try:
            self._process = subprocess.Popen(
                self._base_cmd() + list(args),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as exc:
            raise RuntimeError(f"yt-dlp başlatılamadı: {exc}") from exc

        _register(self._process)
        try:
            assert self._process.stdout is not None
            for line in self._process.stdout:
                line = line.rstrip("\r\n")
                if on_line is not None:
                    try:
                        on_line(line)
                    except Exception:
                        pass  # GUI hatası indirmeyi durdurmasın
            code = self._process.wait()
        finally:
            _unregister(self._process)
            self._process = None
        return -1 if self.cancelled else code

    # ---------------------------------------------------------------- tek-parça modu

    def run_capture(self, args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
        """Çıktıyı tek parça olarak toplar (--dump-json gibi sorgular için).

        Süreç kayda alınır: pencere kapanırsa veya zaman aşımı olursa
        tüm alt süreç ağacı öldürülür (yetim yt-dlp kalmasın).
        """
        try:
            proc = subprocess.Popen(
                self._base_cmd() + list(args),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except OSError as exc:
            raise RuntimeError(f"yt-dlp başlatılamadı: {exc}") from exc

        _register(proc)
        try:
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_tree(proc)
                out, err = proc.communicate()
                raise
        finally:
            _unregister(proc)
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
