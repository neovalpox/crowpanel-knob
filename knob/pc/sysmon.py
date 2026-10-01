"""Charge du PC pour la tuile système : CPU, RAM (psutil) et GPU NVIDIA (nvidia-smi).

nvidia-smi est lancé dans un thread toutes les 2 s pour ne pas bloquer la boucle.
"""
import shutil
import subprocess
import threading
import time

import psutil


class SysMon:
    def __init__(self):
        self.gpu = -1        # % d'utilisation, -1 = pas de GPU NVIDIA
        self.gpu_temp = -1   # °C
        self.gpu_name = ""
        psutil.cpu_percent(None)  # amorce la mesure différentielle
        if shutil.which("nvidia-smi"):
            threading.Thread(target=self._gpu_loop, daemon=True, name="gpu").start()

    def _gpu_loop(self):
        while True:
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,name",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
                ).stdout.splitlines()[0]
                util, temp, name = [x.strip() for x in out.split(",", 2)]
                self.gpu, self.gpu_temp, self.gpu_name = int(util), int(temp), name
            except Exception:
                self.gpu = self.gpu_temp = -1
            time.sleep(2)

    def snapshot(self):
        return {
            "cpu": round(psutil.cpu_percent(None)),
            "ram": round(psutil.virtual_memory().percent),
            "gpu": self.gpu,
            "gpu_temp": self.gpu_temp,
        }

    def message(self):
        s = self.snapshot()
        return f"G{s['cpu']}\t{s['gpu']}\t{s['ram']}\t{s['gpu_temp']}\n"
