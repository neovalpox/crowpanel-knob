"""Banc de test du mode dédié : pilote le module directement (compagnon arrêté).

Verrouille la vue média, envoie une pochette, puis un spectre aléatoire à 30 images/s,
et affiche les rapports de performance du module (M...). Si le module se fige, plus
aucune ligne n'arrive.
Usage : .venv\\Scripts\\python tools_test_media_lock.py [secondes]
"""
import math
import random
import sys
import time

import serial
from serial.tools import list_ports

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 20
MODE = sys.argv[2] if len(sys.argv) > 2 else "normal"  # normal | zero | none
port = next(p.device for p in list_ports.comports() if p.vid == 0x303A and p.pid == 0x4C4B)
ser = serial.Serial()
ser.port, ser.baudrate, ser.timeout, ser.write_timeout = port, 115200, 0, 2
ser.dtr, ser.rts = True, False
ser.open()


def send(s):
    ser.write(s.encode() if isinstance(s, str) else s)


send("V40 M0\n")
time.sleep(0.5)
# Pochette factice 72x72 (dégradé) puis verrouillage.
px = bytearray()
for y in range(72):
    for x in range(72):
        c = ((x * 31 // 72) << 11) | ((y * 63 // 72) << 5) | 20
        a = 255 if (x - 36) ** 2 + (y - 36) ** 2 < 36 * 36 else 0
        px += bytes([c & 0xFF, c >> 8, a])
send(f"I72 72 {len(px)}\n".encode() + bytes(px))
send("u\n")
send("e1\n")
TITLE = sys.argv[3] if len(sys.argv) > 3 else "Titre de test assez long pour defiler"
send(f"k{TITLE}\tArtiste\t1ED760\t250\t1\n")

real = None
if MODE == "real":  # vrai spectre de la musique en cours (capture loopback du PC)
    import comtypes
    comtypes.CoInitialize()
    import audio_out
    import spectrum
    real = spectrum.Spectrum()
    real.start(audio_out.current()[1])
    time.sleep(1)

t0, last_rx, buf, frame = time.time(), time.time(), b"", 0
while time.time() - t0 < DURATION:
    frame += 1
    phase = frame / 6
    bands = [int(31 + 31 * math.sin(phase + i / 3) * random.uniform(0.6, 1)) for i in range(24)]
    bass = max(0, min(63, int(40 + 23 * math.sin(phase * 2))))
    if MODE == "zero":
        bands, bass = [0] * 24, 0
    if real is not None:
        if real.frame:
            send(real.frame)
    elif MODE != "none":
        send("v" + "".join(chr(48 + max(0, min(63, b))) for b in bands) + chr(48 + bass) + "\n")
    if frame % 15 == 0:
        send("V40 M0\n")  # garde la liaison « synchronisée »
    data = ser.read(4096)
    if data:
        buf += data
        last_rx = time.time()
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if line.startswith(b"M"):
                print(f"{time.time() - t0:5.1f}s  {line.decode(errors='ignore')}")
    elif time.time() - last_rx > 5:
        print(f"{time.time() - t0:5.1f}s  !!! plus aucune réponse du module depuis 5 s (figé ?)")
        last_rx = time.time()
    time.sleep(1 / 30)
send("e0\n")
ser.close()
print("fin du test,", frame, "trames envoyées")
