"""Caméra d'imprimante Bambu (X1 / H2D : flux RTSPS port 322) décodée par ffmpeg.

ffmpeg sort directement des images 160x160 en RGB565 little-endian, prêtes à envoyer.
"""
import logging
import shutil
import subprocess
import threading

log = logging.getLogger("knob.camera")
SIZE = 160
FRAME_BYTES = SIZE * SIZE * 2


class Camera:
    def __init__(self):
        self.proc = None
        self.frame = None
        self.seq = 0
        self.url = None

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, ip, code):
        url = f"rtsps://bblp:{code}@{ip}:322/streaming/live/1"
        if self.running and url == self.url:
            return True
        self.stop()
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            log.info("caméra : ffmpeg introuvable")
            return False
        self.url = url
        # Recadrage carré centré un peu à gauche (zone de la buse), 3 images/s.
        vf = f"fps=3,crop=ih:ih:(iw-ih)*0.35:0,scale={SIZE}:{SIZE}"
        self.proc = subprocess.Popen(
            [ffmpeg, "-loglevel", "quiet", "-rtsp_transport", "tcp", "-tls_verify", "0", "-i", url,
             "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb565le", "-"],
            stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True, name="camera").start()
        return True

    def _reader(self, proc):
        while proc.poll() is None:
            data = proc.stdout.read(FRAME_BYTES)
            if not data or len(data) < FRAME_BYTES:
                break
            self.frame = data
            self.seq += 1

    def stop(self):
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None
        self.frame = None
