"""Spectre audio du PC pour le mode dédié média.

Capture en « loopback » WASAPI (ce que joue la sortie physique réellement utilisée, donc
après Sonar), FFT sur 2048 échantillons, 24 bandes logarithmiques de 50 Hz à 14 kHz,
gain automatique et retombée douce. Ne tourne que pendant le mode dédié.
"""
import logging
import threading

import numpy as np

log = logging.getLogger("knob.spectrum")
BANDS = 24
FFT_SIZE = 2048
F_MIN, F_MAX = 50, 14000
FALL = 0.80     # retombée des barres par trame (0..1)
DYNAMIC = 48    # dB affichés sous le pic courant


class Spectrum:
    def __init__(self):
        self.frame = None   # message "v..." prêt à envoyer
        self.seq = 0
        self._stop = threading.Event()
        self._thread = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, device_hint=""):
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(device_hint,), daemon=True, name="spectrum")
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.frame = None

    @staticmethod
    def _find_loopback(pa, hint):
        devices = [pa.get_device_info_by_index(i) for i in range(pa.get_device_count())]
        loops = [d for d in devices if d.get("isLoopbackDevice")]
        if hint:
            for d in loops:
                if hint.lower() in d["name"].lower():
                    return d
        return pa.get_default_wasapi_loopback()

    def _run(self, hint):
        import pyaudiowpatch as pyaudio
        pa = pyaudio.PyAudio()
        stream = None
        try:
            dev = self._find_loopback(pa, hint)
            rate, channels = int(dev["defaultSampleRate"]), max(1, dev["maxInputChannels"])
            stream = pa.open(format=pyaudio.paFloat32, channels=channels, rate=rate, input=True,
                             input_device_index=dev["index"], frames_per_buffer=1024)
            log.info("spectre : capture de %s (%d Hz)", dev["name"], rate)
            freqs = np.fft.rfftfreq(FFT_SIZE, 1 / rate)
            edges = np.geomspace(F_MIN, F_MAX, BANDS + 1)
            # Chaque bande prend ses cases FFT ; une bande trop étroite (graves) prend la plus proche.
            idx = [np.where((freqs >= lo) & (freqs < hi))[0] for lo, hi in zip(edges[:-1], edges[1:])]
            idx = [i if len(i) else np.array([np.abs(freqs - np.sqrt(lo * hi)).argmin()])
                   for i, lo, hi in zip(idx, edges[:-1], edges[1:])]
            window = np.hanning(FFT_SIZE).astype(np.float32)
            ring = np.zeros(FFT_SIZE, np.float32)
            levels = np.zeros(BANDS)
            peak = -30.0
            while not self._stop.is_set():
                raw = np.frombuffer(stream.read(1024, exception_on_overflow=False), np.float32)
                mono = raw.reshape(-1, channels).mean(axis=1)
                ring = np.concatenate([ring[len(mono):], mono])[-FFT_SIZE:]
                power = np.abs(np.fft.rfft(ring * window)) ** 2
                db = np.array([10 * np.log10(power[i].sum() + 1e-12) if len(i) else -120 for i in idx])
                peak = max(db.max(), peak - 0.15)        # gain automatique : suit le pic, redescend lentement
                target = np.clip((db - (peak - DYNAMIC)) / DYNAMIC, 0, 1)
                levels = np.maximum(target, levels * FALL)
                values = (levels * 63).astype(int)
                bass = int(values[:3].mean())
                self.frame = "v" + "".join(chr(48 + v) for v in values) + chr(48 + bass) + "\n"
                self.seq += 1
        except Exception:
            log.exception("spectre")
        finally:
            if stream:
                stream.close()
            pa.terminate()
            log.info("spectre : arrêt")
